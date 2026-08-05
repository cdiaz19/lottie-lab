# Round 32 — Memory and session modules (orchestrator V3 S5)

> S5 moved recall, trajectory and session out of `core` into their owning subsystems —
> with the **logic** moving, not just the class. Behaviour must be identical.

| # | Case | Result |
|---|------|--------|
| 1 | recall / trajectory / session resolve to their subsystems | PASS |
| 2 | the chain is 11 modules with distinct orders | PASS |
| 3 | episodic trajectory capture still works | PASS |
| 4 | trajectory is still OFF by default | PASS |
| 5 | **recall still injects as a DATA block** (S2a contract) | PASS |
| 6 | the recall prefix does not leak past the run | PASS |
| 7 | session history accumulates across fresh agents | PASS |
| 8 | **session history is still hash-only** | PASS |
| 9 | a failed run is still recorded as an error | PASS |

**Case 5** is the one that matters most. Recall-as-data is the S2a anti-poisoning
contract: recalled notes reach the model framed as data, never as instructions. Moving
that code between subsystems is exactly where the framing could be lost silently, so the
round asserts the `render_as_data` block is still present in what the provider receives.

**Case 8** re-proves the privacy discipline after the move: session run history records
*that* the session progressed and what it cost, never the content.

## Scope note, carried from the orchestrator PR

The plan listed **reflect** and **verify** in this slice. Neither moved:

- `_maybe_reflect` re-enters the agent's own `complete()` with hand-primed budget state;
  extracting it needs a host Protocol that is `BaseAgent` in all but spelling. It becomes
  a real module once **E4** owns message assembly.
- `_verify` is a `BaseAgent` extension point by design.

Recorded rather than forced.

## Run

```bash
.venv/bin/python rounds/round-32-memory-modules/_modules_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v3-s5-memory-modules`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
