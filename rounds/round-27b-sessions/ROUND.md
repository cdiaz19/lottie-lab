# Round 27b — Session artifacts and resumable runs (orchestrator V2 S5b)

> S5b claims a task can survive **beyond one process**. The only honest way to check that
> is to build a fresh agent *and* a fresh store on every step — never reusing the in-memory
> object — so nothing but the file on disk carries state forward. That is what this driver
> does.

| # | Case | Result |
|---|------|--------|
| 1 | a run without a session leaves no artifact | PASS |
| 2 | a session run persists to `.lottie/sessions/` | PASS |
| 3 | **a fresh agent+store resumes and advances** | PASS — step=2 |
| 4 | run history accumulates across processes | PASS — runs=2 |
| 5 | separate sessions do not interfere | PASS |
| 6 | **progress written before a crash survives the crash** | PASS |
| 7 | **run history is hash-only** | PASS |
| 8 | a traversing session id cannot escape the directory | PASS |
| 9 | injected progress is rejected by the write screen | PASS |

## The three that matter

**Case 6 — why progress is written per call.** The driver builds an agent whose `_execute`
saves progress and then raises. If progress were flushed once at the end, everything that
run achieved would be lost. It isn't: `reached=halfway` survives, and the run is recorded
with `status=error`.

**Case 7 — privacy.** Run history follows the audit ledger's discipline: it records *that*
the session progressed and what it cost, never the content. The driver runs a query
containing `SENSITIVE_QUERY_TEXT` and asserts it does not appear in the recorded run.

**Case 9 — the round-trip vector.** Progress is read back into a *future* run. An agent
storing raw model output would otherwise have a way to smuggle instructions across a
process boundary, which is exactly what the memory write gateway exists to prevent. Progress
is screened on write for the same reason, and nothing reaches disk when it trips.

## Run

```bash
.venv/bin/python rounds/round-27b-sessions/_session_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v2-s5b-sessions`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## S5 complete

R27a (compaction) + R27b (sessions) together cover V2 slice S5. Next is **S6** — release,
full regression, and the `v2.0.0` tag.
