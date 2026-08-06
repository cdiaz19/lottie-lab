# Round 34 — Context Compiler (orchestrator E4 S1)

> E4 gave message assembly an **ordering authority**, a **cross-source budget**, and
> **provenance**. The behavioural claim is that nothing changes for existing agents:
> `complete(messages)` keeps its signature and a prompt made only of pinned sources comes
> out byte-identical.

| # | Case | Result |
|---|------|--------|
| 1 | an ordinary agent's prompt is unchanged | PASS |
| 2 | recall is assembled ahead of the agent's messages, **by declared order** | PASS |
| 3 | recall and the agent's messages are both **pinned sources** | PASS |
| 4 | provenance answers *"which source filled the window?"* | PASS |
| 5 | over budget, the **lowest-order droppable** source goes first | PASS |
| 6 | a pinned source is **never** dropped, even far over budget | PASS |
| 7 | dropping stops once under budget, not once it runs out of things to drop | PASS |
| 8 | summarising is preferred over outright dropping | PASS |
| 9 | nothing is summarised when the prompt already fits | PASS |
| 10 | an assembly failure sends the prompt as-is | PASS |
| 11 | **a budget stop during assembly propagates** | PASS |

## Why cases 5–8 use a synthetic source

**Every source the orchestrator ships today is pinned**, so the drop policy is real but not
yet reachable through a shipped agent — compaction still does the shrinking. Exercising the
policy here with a synthetic droppable source is what stops it rotting before knowledge is
wired in as one.

That is a scope limit of E4 S1, recorded in the orchestrator PR rather than implied away.

## Case 3 is the point of the slice

S5a had to pin on `role == "system"`, because role was the only signal available. But a
knowledge block and the recall block are **both system messages**, and only the recall
block is load-bearing — S2a's anti-poisoning contract. Pinning belongs to the **source**,
and this case asserts it now is one.

## Case 11 is the subtle one

Summarisation happens *during* assembly and **spends tokens**. If a cap trip there were
caught by the same handler that tolerates an assembly outage, the run would carry on
spending past its ceiling — the opposite of what the cap is for. Assembly is best-effort
about its own failures, never about the run's budget.

## Run

```bash
.venv/bin/python rounds/round-34-context-compiler/_compiler_driver.py
```

## Result

**11/11 PASS** against orchestrator `v3.0.0` + E4 S1 (`63c5682`).
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
