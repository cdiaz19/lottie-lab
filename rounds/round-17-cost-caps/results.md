# Round 17 — Results

**5/5 cases PASS.** Validated locally against orchestrator branch `feat/governance-cost-caps-toctou`
(S3) via the lab's editable install.

| # | Case | Outcome |
|---|------|---------|
| 1 | atomic admission | PASS — held reservation (6) counted → concurrent run refused `BudgetExceeded` |
| 2 | settle frees | PASS — two sequential gated runs both admitted (reservation released on settle) |
| 3 | token cap | PASS — `max_run_tokens=5`, 12 accrued → `TokenCapExceeded` mid-run |
| 4 | legacy cumulative | PASS — `budget_usd=0`, no `max_run_usd` → legacy check blocks |
| 5 | fail-closed | PASS — budget + disabled audit ledger → `BudgetExceeded` (never admits) |

## What this proves downstream

- The reservation is TOCTOU-safe: an in-flight (unsettled) reservation is counted against a
  concurrent run's admission, so N concurrent runs can't all pass the same headroom.
- Reservations are released (settled) after the run records its real cost, so headroom is
  restored for the next run without ever briefly under-counting.
- The per-run token cap bounds a single runaway run independently of the cumulative budget.
- Back-compat holds: a plain `budget_usd` (no `max_run_usd`) keeps the legacy cumulative check.
- Fail-closed: a configured budget with no readable ledger blocks rather than admitting on
  unverifiable spend.

## Notes / limitations (honest)

- The reservation amount is the pessimistic per-run ceiling (`max_run_usd`); actual run cost may
  be lower and is recorded in audit at settle. Overshoot for reserved runs is bounded to 0.
- A process killed mid-run could orphan a reservation row; a TTL sweep (1h) on the next reserve
  reclaims it, so a crash can't permanently shrink a budget.
- Lab CI red on `ORCH_REPO_TOKEN` (known non-bug). Round validated locally.
