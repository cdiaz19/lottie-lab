# Round 6 — Multi-agent Mesh (Phase 2 + 3)
> Supervisor→workers routing · LangGraph parallel fan-out · HITL interrupt/resume · checkpoint time-travel · capability enforcement

## Goal
Verify Lottie's mesh stack — supervisor→workers routing, LangGraph parallel fan-out, HITL
interrupt/resume, and checkpoint time-travel — from an independent lab project on **Mock providers
(API keys unset)**, and sign off the Round-6 checklist (§7) so the rounds↔phases mapping is synced
with Phase 2 (mesh engine) and Phase 3 (mesh hardening).

## What's being tested
1. **Routing** (A) — `SupervisorRouter` dispatches a task to the correct worker agent based on role; `LocalEngine` sequential fallback path.
2. **Parallel fan-out** (B) — `LangGraphEngine` runs independent worker steps in parallel; fan-out correctness and result merging verified.
3. **HITL interrupt/resume** (C) — mesh interrupts on a configured step, surfaces a `PendingApproval`; `mesh resume` (in-process) applies the edited input and continues to completion.
4. **Time-travel / history** (D) — `mesh history` CLI surfaces the Phase-3 checkpoint surface; cold-CLI behaviour (in-memory checkpointer returns an informative notice, exit 0) verified.
5. **Capability enforcement** (E) — `CapabilityEnforcerSkill` blocks a worker from calling a skill not in its `capabilities` list; mesh-level enforcement tested alongside agent-level.
6. **Full gate** (F) — `pytest -q`, `mypy --strict`, and `ruff` all clean across framework mesh code and the lab `editor` agent.

## Build / verify sequence

```bash
# Install the framework with the [mesh] extra into the lab venv (cwd = lab).
pip install -e '../lottie-orchestrator[mesh]'

# Framework mesh suite (cwd = lottie-orchestrator).
( cd ../lottie-orchestrator && pytest -q src/lottie/mesh )

# Lab editor-agent tests on MockLLMProvider (cwd = lab).
pytest agents/editor -v

# CLI input cases: registry + inspect + mesh-history surface (3 cases → outputs/).
bash rounds/round-6-mesh/run-inputs.sh

# In-process mesh driver: routing / parallel / HITL / time-travel happy paths.
# NOTE: _mesh_driver.py is created in a later task.
python3 rounds/round-6-mesh/_mesh_driver.py

# Type-check the editor agent.
mypy --strict agents/editor

# Lint the editor agent and round directory.
ruff check agents/editor rounds/round-6-mesh
```

## Inputs
See `inputs/`. Each `input-*.json` carries `_case`, `argv`, and `_expect_contains` checks driven by
`run-inputs.sh`. The three CLI cases prove the registry and inspection surface, and exercise the
Phase-3 `mesh history` CLI:

| File | Case | What it proves |
|---|---|---|
| `input-01-list.json` | `lottie list agents` | `editor` mesh is registered alongside `digest`/`reviewer`. |
| `input-02-inspect.json` | `lottie inspect agent editor` | Typed `EditorInput` (`task`/`max_steps`) surfaces via the inspect command. |
| `input-03-history.json` | `lottie mesh history --agent editor --thread-id t1` | Cold-CLI with the in-memory checkpointer prints an informative notice and exits 0. |

These cases do **not** run the mesh end-to-end — the CLI's `build_provider` always returns a real
`LiteLLMProvider`, so happy-path routing/parallel/HITL execution is proven in-process by
`_mesh_driver.py` (see later task).

Raw results land in `outputs/`; the signed-off summary will be `results.md`.

## Definition of done
- Every box in `results.md` §7 checked.
- Framework mesh suite green under `[mesh]` extra.
- `agents/editor` tests green on `MockLLMProvider`.
- Parallel fan-out, HITL interrupt/resume, and time-travel proven by the in-process `_mesh_driver.py`.
- `mypy --strict agents/editor` and `ruff check agents/editor rounds/round-6-mesh` clean.
- README rounds↔phases table corrected to reflect Phase 2 (mesh engine) and Phase 3 (mesh hardening) mapping to Round 6.

## Deviations from plan
1. **CLI cannot script the supervisor.** `build_provider` always returns a `LiteLLMProvider` — a scripted `MockLLMProvider` cannot be injected via the CLI. Happy-path mesh execution (routing, parallel fan-out, HITL, time-travel) is proven in-process by `_mesh_driver.py`, not via `lottie run`.
2. **`lottie benchmark agent editor` skipped.** A HITL mesh returns `status: interrupted` rather than a clean final output, so it is not a meaningful eval target for the benchmark harness.
3. **Cross-process `mesh resume` deferred.** `lottie mesh resume` across CLI processes requires the sqlite checkpointer (framework follow-up FU-9). The in-memory checkpointer is process-local; the in-process driver covers resume within a single process.
