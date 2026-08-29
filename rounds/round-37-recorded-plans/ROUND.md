# Round 37 — Recorded plans and replay (orchestrator E6 S1)

> A mesh routes **dynamically**: the supervisor decides step N+1 from the result of step N.
> That makes a multi-agent flow non-deterministic, so a mesh test today either hand-mocks
> the router or cannot assert on the path taken at all.

| # | Case | Result |
|---|------|--------|
| 1 | a completed run records its routing decisions | PASS |
| 2 | the plan matches the path actually taken | PASS |
| 3 | **the plan stores a task hash, never the text** | PASS |
| 4 | a plan knows which task it belongs to | PASS |
| 5 | **a replayed run makes ZERO supervisor calls** | PASS |
| 6 | **replaying a changed roster fails loudly** | PASS |
| 7 | **a parallel fan-out records as ONE step** | PASS |
| 8 | sequential steps stay separate | PASS |
| 9 | no plans root means no artefacts | PASS |
| 10 | loading a plan that was never recorded raises | PASS |
| 11 | a traversing thread id cannot escape the directory | PASS |

## Case 5 is the payoff

The replayed run is driven by a mock holding **one canned response that is not a valid
worker name**. If replay ever asked the supervisor, routing would raise
`CapabilityViolation` rather than pass quietly. Reaching the end of the flow proves the
routing cost nothing.

That is what turns a non-deterministic mesh into something you can put a regression test
around, and what lets you debug a failure without paying for routing again.

## Cases 7 and 8 cover a bug this slice already had

The first implementation inferred the plan from `MeshState.history`, grouping by
`StepResult.step` — the index that repeats across a parallel fan-out. It looked cheaper and
was **wrong**: only `LangGraphEngine` populates `step` (it needs it for deterministic
branch merge). `LocalEngine` leaves it at 0, so every sequential step collapsed into one
phantom fan-out.

Replaced with a recorder that wraps the `RouteFn` and captures decisions as they are made
— exact by construction and identical across engines, which is also why no engine had to
change. Case 7 pins the fan-out shape and case 8 the sequential one.

## Cases 3 and 11 are the familiar disciplines

A plan lives on disk, so it stores a **hash** of the task rather than its text — the same
rule that keeps raw content out of the audit ledger. Thread ids and agent names arrive from
CLI arguments and are validated before any path join, since `Path(base) / "../../etc"`
silently escapes. That is the third time this guard has earned its place: distill drafts
(PR #35), sessions (S5b), and now plans.

## Run

```bash
.venv/bin/python rounds/round-37-recorded-plans/_plan_driver.py
```

## Result

**11/11 PASS** against orchestrator `feat/e6-recorded-plan`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
