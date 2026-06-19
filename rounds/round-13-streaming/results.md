# Round 13 — Phase 4: SSE streaming for /v1/chat/completions — Results

**Framework under test:** `lottie-orchestrator @ main` (PR #18 merged, squash `6ba0e58`), installed
editable in the lab venv with `[api]` (+ serve, mesh, otel).
**Harness:** `_streaming_driver.py` — `build_http_app(LAB_ROOT)` driven by Starlette's `TestClient`,
`build_provider` patched per-case to a `MockLLMProvider`. The lab's chat-capable `digest` agent is the
worked example.

**Headline: 6/6 pass. `stream:true` on the OpenAI chat endpoint returns a valid `text/event-stream` of the
completed output; the fail-closed SecurityGate fires before any byte streams (a withheld secret never
streams, an injection input is a 400 JSON not a stream); pre-stream errors stay JSON; governance inherited.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | stream happy path | 200 SSE chunks | `text/event-stream`; role delta, `content="a concise digest of the input"` delta, `finish_reason=stop`, `[DONE]`; all `object=chat.completion.chunk` | ✅ |
| 2 | both modes, one endpoint | JSON vs SSE | omit stream → 200 `application/json` `chat.completion`; `stream:true` → 200 `text/event-stream` | ✅ |
| 3 | output security | 200 SSE content_filter | secret output → 200 SSE, last chunk `finish_reason=content_filter`, no content delta, `AKIA` absent from the stream | ✅ |
| 4 | input security | 400 JSON, not SSE | injection input → 400 `application/json` `content_filter`, payload not echoed | ✅ |
| 5 | unknown model | 404 JSON | `stream:true` + `nope` → 404 `application/json` `model_not_found` | ✅ |
| 6 | governance inherited | `root=True` audit | one `DigestAgent` record, `root=True`, `status=ok` | ✅ |

## Proof points

- **Spec-shaped SSE** (case 1): `stream:true` returns `text/event-stream` — a role-delta chunk, a content
  chunk carrying the agent's output, a `finish_reason=stop` chunk, then `data: [DONE]`. Every chunk is a
  `chat.completion.chunk`. A real OpenAI streaming client parses it unchanged.
- **One endpoint, two modes** (case 2): omitting `stream` still returns the JSON `chat.completion` (the
  non-stream path is unaffected); `stream:true` switches the same endpoint to SSE.
- **Fail-closed security, inherited** (cases 3–4): the output gate runs *before* streaming — a secret in
  the output yields a 200 SSE whose only signal is `finish_reason=content_filter` (no content delta), and
  the secret is **never** present in the stream. The input gate fires *before* the agent runs — an
  injection input is a normal **400 JSON** (`content_filter`), not a half-open SSE 200, with no payload
  echo. This is the "run fully, THEN stream" guarantee: a streamed secret can't be un-sent, so nothing
  streams until the gates have passed.
- **Pre-stream errors stay JSON** (case 5): an unknown model with `stream:true` is a 404 JSON
  `model_not_found` — the client gets a real HTTP status, never a 200 stream that then errors.
- **Governance inherited** (case 6): a streamed run produces one `root=True` audit record — the streaming
  branch reuses the `run_agent` → `BaseAgent.run` chokepoint; the transport adds no gating.

## Findings

No defects. One pre-existing cosmetic note (carried): the chat `model` field uses the agent directory name
(`digest`) while the audit ledger keys the class name (`DigestAgent`) — the governance case queries by
`DigestAgent`. `BaseAgent.name` defaults to `type(self).__name__`.

## §-sign-off checklist

- [x] `stream:true` → 200 `text/event-stream`, spec-shaped `chat.completion.chunk` events + `[DONE]`
- [x] Both modes on one endpoint (JSON when stream omitted; SSE when `stream:true`)
- [x] Output gate inherited: secret → 200 SSE `content_filter`, no content, secret never streams
- [x] Input gate inherited: injection → 400 JSON (not SSE), no payload echo
- [x] Pre-stream error stays JSON (unknown model → 404 JSON)
- [x] Streamed run inherits audit (`root=True`)
- [x] Findings recorded honestly (format-level scope + cross-naming noted)

**Verdict:** SSE streaming validated end-to-end — **6/6** — format-level streaming on `/v1/chat/completions`
with the fail-closed SecurityGate and governance inherited through the streaming path. Phase 4 integration's
streaming slice is confirmed on `main`.
