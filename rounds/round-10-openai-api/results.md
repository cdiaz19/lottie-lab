# Round 10 — Phase 4: OpenAI-compatible HTTP transport — Results

**Framework under test:** `lottie-orchestrator @ main` (PR #15 merged, squash `e6ee5c6`), installed
editable in the lab venv with the `[api]` (+ `serve`, `mesh`, `otel`) extras.
**Harness:** `_openai_driver.py` — `build_openai_app(LAB_ROOT)` driven by Starlette's `TestClient`;
`build_provider` patched to a `MockLLMProvider` (API keys unset). The lab's `digest` agent is opted
into the chat endpoint via a `chat:` block; `reviewer` + `editor` are not.

**Headline: 7/7 pass. The OpenAI-compatible transport works end-to-end from a downstream client, and
the fail-closed SecurityGate + audit/policy/cost are inherited through the HTTP path — no second gate.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | `GET /v1/models` | only chat-capable agents | `data` ids = `[digest]`; reviewer + editor absent; each `object=model`, `owned_by=lottie` | ✅ |
| 2 | Happy path | 200 `chat.completion` | `id=chatcmpl-…`, `model=digest`, content = agent Output `result`, `finish_reason=stop`, `usage` + `lottie` ext present | ✅ |
| 3 | model_not_found | unknown + non-chat → 404 | `nope`→404/`model_not_found`; `reviewer`→404/`model_not_found` | ✅ |
| 4 | Bad requests | 400 invalid_request | `stream:true`→400 invalid_request_error; no-user→400; missing `model`→400 | ✅ |
| 5 | Input security | 400 content_filter, no echo | injection input → 400, code `content_filter`, message did NOT contain the payload | ✅ |
| 6 | Output security | 200 content_filter, withheld | secret output → 200, `finish_reason=content_filter`, `content=""`, `usage` present, `AKIA` absent from body | ✅ |
| 7 | Governance inherited | `root=True` audit on HTTP | one `DigestAgent` record, `root=True`, `status=ok` | ✅ |

## Proof points

- **Opt-in discovery** (case 1): only agents that declare a `chat:` block appear as OpenAI models.
  `digest` (with the block) is listed; `reviewer` and the `editor` mesh (no block) are not — the
  endpoint is honestly scoped to what's chat-capable.
- **Spec-shaped completion** (case 2): the response is a real `chat.completion` — `id` prefixed
  `chatcmpl-`, one `choices[0].message{role:assistant, content}`, `usage` token counts, plus the
  non-standard `lottie` metrics extension (latency/cost/status) that OpenAI clients ignore.
- **OpenAI error contract** (cases 3–4): unknown/non-chat models → 404 `model_not_found`; malformed,
  streaming, and no-user-message requests → 400 `invalid_request_error`. A client's error handling
  works unchanged.
- **Fail-closed security, inherited** (cases 5–6): the input gate rejects prompt-injection → 400
  `content_filter` with **no payload in the message**; the output gate withholds a secret → 200 with
  `finish_reason=content_filter` and **empty content**, the secret never present in the response body.
  `usage` is still reported on the withheld run (metrics carried on `OutputSecurityViolation`).
- **Governance inherited, no second gate** (case 7): a top-level HTTP run produces exactly one audit
  record with `root=True` — `anyio.to_thread.run_sync` copies the audit-depth ContextVar into the
  worker thread (the same propagation property Round 9 verified for OTel spans), so the HTTP run is
  correctly top-level. Security + policy + cost ride the same `AgentService.run_agent` →
  `BaseAgent.run` chokepoint; the transport adds no gating of its own.

## Findings

No defects. One pre-existing cosmetic note (carried, not a bug): the chat `model` field is the agent
DIRECTORY name (`digest`) while the audit ledger keys on the agent CLASS name (`DigestAgent`) — the
governance case queries by `DigestAgent`. `BaseAgent.name` defaults to `type(self).__name__`; nothing
on the HTTP path needs the two namespaces to join. A future model→audit correlation tool would want a
stable mapping; noted for the framework backlog.

## §-sign-off checklist

- [x] `GET /v1/models` lists only chat-capable agents
- [x] `POST /v1/chat/completions` returns a spec-shaped `chat.completion` (usage + `lottie` ext)
- [x] OpenAI error contract: 404 `model_not_found`, 400 `invalid_request_error`
- [x] Input gate inherited: injection → 400 `content_filter`, no payload echo
- [x] Output gate inherited: secret → 200 `content_filter`, content withheld, secret never leaks
- [x] Audit inherited: top-level HTTP run is `root=True` (no second gate)
- [x] Findings recorded honestly (cosmetic cross-naming noted)

**Verdict:** OpenAI-compatible transport validated end-to-end — **7/7** — security + governance
inherited through the HTTP path. Phase 4 integration's OpenAI-compat slice is confirmed on `main`.
