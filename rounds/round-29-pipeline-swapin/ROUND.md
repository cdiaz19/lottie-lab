# Round 29 — Pipeline swap-in (orchestrator V3 S2a)

> S2a rewired `BaseAgent.run` from a hand-sequenced list of twelve cross-cutting steps
> into **one line** over a middleware chain. The claim is **behaviour preservation**, so
> this round drives a real lab agent through the real `instantiate_agent` path and checks
> the governance guarantees a downstream project actually depends on.

| # | Case | Result |
|---|------|--------|
| 1 | an ordinary agent run is unchanged | PASS |
| 2 | all 12 standard middleware mount with distinct orders | PASS |
| 3 | the run is still audited, still flagged `root` | PASS |
| 4 | a failed run is still audited `status=error` | PASS |
| 5 | **a denied run is audited `status=denied` AND `root=True`** | PASS |
| 6 | the rule-11 gate is active during `_execute` | PASS |
| 7 | **the gate is already released during `_verify`** | PASS |
| 8 | rule 11 still blocks an undeclared skill call | PASS |
| 9 | the `_verify` post-condition still fails a run closed | PASS |

## The three that justify the order table

S2a's analysis identified three orderings where a wrong position changes security or
audit semantics **silently**. Cases 5, 7 and 8 are those, checked end-to-end:

**Case 5 — why `DEPTH` sits above `COST`.** `_write_block` reads `_depth() == 0` to decide
the audit `root` flag. If the depth middleware ran before the gates, a denied *top-level*
run would be recorded `root=False` — the ledger would quietly misattribute it as a nested
worker. The round asserts a policy-denied run is still `status=denied, root=True`.

**Case 7 — why `CAPABILITY` is the innermost middleware.** `_active_capabilities` is reset
*before* `_verify` today. `_verify` is user code that may call a skill, so leaving the gate
active there would change rule-11 enforcement inside it. The round asserts the gate is
active during `_execute` (case 6) and already released during `_verify` (case 7) — the two
halves of that window.

**Case 8 — rule 11 itself.** An agent declaring `retrieval` that calls an undeclared skill
inside `_execute` is still blocked fail-closed.

## Run

```bash
.venv/bin/python rounds/round-29-pipeline-swapin/_swapin_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v3-s2-pipeline-swapin`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## Scope

`run_stream` still uses the old inline path, so the duplicated execution path is **not**
yet removed. Streaming has genuinely different semantics — no output gate, no `_verify`,
no reflect, `output=None` for audit — and folding it in is orchestrator slice **S2b**,
which gets round **R29b**.
