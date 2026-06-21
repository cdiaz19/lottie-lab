# Round 14 — Phase 4+: REAL token streaming for /v1/chat/completions — Results

**Framework under test:** `lottie-orchestrator @ main` (slices 3a #21 `BaseAgent.run_stream` squash `a3e6818`,
3b #22 SSE seam squash `248815c`), installed editable in the lab venv with `[api,serve,mesh,otel]`.
**Harness:** `_real_streaming_driver.py` — `build_http_app(LAB_ROOT)` driven by Starlette's `TestClient`,
`build_provider` patched per-case to a `MockLLMProvider`. `digest` (now overrides `_stream`) is the real
example; `reviewer` (chat block, no `_stream`) is the fallback example.

**Headline: 6/6 pass. `stream:true` on an opt-in agent streams LLM output INCREMENTALLY — multiple content
chunks through the line-buffered secret gate, governed by `BaseAgent.run_stream` (policy/cost/audit
inherited). A non-opt-in chat agent falls back to format-level on the same endpoint. The fail-closed gates
hold on a live stream: a secret cuts the stream after the clean prefix already streamed, an injection input
is a pre-stream 400 JSON, and an over-budget run ends `finish_reason=error` with a `budget_exceeded` audit.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | real multi-chunk | >1 content chunk | digest + `"alpha\nbeta\ngamma\n"` → 3 content deltas `["alpha\n","beta\n","gamma\n"]`, role first, `finish=stop`, `[DONE]`; all `chat.completion.chunk` | ✅ |
| 2 | capability fallback | 1 content chunk | reviewer (no `_stream`) + same multi-line output → **1** content delta `"alpha\nbeta\ngamma\n"`, `finish=stop` | ✅ |
| 3 | secret clean-prefix-then-cut | prefix streams, then content_filter | `"safe line\n"` delivered, last chunk `finish=content_filter`, `AKIA` absent from the stream | ✅ |
| 4 | input reject pre-stream | 400 JSON, not SSE | injection input → 400 `application/json` `content_filter`, payload not echoed | ✅ |
| 5 | governance audit root | `root=True` audit | one `DigestAgent` record, `root=True`, `status=ok` | ✅ |
| 6 | budget denial mid-stream | 200 SSE `error` + audit | over-budget digest → 200 SSE, last chunk `finish=error`, no content, `budget_exceeded` in audit | ✅ |

## Proof points

- **Real incremental streaming** (case 1): the same endpoint that returned ONE content blob in Round 13 now
  returns THREE content deltas for a three-line output — the agent's `_stream` flows token deltas through
  `run_stream` → the line-buffered `StreamingSecretGate`, emitting one chunk per complete line. `n_content
  chunks > 1` is the format-vs-real discriminator.
- **Capability gate picks the path** (case 2): `reviewer` declares `chat:` but does not override `_stream`,
  so `supports_streaming()` is False and the transport falls back to format-level — the identical multi-line
  output arrives as a SINGLE content chunk. digest (real, n>1) vs reviewer (fallback, n==1) on the same
  request shape proves `AgentService.stream_agent` returns the gated stream for opt-in agents and `None`
  (→ fallback) otherwise.
- **Rule 9 on a live stream** (case 3): a secret on a later line is stronger than format-level's
  withhold-everything — the clean prefix line **does** stream (only scanned-clean bytes ever leave), then
  the gate trips and the SSE ends `content_filter`; the secret line itself is never emitted. A later secret
  cannot un-send the clean prefix, and never streams itself.
- **Input gate stays pre-stream** (case 4): `stream_agent` gates the input EAGERLY (before `run_stream` is
  pulled), so an injection input is a normal **400 JSON** `content_filter`, not a half-open SSE 200, with no
  payload echo.
- **Governance through `run_stream`** (cases 5–6): a real-streamed run produces one `root=True` audit record
  — content flows THROUGH `BaseAgent.run_stream`, never around it, so policy/cost/audit are inherited. An
  over-budget agent is denied on the first pull: the cost gate raises, the transport maps it to a terminal
  `finish_reason=error` (a 200 SSE is already committed — you cannot 500 after a 200), and a `budget_exceeded`
  audit row is written. The mid-stream failure is also logged server-side.

## Findings

No defects. Notes (carried / by-design, not bugs):
- Streaming is **line-granular**, not character-granular — the secret gate emits per complete line (sound
  because `detect-secrets` is line-scoped). A no-newline response buffers to a single chunk.
- No `usage` object in the SSE chunks (OpenAI's `stream_options.include_usage` final-usage chunk is a
  deferred framework slice); usage is still recorded in the audit ledger server-side.
- Cross-naming (carried): chat `model` = directory name (`digest`); audit ledger keys the class name
  (`DigestAgent`).

## §-sign-off checklist

- [x] Opt-in agent streams INCREMENTALLY: >1 `chat.completion.chunk` content delta, reconstructs output, `[DONE]`
- [x] Capability fallback: a chat agent without `_stream` → 1 content chunk (format-level) on the same endpoint
- [x] Rule 9 on a live stream: clean prefix streams, secret cuts to `content_filter`, secret never sent
- [x] Input gate pre-stream: injection → 400 JSON (not SSE), no payload echo
- [x] Streamed run inherits audit (`root=True`) via `run_stream`
- [x] Cost gate fires on the streamed path: over-budget → SSE `finish=error` + `budget_exceeded` audit
- [x] Findings recorded honestly (line-granular scope, no-usage-chunk, cross-naming noted)

**Verdict:** Real token streaming validated end-to-end — **6/6** — incremental SSE on `/v1/chat/completions`
for opt-in agents, capability-gated format-level fallback, the fail-closed gates on a live stream, and full
governance inherited through `BaseAgent.run_stream`. Phase 4+ real-streaming (slices 1→2→3a→3b) is confirmed
on `main`.
