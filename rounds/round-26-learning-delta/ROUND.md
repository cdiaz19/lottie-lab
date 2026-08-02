# Round 26 — Learning-delta eval loop (orchestrator V2 S4)

> S4 exists to answer *"does learning actually help?"* with **evidence**. A benchmark that
> can only ever say "yes" is worthless, so this round checks the report is honest — and it
> caught itself being dishonest on the first run.

## The hollow pass, and the guard that now prevents it

The first version of this round reported **8/8 green while every single eval case was
failing**. `mock/sim` is not a real litellm provider, so each case died on a
`BadRequestError`, both arms scored `accuracy = 0.0`, and the verdict came back "neutral"
— from two equally-broken runs rather than from a real comparison.

**Case 0 now asserts `success_rate == 1.0` in both arms before anything else is checked.**
A round that measures nothing can no longer report success.

## Cases

| # | Case | Result |
|---|------|--------|
| 0 | **the eval suite actually ran (no provider errors)** | PASS — `success_rate=1.0` both arms |
| 1 | empty store reports 0 recalled notes | PASS |
| 2 | both arms ran the same suite | PASS — 3 cases each |
| 3 | seven metrics, each tagged `higher_is_better` | PASS |
| 4 | **benchmarking writes no memory** | PASS — before=0, after=0 |
| 5 | a populated store is reflected in the note count | PASS — 4 notes |
| 6 | state-dependent metrics reproducible run-to-run | PASS |
| 7 | machine-readable report on disk | PASS |
| 8 | the verdict can report **regression**, not just success | PASS |

### Why case 4 is load-bearing

If benchmarking mutated the corpus it measures — persisting trajectories, writing lessons —
every subsequent run would report different numbers and the report could not gate anything.
S4 disables all memory writes in **both** arms, and this case proves it.

### Why case 1 matters

A `neutral` verdict over an **empty** store means the experiment never ran. That is a
completely different finding from *learning did not help*, and without the note count the
two are indistinguishable in the report.

## Honest limitation

A mock provider returns canned responses, so recall cannot change output quality — the
verdict here is legitimately `neutral`. This round validates the **machinery and the honesty
of the report**, not a real quality gain. Measuring actual improvement requires a live model
and belongs to the eval tier (real-LLM), per the epic.

## Run

```bash
.venv/bin/python rounds/round-26-learning-delta/_learning_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v2-s4-learning-delta`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
