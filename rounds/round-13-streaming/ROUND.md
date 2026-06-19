# Round 13 — Phase 4: SSE streaming for /v1/chat/completions

> Validate the SHIPPED `stream:true` SSE streaming on the OpenAI chat endpoint (orchestrator PR #18,
> merged to main) from a downstream project: an OpenAI client that requires `stream:true` gets a valid
> `text/event-stream` response, the output gate still fires before any byte streams, and pre-stream
> errors stay normal JSON.

## Goal

Prove, from a downstream project's point of view, that:
- `POST /v1/chat/completions` with `stream:true` → `200 text/event-stream`, OpenAI `chat.completion.chunk`
  events (role → content → finish `stop` → `[DONE]`);
- the SAME endpoint still returns a JSON `chat.completion` when `stream` is omitted (both modes, one
  endpoint);
- **the fail-closed SecurityGate is inherited** — a secret in the output streams a `content_filter`
  finish with **no content** (the secret never streams); a prompt-injection input → **400 JSON** (not an
  SSE 200), because the input gate fires before the agent runs;
- pre-stream errors stay JSON: an unknown model + `stream:true` → 404 JSON `model_not_found`;
- governance is inherited on the streamed path (a streamed run is audited `root=True`).

## What's being tested

The driver runs the real combined HTTP app (`build_http_app(LAB_ROOT)` — the same app `lottie serve
--port` serves) via Starlette's `TestClient`, with `build_provider` patched to a `MockLLMProvider` (API
keys unset). The lab's `digest` agent is chat-capable (a `chat:` block), so it is reachable on
`/v1/chat/completions`. Format-level streaming: the agent runs fully, then its output streams as SSE.

| # | Case | Checks |
|---|------|--------|
| 1 | stream happy path | `stream:true` → 200 `text/event-stream`, role/content/`stop`/`[DONE]` chunks |
| 2 | both modes, one endpoint | omit stream → JSON `chat.completion`; `stream:true` → SSE |
| 3 | output security | secret + `stream:true` → 200 SSE `content_filter` finish, no content, secret never streams |
| 4 | input security | injection + `stream:true` → **400 JSON** (not SSE), payload not echoed |
| 5 | unknown model | `stream:true` + bad model → 404 JSON `model_not_found` |
| 6 | governance inherited | a streamed run is audited `root=True` |

## Build / verify sequence

```bash
# orchestrator installed editable with [api]; lab venv:
source .venv/bin/activate
uv pip install -e '../lottie-orchestrator[api,serve,mesh,otel]'
python3 rounds/round-13-streaming/_streaming_driver.py   # writes outputs/, prints PASS/FAIL per case
```

## Definition of done — ✅ COMPLETE (6/6)

SSE streaming validated end-to-end from a downstream project: a spec-shaped `text/event-stream`
response on `stream:true`, both modes on one endpoint, the inherited fail-closed SecurityGate (output
withhold streams no secret, injection input → 400 JSON), pre-stream errors stay JSON, and inherited audit.
**6/6 PASS.**

## Deviations / notes

- Validated **in-process** via the real `build_http_app` hook with Starlette's `TestClient` — no live
  uvicorn needed; `TestClient` buffers the SSE stream (a sync iterator over a pre-built list of chunks),
  so `resp.text` holds the full event stream.
- Scope is **format-level** streaming (the agent runs fully, then streams its completed output) — real
  token-by-token incremental generation, `usage` in chunks, and REST `/run` streaming are deferred
  framework slices (spec §1), out of scope.
- Cosmetic cross-naming (carried): the chat `model` field uses the agent directory name (`digest`) while
  the audit ledger keys the class name (`DigestAgent`) — the governance case queries by `DigestAgent`.
  Pre-existing `BaseAgent.name` behavior.
