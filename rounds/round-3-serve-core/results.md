# Round 3 — Results: Serve Core + Phase 0 Completion

**Verified against:** `lottie-orchestrator` @ `9acb48b` (Merge PR #4 `feat/serve-core` → main)
**Date:** 2026-06-08 · **venv:** `lottie-orchestrator/.venv` (py 3.12.13, pytest 9.0.3)
**Raw data:** `outputs/raw-results.json`, `outputs/test-summary.txt`

---

## 1. Serving core — `AgentService`

- [x] `list_agents()` returns one `AgentInfo` per discovered agent → `["digest", "reviewer"]`, import-free (`test_list_agents_does_not_import_user_code`).
- [x] `run_agent("digest", {"query": ...})` → `RunResult` end-to-end.
      Live: `latency_ms=8437.3`, `input_tokens=38`, `output_tokens=392`, `cost_usd=0.005994`, `output={"result": <1408 chars>}`.
- [x] Error mapping, typed and clean:
  - [x] unknown agent → `AgentNotFoundError` (live)
  - [x] bad payload (`{}`, missing `query`) → `InvalidInputError` (live)
  - [x] agent raises (empty `query`) → `AgentExecutionError` (live)
  - [x] load failure → `AgentLoadError` (suite: `test_run_agent_bad_config_raises_load_error`, `test_run_agent_broken_schema_raises_load_error`)

> Note: `RunResult` exposes `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd` —
> not a single `tokens` field. Spec wording "latency/tokens/cost" maps to those four.

## 2. Security gate on serve path

- [x] `check_input` runs on the raw payload **before** the agent (chokepoint wired).
- [x] `check_output` runs on `output.model_dump_json()` **before** return.
- [x] Order verified: `_SpyGate.calls == ["in", "out"]` (`test_run_agent_gate_called_input_then_output`).
- [⚠] "Injection payload is gated, not passed through" — **only with a blocking gate injected.**
      The **default** `SecurityGate` is an **identity gate** (`serve/security.py`): it returns
      input/output unchanged (`test_check_input_is_identity`, `test_check_output_is_identity`).
      So out-of-the-box the injection payload **passes through** to the agent.
      Architecture is correct (single chokepoint, constructor-injectable); real scanning is a
      Phase-1 swap-in. Demonstrated with a `BlockingGate` subclass → injection raised
      `InvalidInputError` before the agent ran. **Real blocking is not yet active on `main`.**

## 3. Memory stubs

- [x] `BaseAgent` exposes `self.memory`, defaults to `NullMemoryClient`
      (`core/base_agent.py:43` → `self.memory = memory or NullMemoryClient()`).
- [x] `memory/schema.py` defines all 7: MemoryTier, MemoryRecord, MemoryQuery, MemoryHit,
      RecallResult, ReflectionInput, ReflectionResult.
- [x] `MockMemoryClient` (`memory/mock.py`) + `MockMemoryAgent` (`memory/agent.py`) — no real store.
      18/18 memory tests green.

## 4. Security write-gate (rule-13)

- [x] `guard_and_write` runs SecretDetection → CodeSecurityScan → SchemaValidator(mypy + ruff) in order.
- [x] On any failure `shutil.rmtree(target, ignore_errors=True)` — target dir removed, no partial code survives
      (`test_secret_aborts_and_rolls_back`, `test_type_error_aborts_and_rolls_back`).

## 5. Regression — Phase 0 green

- [x] `pytest -q` full suite: **224 passed** (~71s), no API keys (MockLLMProvider).
- [x] Coverage **99%** (≥ 80% gate). serve/security modules 93–100%.

| Suite | Result |
|---|---|
| `pytest src/lottie/serve -v`    | 15 passed |
| `pytest src/lottie/memory -v`   | 18 passed |
| `pytest src/lottie/security -v` | 17 passed |
| `pytest -q` (full)              | 224 passed |
| coverage (`--cov=lottie`)       | 99% |

---

## Sign-off

Serve core, memory stubs, and write-gate are **real in code and green**. Error mapping
maps to all four typed exceptions. Full suite passes at 99% coverage.

**One caveat on the Definition of Done:** "security gate blocks the injection payload" is
satisfied *by architecture* (chokepoint + injectable gate) and *demonstrated* with a blocking
subclass, but the **default gate on `main` is identity and does not block** — real input/output
scanning is a Phase-1 deliverable. If the DoD requires active blocking on the default path,
that box is **not** met yet; if it requires the chokepoint to exist and be wired, it is met.

**Recommendation:** Phase 0 closes on the structural goals. Carry "wire a real scanning
SecurityGate into the default serve path" into Round 4 / Phase 1 (Knowledge Core) as the
first security task, so the default path blocks injection rather than passing it through.
