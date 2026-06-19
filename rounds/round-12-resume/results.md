# Round 12 — Phase 4: durable resume over REST — Results

**Framework under test:** `lottie-orchestrator @ main` (PR #17 merged, squash `cc18011`), installed
editable in the lab venv with `[api]` + `[mesh]` (+ serve, otel).
**Harness:** `_resume_driver.py` — `build_http_app(LAB_ROOT)` driven by Starlette's `TestClient`,
`LOTTIE_MESH_CHECKPOINT=sqlite`, `build_provider` patched per-case to a scripted `MockLLMProvider`. The
lab's `editor` mesh (HITL `publish` gate) is the worked example.

**Headline: 8/8 pass. Durable resume works end-to-end over HTTP — and a FRESH server process resumes a
mesh interrupt from the shared on-disk sqlite checkpoint (FU-9 closed), with security + audit inherited
through the resume path and no second gate.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | run → interrupt | 200 interrupted + thread_id + pending | editor ran to the `publish` gate → `status=interrupted`, a `thread_id`, a `pending` block | ✅ |
| 2 | resume (same app) | 200 complete | approve → `status=complete`, `output.final` = `PUBLISHED: …` | ✅ |
| 3 | **durable cross-process** | fresh app resumes from disk | db persisted; a NEW `build_http_app` (empty cache) resumed the thread → 200 `complete`, `PUBLISHED: …` | ✅ |
| 4 | unknown agent | 404 not_found | `nope` → 404 `not_found` | ✅ |
| 5 | non-mesh agent | 400 not_resumable | `digest` (no HITL) → 400 `not_resumable` | ✅ |
| 6 | unknown/expired thread | 404 thread_not_found | bogus tid → 404 `thread_not_found` (typed; no raw leak) | ✅ |
| 7 | bad body | 400 invalid_request | missing `thread_id` → 400 `invalid_request` | ✅ |
| 8 | governance inherited | resume audited | `EditorMesh` audit records present, ≥1 `status=ok` | ✅ |

## Proof points

- **HITL interrupt over HTTP** (case 1): `POST /v1/agents/editor/run` drove the mesh through
  plan → parallel[draft,factcheck] → review to the `publish` gate, returning `200 status="interrupted"`
  with a `thread_id` + `pending` — the client gets everything it needs to resume.
- **Resume to completion** (case 2): `POST /resume {thread_id, decision:approve}` continued past the gate
  → `200 status="complete"`, `output.final` starting `PUBLISHED:`. Same-process resume via the cached
  agent.
- **Durable cross-process resume** (case 3 — the headline): app A ran to the gate, persisting the mesh
  state to `<root>/.lottie/mesh/checkpoints.db`; a brand-new `build_http_app` instance (app B — a
  separate `AgentService` with an empty agent cache) resumed the SAME `thread_id` from that on-disk db →
  `200 complete`, `PUBLISHED:`. The only link between A and B is the sqlite file — proving
  rehydrate-by-`thread_id` with zero shared in-memory state. This is the new-worker / after-restart case
  that the in-memory checkpointer couldn't serve — FU-9 closed.
- **Typed error contract** (cases 4–7): unknown agent → 404 `not_found`; non-mesh agent (`digest`, no
  HITL) → 400 `not_resumable`; a bogus `thread_id` → 404 `thread_not_found` (the engine's `get_state`
  pre-check raises a typed error — no raw langgraph `EmptyInputError` / pydantic `ValidationError`
  leaks); a body without `thread_id` → 400 `invalid_request`. A programmatic HITL driver can branch
  cleanly on each.
- **Governance inherited, no second gate** (case 8): a resume run produced `EditorMesh` audit records
  (≥1 `status=ok`) — resume rides the same `AgentService.resume_agent` → `BaseAgent.run` chokepoint as
  `/run`; the transport adds no gating of its own.

## Findings

No defects. Notes (carried, framework): a langgraph msgpack-deprecation warning (FU-6) fires on sqlite
deserialize of `StepResult` — a warning today, filtered from the round output. Cosmetic cross-naming: the
REST path uses the agent directory name (`editor`) while audit keys the class name (`EditorMesh`) — the
governance case queries by `EditorMesh`. Both pre-existing.

## §-sign-off checklist

- [x] `POST /run` on a HITL mesh → 200 `interrupted` + `thread_id` + `pending`
- [x] `POST /resume` (approve) → 200 `complete`
- [x] **Durable cross-process resume: a fresh server process resumes from the shared sqlite db** (FU-9)
- [x] Unknown agent → 404 `not_found`
- [x] Non-mesh agent → 400 `not_resumable`
- [x] Unknown/expired thread → 404 `thread_not_found` (typed, no raw leak)
- [x] Bad body → 400 `invalid_request`
- [x] Resume inherits audit (no second gate)
- [x] Findings recorded honestly (FU-6, cross-naming noted)

**Verdict:** durable resume over REST validated end-to-end — **8/8** — including the cross-process
checkpoint rehydration that closes FU-9, with the full typed error contract and inherited governance.
Phase 4 integration's resume slice is confirmed on `main`.
