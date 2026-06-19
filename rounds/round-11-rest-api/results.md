# Round 11 — Phase 4: generic REST transport — Results

**Framework under test:** `lottie-orchestrator @ main` (PR #16 merged, squash `6ac2c9c`), installed
editable in the lab venv with the `[api]` (+ `serve`, `mesh`, `otel`) extras.
**Harness:** `_rest_driver.py` — `build_http_app(LAB_ROOT)` (the combined OpenAI + REST app `lottie serve
--port` serves) driven by Starlette's `TestClient`; `build_provider` patched to a `MockLLMProvider` (API
keys unset).

**Headline: 8/8 pass. The Lottie-native REST surface works end-to-end from a downstream client, composes
with the OpenAI surface on one app, and inherits the fail-closed SecurityGate + audit/policy/cost through
the HTTP path — no second gate.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | `GET /v1/agents` | every agent + provider | `agents` names = `[digest, editor, reviewer]`, each with a `provider` | ✅ |
| 2 | `GET /v1/agents/{name}` | Input JSON schema | `digest` → `input_schema.properties` includes `query` | ✅ |
| 3 | `POST .../run` happy path | 200 serialized RunResult | `agent=digest`, `output={"result": ...}`, `status=complete`, tokens + `cost_usd` present | ✅ |
| 4 | run errors | 404 / 400 / 400 | `nope`→404 `not_found`; `{wrong}`→400 `invalid_request`; array body→400 | ✅ |
| 5 | input security | 400 content_filter, no echo | injection → 400, type `content_filter`, payload absent from message | ✅ |
| 6 | output security | 200 withheld | secret → 200, `status=withheld`, `output={}`, usage present, `AKIA` absent from body | ✅ |
| 7 | composition | one app, both surfaces | `/v1/models` ids = `[digest]`; `/v1/agents` names ⊋ that (all agents) | ✅ |
| 8 | governance inherited | `root=True` audit on REST | one `DigestAgent` record, `root=True`, `status=ok` | ✅ |

## Proof points

- **All-agent discovery** (case 1): `GET /v1/agents` lists `digest`, `reviewer`, AND the `editor` mesh —
  REST exposes every agent by its real typed Input, in contrast to `/v1/models` which lists only agents
  that opt in via a `chat:` block.
- **Input-schema introspection** (case 2): a client can `GET /v1/agents/{name}` to learn the exact payload
  shape (`DigestAgentInput` → a `query` string) before POSTing to `/run`.
- **Typed run → RunResult** (case 3): the request body IS the agent's typed Input; the response is the full
  serialized `RunResult` — output, run status, latency, tokens, cost — not an OpenAI envelope.
- **REST error contract** (case 4): unknown agent → 404 `not_found`; an Input that fails validation or a
  non-object body → 400 `invalid_request`. Native, predictable shapes.
- **Fail-closed security, inherited** (cases 5–6): the input gate rejects prompt-injection → 400
  `content_filter` with **no payload in the message**; the output gate withholds a secret → 200 with
  `status="withheld"` and **`output={}`**, the secret never present in the body, while `usage` is still
  reported (metrics carried on `OutputSecurityViolation`).
- **One app, both surfaces** (case 7): `build_http_app` serves `/v1/models` (OpenAI, chat-capable only)
  and `/v1/agents` (REST, all agents) over a single `AgentService` — the REST agent set is a strict
  superset of the OpenAI model set.
- **Governance inherited, no second gate** (case 8): a top-level REST run produces exactly one audit record
  with `root=True` — `anyio.to_thread.run_sync` copies the audit-depth ContextVar into the worker thread
  (the property Rounds 9–10 verified), so the REST run is correctly top-level. Security + policy + cost ride
  the same `run_agent` → `BaseAgent.run` chokepoint; the transport adds no gating of its own.

## Findings

No defects. One pre-existing cosmetic note (carried): the REST path uses the agent DIRECTORY name
(`digest`) while the audit ledger keys on the agent CLASS name (`DigestAgent`) — the governance case queries
by `DigestAgent`. `BaseAgent.name` defaults to `type(self).__name__`; nothing on the HTTP path needs the two
namespaces to join. Noted for the framework backlog (a model→audit correlation tool would want a stable
mapping).

## §-sign-off checklist

- [x] `GET /v1/agents` lists every agent with provider
- [x] `GET /v1/agents/{name}` returns the Input JSON schema
- [x] `POST /v1/agents/{name}/run` → serialized `RunResult` from a typed Input
- [x] REST error contract: 404 `not_found`, 400 `invalid_request`
- [x] Input gate inherited: injection → 400 `content_filter`, no payload echo
- [x] Output gate inherited: secret → 200 `withheld`, output stripped, secret never leaks
- [x] One app serves both OpenAI + REST surfaces (composition)
- [x] Audit inherited: top-level REST run is `root=True` (no second gate)
- [x] Findings recorded honestly (cosmetic cross-naming noted)

**Verdict:** generic REST transport validated end-to-end — **8/8** — composed with the OpenAI surface on
one `lottie serve --port` app, security + governance inherited through the HTTP path. Phase 4 integration's
REST slice is confirmed on `main`.
