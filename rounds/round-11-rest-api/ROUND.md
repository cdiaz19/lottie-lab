# Round 11 — Phase 4: generic REST transport

> Validate the SHIPPED Lottie-native REST transport (orchestrator PR #16, merged to main) from a
> downstream project — `GET /v1/agents`, `GET /v1/agents/{name}`, `POST /v1/agents/{name}/run` — proving
> any agent is callable by its real typed Input over `lottie serve --port`, that both HTTP surfaces
> (OpenAI + REST) compose onto one app, and that security + governance are inherited, not bypassed.

## Goal

Prove, from a downstream project's point of view, that:
- `GET /v1/agents` lists EVERY agent (not just the chat-capable ones) with its provider;
- `GET /v1/agents/{name}` returns the agent's Input JSON schema;
- `POST /v1/agents/{name}/run` takes the agent's raw typed Input JSON and returns the serialized
  `RunResult` (output + metrics + run status);
- the error contract is REST-native (404 `not_found`, 400 `invalid_request`);
- the **fail-closed SecurityGate** is inherited — injection input → 400 `content_filter`, a secret in
  the output → 200 `status="withheld"` with the body stripped, **no payload ever echoed**;
- **one `lottie serve --port` app serves BOTH** the OpenAI surface (`/v1/models`, chat-capable only)
  and the REST surface (`/v1/agents`, all agents);
- **audit/policy/cost are inherited** via `AgentService.run_agent` → `BaseAgent.run` with NO second
  gate — a top-level REST run is audited with `root=True`.

## What's being tested

Every POST hits `AgentService.run_agent` through the Starlette app built by `build_http_app(root)` —
the SAME app `lottie serve --port` serves, composing `openai_routes` + `rest_routes` over one
`AgentService`. The driver installs an in-process Starlette `TestClient` (the wire contract a real HTTP
client hits over the socket — no live uvicorn needed) and patches `build_provider` to a
`MockLLMProvider` (API keys unset). The lab's `digest` agent (Input `{query}`, Output `{result}`) is the
worked example; `reviewer` and the `editor` mesh are also exposed over REST.

| # | Case | Checks |
|---|------|--------|
| 1 | `GET /v1/agents` | lists ALL agents (digest + reviewer + editor) with provider |
| 2 | `GET /v1/agents/{name}` | returns the Input JSON schema (digest → `query`) |
| 3 | `POST .../run` happy path | typed Input → 200 serialized `RunResult` (output + metrics + status) |
| 4 | run errors | unknown → 404 `not_found`; bad Input → 400 `invalid_request`; non-object body → 400 |
| 5 | input security | injection → 400 `content_filter`, payload NOT echoed |
| 6 | output security | secret → 200 `status="withheld"`, output `{}`, usage kept, secret never leaks |
| 7 | composition | one app serves `/v1/models` (chat-capable) AND `/v1/agents` (all) |
| 8 | governance inherited | a top-level REST run writes a `root=True` audit record |

## Build / verify sequence

```bash
# orchestrator installed editable with the [api] extra; lab venv:
source .venv/bin/activate
uv pip install -e '../lottie-orchestrator[api,serve,mesh,otel]'
python3 rounds/round-11-rest-api/_rest_driver.py   # writes outputs/, prints PASS/FAIL per case
```

## Definition of done — ✅ COMPLETE (8/8)

Generic REST transport validated end-to-end from a downstream project: all-agent discovery, Input-schema
introspection, typed-Input runs returning the full RunResult, the REST error contract, the inherited
fail-closed SecurityGate (input 400 / output 200 withheld, no payload echo), the OpenAI+REST composition
on one app, and inherited audit (`root=True` on the REST path). **8/8 PASS.**

## Deviations / notes

- Validated **in-process** via the real `build_http_app` hook with Starlette's `TestClient` — no live
  socket/uvicorn needed; the app + its `run_agent` chokepoint are the framework's, the driver asserts the
  HTTP contract they produce.
- Scope is the generic REST transport + its composition with the OpenAI surface. Resume
  (`POST /v1/agents/{name}/resume`), streaming, and auth are deferred framework slices (spec §1) — out
  of scope. The `run` response structurally surfaces a mesh interrupt (`status`/`thread_id`/`pending`);
  exercising a live mesh interrupt over REST is left to a resume-focused round.
- Cosmetic cross-naming (framework note, carried): the REST path uses the agent DIRECTORY name
  (`digest`) while the audit ledger keys on the agent CLASS name (`DigestAgent`) — the governance case
  queries by `DigestAgent`. Pre-existing `BaseAgent.name` behavior, harmless.
