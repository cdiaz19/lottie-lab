# Round 8 — Governance: Cost Budget — Results

**Framework under test:** `lottie-orchestrator @ feat/governance-cost-budget` (PR #13), installed
editable in the lab venv.
**Harness:** `_cost_driver.py` — real `instantiate_agent` + real `DigestAgent`; a cost-reporting
`_CostProvider` for dynamic accrual, pre-seeded audit rows for deterministic blocks. A blocked run
leaves `provider.calls == 0`, proving `_execute` never ran. Ledger key = `DigestAgent` (metrics name).

**Headline: 8/8 cases pass, no findings. The cost circuit-breaker is enforced end-to-end, fail-closed,
policy-after, and backward-compatible.**

## Test matrix

| # | Case | Expected | Observed | LLM calls | Audit status | Result |
|---|------|----------|----------|-----------|--------------|--------|
| 1 | No budget declared | unlimited | `ok` | 1 | `ok` | ✅ |
| 2 | Prior spend < budget | runs | `ok` | 1 | `ok` | ✅ |
| 3 | Prior spend ≥ budget | `BudgetExceeded` before `_execute` | `BudgetExceeded` | **0** | `budget_exceeded` | ✅ |
| 4 | Budget + audit disabled | fail-closed `BudgetExceeded` | `BudgetExceeded` | **0** | (audit off) | ✅ |
| 5 | No budget + audit disabled | runs (scope check) | `ok` | 1 | (audit off) | ✅ |
| 6 | Policy-denied AND over budget | `PolicyDenied` (policy first) | `PolicyDenied` | 0 | `denied` | ✅ |
| 7 | Accrual: budget 0.05, 0.04/run ×3 | `[ok, ok, BudgetExceeded]` | `[ok, ok, BudgetExceeded]`, final spend $0.0800 | — | — | ✅ |
| 8 | `lottie audit` renders rows | `ok` + `budget_exceeded` shown | both statuses present, exit 0 | — | — | ✅ |

## Proof points

- **Blocked before `_execute`** (cases 3, 4, 6): every blocked run reports `llm_calls=0`.
  `DigestAgent._execute` is the only caller of `self.complete`; zero completions ⇒ the cost gate blocks
  at the chokepoint, before the agent runs (and before any spend is incurred).
- **Fail-closed, scoped to a configured budget** (cases 4 vs 5): a *configured* budget with the audit
  ledger disabled blocks (`BudgetExceeded` — spend unverifiable); a *budget-free* agent with audit
  disabled runs normally. The fail-closed property never affects an unbudgeted agent.
- **Policy before budget** (case 6): an agent both capability-denied and over budget surfaces
  `PolicyDenied` (audited `denied`), not `BudgetExceeded` — policy is the cheaper no-I/O check and wins.
- **Circuit breaker, post-hoc accrual** (case 7): budget $0.05, $0.04/run. Run 1 (prior $0.00) and run 2
  (prior $0.04) both proceed; run 2 *crosses* the budget (final spend $0.08); run 3 (prior $0.08 ≥
  $0.05) is blocked. One-run overshoot under sequential execution, as specified.
- **Backward-compatible** (cases 1, 5): no `budget_usd` ⇒ unlimited; existing agents are unaffected.
- **Audit integration** (case 8): `ok` and `budget_exceeded` rows land in `.lottie/audit.db` and render
  through the real `lottie audit` CLI (exit 0), cost column populated.

## Findings

None. The cost-budget slice passed clean on first run (contrast Round 7, which caught FG-1 in the
policy slice). The framework's own unit + integration tests (`test_cost.py`, `test_base_agent_cost.py`,
`test_instantiate_cost.py`) already cover these paths; this round confirms them end-to-end from a
downstream consumer, including the dynamic accrual the unit tests seed rather than accrue.

## §7 Sign-off checklist

- [x] `budget_usd` declared ⇒ cost gate attached via the real `instantiate_agent` path
- [x] Prior spend ≥ budget ⇒ `BudgetExceeded`, blocked before `_execute` (`llm_calls=0`)
- [x] Block audited `status="budget_exceeded"`; normal run `status="ok"`
- [x] Fail-closed: configured budget + disabled/unverifiable ledger ⇒ block
- [x] Fail-closed scopes to a *configured* budget (no budget + audit off ⇒ runs)
- [x] Policy checked before budget (both-fire ⇒ `PolicyDenied`)
- [x] Circuit breaker engages on real accrual; one-run overshoot (sequential) as specified
- [x] No `budget_usd` ⇒ unlimited (backward-compatible)
- [x] `lottie audit` renders `budget_exceeded` rows (exit 0)
- [x] Findings recorded honestly (none this round)

**Verdict:** cost-budget circuit-breaker validated end-to-end — **8/8**. No orchestrator PR merged by
this round; PR #13 awaits review. OpenTelemetry (next governance slice) and per-project budgets remain
out of scope.
