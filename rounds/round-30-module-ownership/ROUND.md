# Round 30 — Module ownership (orchestrator V3 S3)

> S3 moved the **fail-closed** modules — security (rules 8/9), policy, cost, capability
> (rule 11) — out of `core` and into their owning subsystems, constructed from their gate
> alone. Behaviour must be identical; what changes is **who owns the code**.

| # | Case | Result |
|---|------|--------|
| 1 | security / policy / cost / capability resolve to their subsystems | PASS |
| 2 | the chain is still 12 modules with distinct orders | PASS |
| 3 | the migrated modules construct from a gate alone, no agent | PASS |
| 4 | **rule 8** — the input gate still refuses fail-closed | PASS |
| 5 | **rule 9** — the output gate still withholds fail-closed | PASS |
| 6 | policy still denies AND still audits the block `root=True` | PASS |
| 7 | budget still blocks AND still audits `budget_exceeded` | PASS |
| 8 | **rule 11** still blocks an undeclared skill call | PASS |
| 9 | an ordinary run is unchanged | PASS |
| 10 | the streaming chain still mounts the migrated modules | PASS |

## What "ownership" actually bought

**Case 1** asserts each module's `__module__` is its owning subsystem, so a regression
back into `core` fails loudly rather than drifting silently.

**Case 3** is the point of the slice: the migrated modules take a **gate**, not an agent.
Policy and Cost audit their own blocks through an injected callback rather than reaching
back into `BaseAgent` for `_write_block`. That is the coupling that had to go before the
module orchestrator (S6) can do the wiring.

**Cases 4–8** are the reason this needed a round at all. Moving security code is exactly
where a silent regression would be most expensive, so every fail-closed guarantee is
re-proven end-to-end: input refused, output withheld, policy denied *and audited*, budget
exceeded *and audited*, and an undeclared skill call blocked inside `_execute`.

## Run

```bash
.venv/bin/python rounds/round-30-module-ownership/_ownership_driver.py
```

## Result

**10/10 PASS** against orchestrator `feat/v3-s3-module-ownership`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## Honest progress note

`base_agent.py` still imports `governance`, `llm` and `memory` — it holds the gate fields,
`_write_audit`, and the memory hooks. Those edges close in **S4** (audit → subscriber) and
**S5** (recall / reflect / verify). S3 owns only the fail-closed set; the epic metric
(6 subsystem imports → 1) is reached progressively, not here.
