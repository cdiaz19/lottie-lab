# Round 35 — Reflection as a module (orchestrator E4 S2)

> Reflection left `BaseAgent` and became a module in the memory subsystem. Behaviour must
> be identical: opt-in, success-only, budget-respecting, and never able to fail an
> already-successful run.

| # | Case | Result |
|---|------|--------|
| 1 | reflect is owned by the memory subsystem | PASS |
| 2 | still OFF by default | PASS |
| 3 | enabled, a successful run writes a SEMANTIC lesson | PASS |
| 4 | **skipped when the run's token cap is already reached** | PASS |
| 5 | a **failed** run is never reflected on | PASS |
| 6 | a reflector failure never fails an already-successful run | PASS |
| 7 | the lesson lands in SEMANTIC, not EPISODIC | PASS |
| 8 | the module constructs from callables alone, no agent | PASS |

## Case 4 is the load-bearing one

Reflection **spends tokens**. Skip-when-exhausted is what keeps learning from becoming the
thing that overspends a run's budget.

Worth recording how the case was written: it first used `max_run_tokens=1` and **failed** —
but that was a wrong premise, not a regression. `MockLLMProvider` reports zero usage, so a
run's spend never climbs and a cap of 1 is never reached. The cap is now `0`, meaning *this
run has no token budget at all* — a real configuration that triggers the guard genuinely
end-to-end.

## Case 8 is the point of the slice

V3 S5 recorded that reflection could not move because it re-entered the agent's own
`complete()`, and predicted E4's Context Compiler would unblock it. **That turned out to be
wrong.** What it actually needed was a narrow `BudgetedCaller` Protocol — *"an LLM call that
counts against this run's budget"* — and nothing about message assembly. This case asserts
the module now constructs from plain callables with no `BaseAgent` anywhere.

## Case 7

Tier follows **origin**: a reflection lesson is a SEMANTIC note, a trajectory is an EPISODIC
event. Neither module has to know the tier taxonomy.

## Run

```bash
.venv/bin/python rounds/round-35-reflect-module/_reflect_driver.py
```

## Result

**8/8 PASS** against orchestrator `feat/e4-s2-reflect-module`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
