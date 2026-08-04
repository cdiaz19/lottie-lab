# Round 29b — Streaming chain (orchestrator V3 S2b)

> S2b put `run_stream` on the **same middleware instances** `run()` uses, removing the
> last hand-sequenced execution path. The interesting property here is **temporal**.

## Why this round is about timing

The plain `Middleware` contract is `pre; try: return nxt(ctx); finally: post`. When `nxt`
hands back a **generator object**, that `finally` fires the moment the generator is
*created* — before a single delta exists. The cost reservation would settle and the
capability gate would reset while the stream was still producing.

`ScopedMiddleware` + `ExitStack` fixes it: a `with` block spans consumption. Cases 4–7 are
the ones that would catch a regression back to the broken behaviour.

| # | Case | Result |
|---|------|--------|
| 1 | the streaming chain is exactly policy, cost, audit, depth, capability | PASS |
| 2 | verify / security_output / reflect absent (a stream has no Output) | PASS |
| 3 | deltas reach the caller unchanged | PASS |
| 4 | **an unconsumed generator runs no gates and produces no deltas** | PASS |
| 5 | **audit fires after the last delta, never at generator creation** | PASS |
| 6 | **the rule-11 gate is live for the whole stream** | PASS |
| 7 | **closing early still unwinds every scope** | PASS |
| 8 | a denied stream raises before any delta | PASS |
| 9 | the non-streaming path still works alongside it | PASS |

**Case 5** is the direct regression guard: it takes one delta, asserts the audit ledger is
still empty mid-stream, drains, then asserts exactly one record. Under the old contract the
record would already exist after `next()`.

**Case 7** matters because the slice-3b transport cancels a stream by **closing the
generator**. The reservation must still settle and the depth counter must still be
restored, or a cancelled request would leak budget.

**Case 2** is a deliberate absence, not a gap: `verify`, `check_output` and `reflect` need
an output *value*, which `__exit__` never receives. They were absent from `run_stream`
before the swap-in too — the output gate wraps the deltas at the serve boundary instead.

## Run

```bash
.venv/bin/python rounds/round-29b-stream-chain/_stream_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v3-s2b-stream-chain`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## V3 S2 complete

R29 (`run()`) + R29b (`run_stream`) together close the swap-in. Both execution paths now
run one chain; `_pre_run_gates` is deleted. Next is **S3** — the fail-closed modules take
ownership of their middleware.
