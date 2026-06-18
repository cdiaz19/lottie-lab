# Round 10 — Phase 4: OpenAI-compatible HTTP transport

> Validate the SHIPPED OpenAI-compatible `/v1/chat/completions` transport (orchestrator
> PR #15, merged to main) from a downstream project — proving any OpenAI client can call a
> Lottie agent over `lottie serve --port`, and that security + governance are inherited, not
> bypassed.

## Goal

Prove, from a downstream project's point of view, that:
- a chat-capable agent (one that declares a `chat:` block) is reachable as an OpenAI "model"
  and returns a spec-shaped `chat.completion`;
- `GET /v1/models` lists only chat-capable agents;
- the error contract is OpenAI-shaped (404 `model_not_found`, 400 `invalid_request_error`);
- the **fail-closed SecurityGate** is inherited — injection input → 400 `content_filter`, a
  secret in the output → 200 `finish_reason=content_filter` with the content withheld, and **no
  payload ever echoed**;
- **audit/policy/cost are inherited** via `AgentService.run_agent` → `BaseAgent.run` with NO
  second gate — a top-level HTTP run is audited with `root=True`.

## What's being tested

Every POST hits `AgentService.run_agent` through the Starlette app built by
`build_openai_app(root)`. The driver opts the lab's `digest` agent into the chat endpoint with a
`chat: {input_field: query, output_field: result}` block in its `config.yaml`; `reviewer` (no
chat block) and `editor` (mesh, no chat block) stay off the endpoint. The driver installs an
in-process Starlette `TestClient` (the same wire contract a real `openai` SDK hits over the
socket — no live uvicorn needed) and patches `build_provider` to a `MockLLMProvider` (API keys
unset).

| # | Case | Checks |
|---|------|--------|
| 1 | `GET /v1/models` | lists only chat-capable agents (digest in; reviewer + editor out) |
| 2 | Happy path | POST → 200 `chat.completion`, content from the agent Output, usage + `lottie` ext, finish_reason `stop` |
| 3 | model_not_found | unknown model AND a non-chat agent both → 404 `model_not_found` |
| 4 | Bad requests | `stream:true` / no user message / missing `model` → 400 `invalid_request_error` |
| 5 | Input security | prompt-injection input → 400 `content_filter`, payload NOT echoed |
| 6 | Output security | secret in output → 200 `finish_reason=content_filter`, empty content, usage present, secret never leaks |
| 7 | Governance inherited | a top-level HTTP run writes a `root=True` audit record |

## Build / verify sequence

```bash
# orchestrator installed editable with the [api] extra; lab venv:
source .venv/bin/activate
uv pip install -e '../lottie-orchestrator[api,serve,mesh,otel]'
python3 rounds/round-10-openai-api/_openai_driver.py   # writes outputs/, prints PASS/FAIL per case
```

## Definition of done — ✅ COMPLETE (7/7)

OpenAI-compat transport validated end-to-end from a downstream project: chat-capable discovery,
spec-shaped completions, the full error contract, the inherited fail-closed SecurityGate (input
400 / output 200 content_filter, no payload echo), and inherited audit (`root=True` on the HTTP
path). **7/7 PASS.**

## Deviations / notes

- Validated **in-process** via the real `build_openai_app` hook with Starlette's `TestClient`
  (httpx under the hood) — no live socket/uvicorn needed; the app and its `run_agent` chokepoint
  are the framework's, the driver asserts the HTTP contract they produce. A real `openai` Python
  SDK pointed at `lottie serve --port` would hit the identical wire shape.
- The driver opts `digest` into the chat endpoint by adding a `chat:` block to its `config.yaml`
  (the documented opt-in mechanism) — a persistent, demonstrative lab change.
- Scope is the OpenAI chat-completions transport. Streaming, multi-turn/conversation memory,
  generic REST (`/v1/agents/{name}/run`), and auth are deferred framework slices (spec §9), out
  of scope here.
- Cosmetic cross-naming (framework note): the chat `model` field uses the agent DIRECTORY name
  (`digest`) while the audit ledger keys on the agent CLASS name (`DigestAgent`) — the driver's
  governance case queries by `DigestAgent`. Pre-existing `BaseAgent.name` behavior, harmless.
