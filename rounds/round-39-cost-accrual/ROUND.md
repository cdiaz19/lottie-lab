# Round 39 — cost accrual reaches the ledger

**Target:** `lottie-orchestrator` @ `fix/cost-accrual-lost`
**Kind:** regression — a governance control that had gone silently dead

## Why this round exists

Not a planned slice. Found during a routine full-lab regression sweep while closing V3
debt: **round 8 case 07 had gone from PASS to FAIL.** Three $0.04 runs against a $0.05
budget all succeeded, and the ledger reported `final_spend=$0.0000`.

Round 8 was recorded 8/8 in the v1 era. Nothing in the 1,596-test unit suite noticed.

## The bug

Two usage accumulators, one of them orphaned.

| | |
|---|---|
| `Pipeline` | builds the run's accumulator up front via `usage_factory`, keeps the object, reads it back when it emits `RunCompleted`. |
| `InstrumentedRunnable.run` | started a **second** `RunContext` and published *that* as `_active_ctx` — which is what every `complete()` call accrues into. |

The object the pipeline reported from was never written to. Since **V3 S4** moved auditing
off the middleware chain and onto the event bus, the audit row is built from that event, so
every row recorded a free run:

```
lottie audit
│ 2026-09-… │ DigestA… │ ok │ Y │ 0/0 │ 0.000000 │   ← before
│ 2026-09-… │ DigestA… │ ok │ Y │ 10/20 │ 0.010000 │ ← after
```

`budget_usd` sums that ledger. **The cumulative cost circuit-breaker could never fire.**

## Why it stayed hidden

Per-run caps (`max_run_usd`, `max_run_tokens`) and `max_turns` read `_active_ctx`
*directly*, so they kept working — the per-run half of cost governance was fine, and it is
the half most tests exercise. `last_metrics` reads its own `ctx` in `_record`, so agent
benchmarks were correct too. Only the **cross-run ledger** was zeroed, and only an
end-to-end accrual test over three sequential runs shows that.

Blast radius beyond the breaker: `lottie audit`'s cost column, cost trend reporting, and —
since E7 — every third-party telemetry plugin subscribed to the bus.

## The fix

`run` **adopts** a context the caller already published instead of replacing it:

```python
ctx = self._active_ctx or RunContext()
```

`BaseAgent` publishes the pipeline's accumulator through `_new_usage()`, and clears it in
`run`'s `finally` so a gate aborting ahead of `_execute` cannot leave it dangling.

## Cases

| # | Case | Result |
|---|---|---|
| 1 | the audit row carries the run's real cost, not zero | PASS |
| 2 | the audit row carries the run's real token counts | PASS |
| 3 | the ledger agrees with the agent's own metrics | PASS |
| 4 | `total_cost` accumulates across runs | PASS |
| 5 | the cumulative budget breaker refuses the run after the budget is crossed | PASS |
| 6 | the blocked run never spent a token — the gate is fail-closed | PASS |
| 7 | `lottie audit` renders the real cost to an operator | PASS |
| 8 | a plugin subscriber sees the real cost on `RunCompleted` | PASS |
| 9 | the usage accumulator is cleared even when a gate aborts the run | PASS |
| 10 | a genuinely free run still records $0.00 | PASS |

**10/10.** Against the unfixed orchestrator the same driver scores **0/10** — case 3 states
the defect outright: `ledger=0.0 metrics=0.04`.

## Findings

- **F39-1 (high, fixed).** The cumulative `budget_usd` circuit-breaker was inert from V3 S4
  onward: the audit ledger it sums recorded $0.00 for every run. A per-agent spend cap that
  silently never engages is worse than none, because an operator believes it is protecting
  them.
- **F39-2 (process).** Unit tests asserted `last_metrics` — the accumulator that stayed
  correct — and never the ledger. A regression suite covering an end-to-end invariant only
  through one of its two producers proves nothing about the other. Twelve unit tests now
  assert the ledger path directly (`test_cost_accrual.py`), and they fail 10/12 without the
  fix.
- **F39-3 (process).** Round 8 dated from v1 and was not in any V3 regression set. This
  round was found by widening a sweep to **every** round rather than the epic's own. Full-lab
  regression is now the standing rule, not per-epic regression.
