# Round 14 — Phase 4+: REAL token streaming for /v1/chat/completions

> Validate the SHIPPED **real (incremental) token streaming** on the OpenAI chat endpoint (orchestrator
> slices 3a #21 `BaseAgent.run_stream` + 3b #22 SSE seam, merged to main) from a downstream project: an
> opt-in agent streams LLM output token-by-token THROUGH the governance chokepoint and the incremental
> secret gate, while a non-opt-in chat agent keeps the format-level fallback.

## Goal

Round 13 proved **format-level** streaming (run the agent fully, then stream the finished output as SSE).
Round 14 proves **real** streaming, from a downstream project's point of view:

- the lab's `digest` agent now overrides `_stream`, so `stream:true` streams **incrementally** — multiple
  `chat.completion.chunk` content deltas, one per complete line (the gate is line-buffered), reconstructing
  the output; vs format-level's single content blob;
- **capability-gated**: `reviewer` is chat-capable but does NOT override `_stream` → `supports_streaming()`
  is False → it falls back to format-level (one content chunk) on the SAME endpoint/request;
- **rule 9 on a live stream**: a secret on a later line lets the clean prefix stream, then ends the SSE
  `content_filter` with the secret line never sent (only scanned-clean bytes ever leave);
- **input gate is still pre-stream**: an injection input → 400 JSON (not a half-open SSE 200);
- **governance inherited via `run_stream`**: a real-streamed run is audited `root=True`; an over-budget
  agent is denied on the first pull → 200 SSE ending `finish_reason=error` + a `budget_exceeded` audit row
  (you cannot 500 after a 200).

## What's being tested

The driver runs the real combined HTTP app (`build_http_app(LAB_ROOT)` — the same app `lottie serve --port`
serves) via Starlette's `TestClient`, with `build_provider` patched per-case to a `MockLLMProvider` (API keys
unset). `digest` (opted into `_stream`) is the real-streaming example; `reviewer` (chat block, no `_stream`)
is the fallback example. The MockLLMProvider's `stream_complete` replays the canned response as deltas, so a
multi-line response surfaces as multiple line chunks through the gate.

| # | Case | Checks |
|---|------|--------|
| 1 | real multi-chunk | digest + multi-line → **>1** content chunk, reconstructs output, finish `stop` |
| 2 | capability fallback | reviewer (no `_stream`) → **1** content chunk (format-level), same endpoint |
| 3 | secret clean-prefix-then-cut | clean line streams, then `content_filter`, secret line never sent |
| 4 | input reject pre-stream | injection + `stream:true` → **400 JSON** (not SSE), payload not echoed |
| 5 | governance audit root | a real-streamed run is audited `root=True`, `ok` |
| 6 | budget denial mid-stream | over-budget → 200 SSE finish `error`, no content, `budget_exceeded` audit |

## Setup (lab changes for this round)

- `agents/digest/agent.py` — added a `_stream` override mirroring `_execute` (`yield from
  self.stream_complete([...])`) → opts `digest` into real streaming.
- `agents/reviewer/config.yaml` — added a `chat:` block (no `_stream`) → the capability-fallback example.

## Build / verify sequence

```bash
source .venv/bin/activate
uv pip install -e '../lottie-orchestrator[api,serve,mesh,otel]'   # editable; sees main (3a+3b)
python3 rounds/round-14-real-streaming/_real_streaming_driver.py  # writes outputs/, PASS/FAIL per case
```

## Definition of done — ✅ COMPLETE (6/6)

Real token streaming validated end-to-end from a downstream project: incremental multi-chunk SSE for an
opt-in agent, capability-gated format-level fallback for a non-opt-in chat agent, the inherited
fail-closed gates (live secret cut with the clean prefix retained, injection input → 400 JSON), and
governance through `run_stream` (audit `root=True`; over-budget → SSE `error` + `budget_exceeded` audit).
**6/6 PASS.**

## Deviations / notes

- Validated **in-process** via `build_http_app` + Starlette `TestClient` (no live uvicorn). `TestClient`
  buffers the SSE body, so `resp.text` holds the full event stream; chunk *count* still proves real
  incremental chunking (digest n>1 vs reviewer n==1 on the same multi-line output).
- **Line-buffered granularity** (by design): the gate emits per complete line, so "real token streaming"
  is line-granular, not character-granular — sound because `detect-secrets` is line-scoped. A single-line
  (no-newline) response buffers to one chunk; the multi-line responses here exercise the incremental path.
- **No `usage` chunk** in the SSE (OpenAI's `stream_options.include_usage` final-usage chunk is a deferred
  framework slice; the audit ledger still records full/partial usage server-side).
- A mid-stream failure (case 6's budget denial) now logs server-side (`logger.warning(..., exc_info=True)`)
  in addition to the `finish_reason=error` + audit row — the expected `BudgetExceeded` traceback in the run
  log is that observability, not a failure.
- Cross-naming (carried): the chat `model` field uses the agent directory name (`digest`) while the audit
  ledger keys the class name (`DigestAgent`); the governance cases query by `DigestAgent`.
