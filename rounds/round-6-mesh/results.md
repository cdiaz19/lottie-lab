# Round 6 — Results: Multi-agent Mesh (Phase 2 + 3)

**Code under test:** `lottie-orchestrator` `main` @ `feat/phase3-mesh-hardening` (Phase 2 + 3 merged)
**Date:** 2026-06-13 · **venv:** `lottie-lab/.venv` (py 3.12.13, pytest 9.0.3) · **providers:** Mock (API keys UNSET)
**Raw data:** `outputs/` (input-*.out, driver output)

> Run from `lottie-orchestrator` (installed `-e '[mesh]'` into the lab venv).
> Framework mesh suite uses the `[mesh]` extra (LangGraph). Lab editor tests use MockLLMProvider.
> In-process driver (`_mesh_driver.py`) proves routing / parallel / HITL / time-travel end-to-end.

---

## 1. Sub-phase results

| Group | What | Result |
|-------|------|--------|
| A — Routing | Supervisor picks declared workers; `LocalEngine` sequential fallback | ✅ **PASS** (driver + editor tests) |
| B — Parallel fan-out | `draft` + `factcheck` run in parallel; merged with `plan` first in history | ✅ **PASS** (driver history · `test_parallel_branch_runs_both_workers`) |
| C — HITL interrupt/resume | Mesh pauses before `publish`; approve → status `complete` | ✅ **PASS** (driver · `test_run_pauses_before_publish` · `test_resume_approve_completes_and_publishes`) |
| D — Time-travel | Checkpoint history: 10 checkpoints in history | ✅ **PASS** (driver) |
| E — Capability enforcement | Undeclared worker refused at runtime | ✅ **PASS** (`test_undeclared_worker_is_refused`) |
| F — Full gate | 39 framework mesh + 6 editor + 17 lab suite · `mypy --strict` + `ruff` clean | ✅ **PASS** |

---

## 2. Test counts

| Suite | Command | Count |
|-------|---------|-------|
| Framework mesh suite | `pytest -q src/lottie/mesh` (cwd=orchestrator, `[mesh]` extra) | **39 passed** |
| Lab editor tests | `pytest agents/editor` | **6 passed** (5 integration · 1 contract) |
| Lab full suite | `pytest -q` | **17 passed** |
| CLI input cases | `bash rounds/round-6-mesh/run-inputs.sh` | **3/3 PASS** (input-01-list · input-02-inspect · input-03-history) |

---

## 3. In-process driver (`_mesh_driver.py`)

| Checkpoint | Expected | Actual |
|------------|----------|--------|
| Run status | `interrupted` | `interrupted` |
| History workers | `['plan', 'draft', 'factcheck', 'review']` (both parallel branches, plan first) | `['plan', 'draft', 'factcheck', 'review']` |
| Pending worker | `publish` | `publish` |
| Resume status | `complete` | `complete` |
| Final output | starts with `PUBLISHED:` | `PUBLISHED: ship the launch post` |
| Checkpoint count (time-travel) | > 0 | **10 checkpoints** |

**RESULT: PASS**

---

## 4. Gates

| Gate | Command | Result |
|------|---------|--------|
| Types | `mypy --strict agents/editor rounds/round-6-mesh/_mesh_driver.py` | ✅ **clean (7 source files)** |
| Lint | `ruff check agents/editor rounds/round-6-mesh` | ✅ **clean** |

---

## 5. Constraints honored

- ✅ **API keys unset** — MockLLMProvider throughout; supervisor is the sole LLM consumer.
- ✅ **No vendor SDK imported directly** — all LLM calls go through `LLMProvider` abstraction.
- ✅ **Typed I/O** — `EditorInput`, `EditorOutput`, `StepResult`, `MeshState` are Pydantic v2 models; `mypy --strict` clean.
- ✅ **Capability enforcement** — `CapabilityEnforcerSkill` blocks undeclared workers (group E).
- ✅ **Per-run `thread_id`** — Phase-3 FU fix: unique thread IDs prevent cross-run checkpoint contamination.
- ✅ **Parallel branches present and merged in plan-first order** — both `draft` and `factcheck` in history.

---

## 6. Known issues / deviations

1. **CLI cannot script the supervisor.** `build_provider` always returns `LiteLLMProvider` — a `MockLLMProvider` cannot be injected via the CLI. Happy-path mesh execution (routing, parallel fan-out, HITL, time-travel) is proven in-process via `_mesh_driver.py`, not via `lottie run`.
2. **`lottie benchmark agent editor` skipped.** A HITL mesh returns `status: interrupted` rather than a clean final output, making it unsuitable as a benchmark eval target in its current form.
3. **Cross-process `mesh resume` deferred.** `lottie mesh resume` across CLI processes requires the sqlite checkpointer (framework follow-up FU-9). The in-memory checkpointer is process-local; the in-process driver covers resume within a single process.
4. **LangGraph msgpack deprecation warnings (FU-6).** The driver emitted: `Deserializing unregistered type lottie.mesh.schema.StepResult` / `MeshState` "will be blocked in a future version". This is the orchestrator's already-tracked Phase-3 follow-up FU-6 (register `MeshState`/`StepResult` with LangGraph's `allowed_msgpack_modules`). Non-blocking for this round.

---

## 7. Sign-off checklist

- [x] **A.** Supervisor routing — declared workers dispatched correctly
- [x] **B.** Parallel fan-out — `draft` + `factcheck` run in parallel, merged plan-first in history
- [x] **C.** HITL interrupt/resume — pause before `publish`, approve → status `complete`
- [x] **D.** Time-travel — 10 checkpoints in history
- [x] **E.** Capability enforcement — undeclared worker refused at runtime
- [x] **F.** Full gate — 39 framework mesh + 6 editor + 17 lab suite · `mypy --strict` + `ruff` clean
- [x] Framework mesh suite green under `[mesh]` extra (39 passed)
- [x] Editor tests green on MockLLMProvider (6 passed)
- [x] Parallel fan-out merged in plan-first order (`['plan', 'draft', 'factcheck', 'review']`)
- [x] Interrupt → resume reaches `complete`
- [x] `history()` > 0 (10 checkpoints)
- [x] Undeclared worker refused by `CapabilityEnforcerSkill`
- [x] `mypy --strict` clean (7 source files)
- [x] `ruff` clean
- [x] README rounds↔phases table synced (Round 5 = Phase 4, Round 6 = Phase 2 + 3)
- [x] `LOTTIE.md` updated (EditorMesh added to Agents list)

**Boxes: 16 / 16.** No ❌.
**Round 6: SIGNED OFF** → Phase 2 + 3 mesh stack verified; open Round 7 — Governance (audit trail, policy engine, OpenTelemetry).
