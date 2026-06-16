# Round 8 — Governance: Cost Budget Circuit-Breaker

> Validate the SHIPPED per-agent cumulative cost budget (governance slice 3, `lottie-orchestrator @
> feat/governance-cost-budget`, PR #13). Scope: cost budgets only — OpenTelemetry is a later
> governance slice, out of scope here.

## Goal

Prove, from a downstream project, that an agent declaring `budget_usd` is blocked once its prior
recorded spend reaches the budget: the block is **fail-closed**, fires **before `_execute`**, is
audited `status="budget_exceeded"`, is checked **after** the policy gate, and is **backward-compatible**
(no budget → unlimited). Show the circuit breaker engaging dynamically as spend accrues, and the rows
surfaced by `lottie audit`.

## What's being tested

Exercised through the **real shipped path** in-process: `instantiate_agent` (which attaches the cost
gate from `config.budget_usd`) + the real **`DigestAgent`**. Two provider styles: a cost-reporting
`_CostProvider` (`LLMResponse.cost_usd > 0`, so a real run accrues spend into the audit ledger) for the
dynamic accrual case, and pre-seeded audit rows for the deterministic block/fail-closed cases. A
blocked run leaves the provider unconsumed (`llm_calls == 0`), proving `_execute` never ran. The ledger
key is the agent's metrics name (`DigestAgent`).

| # | Case | Expected |
|---|------|----------|
| 1 | No `budget_usd` declared | run succeeds (unlimited, baseline) |
| 2 | Budget set, prior spend below it | run proceeds |
| 3 | Prior spend ≥ budget | `BudgetExceeded`, blocked before `_execute` |
| 4 | Budget set + audit disabled | fail-closed `BudgetExceeded` (spend unverifiable) |
| 5 | No budget + audit disabled | runs (fail-closed scopes to a *configured* budget) |
| 6 | Policy-denied AND over budget | `PolicyDenied` (policy checked first) |
| 7 | Real accrual, budget 0.05, 0.04/run, 3 runs | `[ok, ok, BudgetExceeded]` — crossing run completes, next blocked |
| 8 | Audit integration | `ok` + `budget_exceeded` rows; `lottie audit` renders them |

## Build / verify sequence

```bash
# orchestrator installed editable on feat/governance-cost-budget (the lab venv sees it live)
source .venv/bin/activate
python3 rounds/round-8-cost-budget/_cost_driver.py    # writes outputs/, prints PASS/FAIL
```

## Definition of done — ✅ COMPLETE (8/8)

Budget enforced at the `BaseAgent.run` chokepoint via the real `instantiate_agent` wiring: prior
cumulative `>= budget_usd` → `BudgetExceeded` before `_execute`, audited `budget_exceeded`; fail-closed
when the ledger is disabled; checked after policy; no budget ⇒ unlimited; accrual circuit-breaker
engages; `lottie audit` shows the rows. **8/8 PASS, no findings.**

## Deviations / notes

- Validated **in-process via the real `instantiate_agent`** (the seam both `lottie run` and serve use),
  with a deterministic cost-reporting provider — no real LLM spend. `lottie audit` is exercised as a
  real CLI subprocess (case 8).
- **One-run overshoot (sequential), bounded under concurrency.** Case 7 shows the run that *crosses*
  the budget completes and the *next* is blocked — the post-hoc accrual semantics. The framework spec
  (§2) notes concurrent same-agent runs can overshoot by the number in flight (TOCTOU); this round
  validates the sequential bound only.
- Scope is cost budgets. OpenTelemetry, per-project budgets, per-run token caps, and TOCTOU atomic
  reservation are deferred framework slices, out of scope.
