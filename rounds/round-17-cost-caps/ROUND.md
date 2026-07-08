# Round 17 — Per-run token cap + TOCTOU-safe atomic cost reservation (orchestrator S3)

> Validate the SHIPPED cost-governance hardening (v1 epic slice S3): a per-run token cap and an
> atomic budget reservation that closes the check-then-act race in the cost gate.

## Goal

Before S3 the cost gate blocked on prior *committed* spend (concurrent runs could all slip past
the same headroom) and had no per-run cap. Prove downstream that:

- an in-flight **reservation is counted**, so a concurrent run over budget is refused (TOCTOU
  closed);
- **settle frees headroom** for the next run;
- a **per-run token cap** (`max_run_tokens`) aborts a runaway run mid-flight;
- the **legacy** cumulative budget (`budget_usd`, no `max_run_usd`) still blocks;
- a budget with a **disabled ledger** fails closed (never admits).

## What's being tested

The driver runs `instantiate_agent(DigestAgent, config=…)` per case in a temp project root with
audit ENABLED (the reservation ledger must be live), using a usage-reporting provider so the
token cap has real tokens to count.

| # | Case | Checks |
|---|------|--------|
| 1 | atomic admission | budget 10, `max_run_usd` 6; one reservation held → a concurrent run (6) refused (6+6>10) |
| 2 | settle frees | sequential gated runs both admitted (reservation released between) |
| 3 | token cap | `max_run_tokens` 5, run accrues 12 → `TokenCapExceeded` mid-run |
| 4 | legacy cumulative | `budget_usd` 0, no `max_run_usd` → legacy check blocks (spent 0 ≥ 0) |
| 5 | fail-closed | budget set + audit disabled → `reserve()` fails closed |

## Run

```bash
uv run python rounds/round-17-cost-caps/_cost_caps_driver.py
```

## Result

**5/5 PASS.** See `results.md` and `outputs/`. Lab CI red on `ORCH_REPO_TOKEN` (known non-bug);
validated locally against the S3 branch.
