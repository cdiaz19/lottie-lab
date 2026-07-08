# Round 21 — V1 full regression smoke (orchestrator v1.0.0)

> The downstream sign-off for `v1.0.0`: re-run every v1 slice's round driver (R15–R20) against
> the merged orchestrator `main` and confirm the whole hardened surface still works together.

## What's being tested
`_v1_regression.py` imports and runs each round driver's `main()` in a clean cwd (resetting env
toggles between rounds), aggregating pass/fail.

| Round | Slice | Surface |
|---|---|---|
| 15 | S1 | rule-11 capability enforcement |
| 16 | S2 | BaseAgent/CLI security gate |
| 17 | S3 | cost caps + TOCTOU reservation |
| 18 | S4 | HTTP auth + rate limit + pagination |
| 19 | S5 | HITL edited_input |
| 20 | S6 | agentic hygiene (max_turns + _verify) |

## Run
```bash
uv run python rounds/round-21-v1-regression/_v1_regression.py
```

## Result
**6/6 v1 rounds PASS** (28 underlying cases). Lab CI red on `ORCH_REPO_TOKEN` (known non-bug);
validated locally against orchestrator `v1.0.0`.
