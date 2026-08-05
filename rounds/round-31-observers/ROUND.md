# Round 31 — Observers as subscribers (orchestrator V3 S4)

> S4 took auditing out of the middleware chain and made it an `EventBus` subscriber. The
> claim is that **best-effort stops being a convention** each observer must remember and
> becomes a property of the bus.

| # | Case | Result |
|---|------|--------|
| 1 | audit is no longer a middleware | PASS |
| 2 | a successful run is still audited, still `root=True` | PASS |
| 3 | the record still carries hash, **provider**, and timing | PASS |
| 4 | a failed run is audited `status=error` | PASS |
| 5 | a completed stream is audited with no output hash | PASS |
| 6 | **a CANCELLED stream is audited as partial, never as ok** | PASS |
| 7 | a denied run keeps its governance-specific status | PASS |
| 8 | **a sabotaging observer cannot fail the run** | PASS |
| 9 | `AuditSubscriber` constructs from a logger alone | PASS |

## This round found a regression

**Case 3 failed on the first run: `provider=None`.** S4 added `provider` to the event
models so the subscriber could read it off the event, but nothing ever *populated* it —
every audit record had silently lost the model id it used to carry.

Fixed upstream: `Pipeline` now takes the provider and stamps it on the context, so both
the streaming and non-streaming paths emit it.

## Case 6 is the other one worth reading

A stream cancelled by the transport must be audited **partial**, not `ok`. S4's first
implementation caught `Exception` — but `GeneratorExit` is a `BaseException`, so a
cancelled stream fell through to the `finally` and emitted `RunCompleted`. A cancelled
request would have looked clean in the ledger.

That one was caught by a **pre-existing orchestrator test**, not by this round. Together
the two are a decent illustration: the unit suite caught the semantic break, the lab round
caught the data loss, and neither would have caught both.

## Case 8 is the point of the slice

A subscriber that raises on every event. The run completes, returns its real result, and
the audit record still lands. Under the old middleware arrangement that observer sat *in
the execution path*.

## Run

```bash
.venv/bin/python rounds/round-31-observers/_observers_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v3-s4-observers`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
