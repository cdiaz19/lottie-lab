# Round 3 — Serve Core + Phase 0 Completion
> Serving core (`AgentService`) · Memory stubs · Security write-gate

## Goal
Verify the code merged into `main` via PR #4 (`feat/serve-core`) and confirm the three
Phase 0 deliverables that were missing from the spec checklist are real in code:
the `AgentService` serving core, the memory stubs (`MemoryClient` / `MockMemoryAgent`),
and the rule-13 security write-gate. Close Phase 0 before opening Round 4 (Phase 1 — Knowledge).

## What's being tested

### 1. Serving core — `AgentService` (transport-agnostic)
- `AgentService.list_agents()` returns one `AgentInfo` per discovered agent (digest + reviewer), import-free.
- `AgentService.run_agent("digest", payload)` runs end-to-end and returns a `RunResult` with latency/tokens/cost.
- Error mapping is clean and typed:
  - unknown agent → `AgentNotFoundError`
  - bad payload → `InvalidInputError`
  - load failure → `AgentLoadError`
  - agent raises → `AgentExecutionError`

### 2. Security gate on serve path
- `SecurityGate.check_input` runs on the raw payload before the agent sees it.
- `SecurityGate.check_output` runs on `output.model_dump_json()` before anything is returned.
- An injection-style payload is gated, not passed through.

### 3. Memory stubs (Phase 0 deliverables, now in spec)
- `BaseAgent` exposes `self.memory` — defaults to `NullMemoryClient`.
- `src/lottie/memory/schema.py` defines all schemas: MemoryTier, MemoryRecord, MemoryQuery, MemoryHit, RecallResult, ReflectionInput, ReflectionResult.
- `MockMemoryAgent` / `MockMemoryClient` usable in agent integration tests with no real store.

### 4. Security write-gate (rule-13)
- `guard_and_write` runs SecretDetection → CodeSecurityScan → mypy → ruff in order.
- On any failure the target dir is removed — no partial/unsafe code survives.

### 5. Regression — Phase 0 still green
- `pytest` full suite passes without API keys (MockLLMProvider).
- Coverage ≥ 80%.

## Build / verify sequence

```bash
# From lottie-orchestrator (installed -e into the lab venv)
pytest src/lottie/serve -v          # serving core + gate
pytest src/lottie/memory -v         # memory stubs
pytest src/lottie/security -v       # write-gate + scanners
pytest -q                           # full regression
pytest --cov=lottie --cov-report=term-missing

# Serving core smoke (Python, transport-agnostic — no CLI yet)
python - <<'PY'
from pathlib import Path
from lottie.serve import AgentService
svc = AgentService(Path("."))
print([a.name for a in svc.list_agents()])
print(svc.run_agent("digest", {"query": "multi-agent AI systems"}))
PY
```

## Inputs
See `inputs/`. Each file is a serve-core payload or a marker for a list/error case.
Record raw results in `outputs/` and the signed-off summary in `results.md`.

## Definition of done
Every box in `results.md` checked, full suite green, coverage ≥ 80%,
serve-core errors map to the right typed exceptions, security gate blocks the injection payload.
Round 3 done = Phase 0 fully closed → open Round 4 (Phase 1 — Knowledge Core).
