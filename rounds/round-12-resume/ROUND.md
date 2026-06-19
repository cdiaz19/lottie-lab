# Round 12 — Phase 4: durable resume over REST

> Validate the SHIPPED `POST /v1/agents/{name}/resume` endpoint + durable sqlite checkpointing
> (orchestrator PR #17, merged to main — closes FU-9) from a downstream project: a mesh HITL
> interrupt can be resumed over HTTP, and the checkpoint survives across a fresh server process.

## Goal

Prove, from a downstream project's point of view, that:
- a mesh `POST /run` that hits a HITL gate returns `200 status="interrupted"` + `thread_id` + `pending`;
- `POST /v1/agents/{name}/resume {thread_id, decision}` continues it → `200 status="complete"`;
- **durability (the headline):** a FRESH server process (new `build_http_app`, empty agent cache)
  resumes the same `thread_id` from the shared on-disk sqlite db — not just the process that ran it;
- the typed error contract holds: unknown agent → 404 `not_found`; non-mesh agent → 400 `not_resumable`;
  unknown/expired thread → 404 `thread_not_found` (no raw langgraph/pydantic leak); bad body → 400;
- governance is inherited on the resume path (audit fires; no second gate).

## What's being tested

The lab's `editor` mesh (EditorMesh: `plan → parallel[draft,factcheck] → review → publish(HITL gate)`)
is the worked example. The driver runs the real combined HTTP app (`build_http_app(LAB_ROOT)` — the same
app `lottie serve --port` serves) via Starlette's `TestClient`, with `LOTTIE_MESH_CHECKPOINT=sqlite` (what
`lottie serve --port` sets) so the engine persists state to `<cwd>/.lottie/mesh/checkpoints.db`. The
supervisor is driven by a scripted `MockLLMProvider` (workers are deterministic stubs; API keys unset).

| # | Case | Checks |
|---|------|--------|
| 1 | run → interrupt | `POST /run` → 200 `interrupted` + `thread_id` + `pending` (the publish gate) |
| 2 | resume (same app) | `POST /resume` approve → 200 `complete`, `final` = `PUBLISHED: …` |
| 3 | **durable cross-process** | a FRESH app (empty cache) resumes the checkpoint from disk → 200 `complete` |
| 4 | unknown agent | → 404 `not_found` |
| 5 | non-mesh agent (digest) | → 400 `not_resumable` |
| 6 | unknown/expired thread | → 404 `thread_not_found` (typed; no raw leak) |
| 7 | bad body (no thread_id) | → 400 `invalid_request` |
| 8 | governance inherited | a resume run is audited (`EditorMesh` record, no second gate) |

## Build / verify sequence

```bash
# orchestrator installed editable with [api] + [mesh]; lab venv:
source .venv/bin/activate
uv pip install -e '../lottie-orchestrator[api,serve,mesh,otel]'
python3 rounds/round-12-resume/_resume_driver.py   # writes outputs/, prints PASS/FAIL per case
```

## Definition of done — ✅ COMPLETE (8/8)

Durable resume over REST validated end-to-end from a downstream project: HITL interrupt surfaced,
resume-to-completion, the full typed error contract, governance inherited — and the headline, a FRESH
server process resuming a checkpoint written by another via the shared on-disk sqlite db (FU-9 closed).
**8/8 PASS.**

## Deviations / notes

- Validated **in-process** via the real `build_http_app` hook with Starlette's `TestClient` — no live
  uvicorn needed. Case 3 builds two SEPARATE `build_http_app` instances (distinct `AgentService`s, empty
  caches); the only link is the sqlite checkpoint on disk — a faithful new-worker/after-restart
  simulation. Case 3's "process B" supervisor only needs to FINISH after the (deterministic) publish
  worker runs on resume, so its mock script is just `["FINISH", …]`; the mesh STATE comes entirely from
  the on-disk checkpoint, which is the point.
- `EditorMesh` builds `LangGraphEngine(interrupt_before=...)` with no explicit checkpoint/root, so the
  backend is env-selected (`LOTTIE_MESH_CHECKPOINT=sqlite`) and the db path is cwd-derived (cwd = project
  root under `lottie serve`). No agent-author change was needed to gain durability.
- Scope is the resume transport + durability. Streaming, applying `edited_input` on approve, and
  distributed multi-host resume are deferred framework slices (spec §1), out of scope.
- Residual (framework, carried): a langgraph msgpack-deprecation warning fires on sqlite deserialize of
  `StepResult` (FU-6) — a warning today; the round filters it from output. Cosmetic cross-naming: the
  REST path uses the agent directory name (`editor`) while the audit ledger keys the class name
  (`EditorMesh`) — pre-existing `BaseAgent.name` behavior.
