# Round 25a — Episodic trajectory persistence (orchestrator V2 S3a)

> Validate the SHIPPED post-run episodic write-back from a downstream project, against a
> **real `SqliteMemoryClient` on disk** — not the mock — so durability is actually exercised.

## Why this round exists

Before S3a **nothing wrote EPISODIC records**. `MemoryAgent._execute` read them,
`_apply_add` hardcoded `tier=SEMANTIC`, and `RunTrajectory` was built in-memory inside
`_maybe_reflect` then discarded. Two consequences: S3b distillation had no corpus to select
trajectories from, and `lottie reflect` was a **latent no-op** — it consolidated an
always-empty tier.

Case 4 is the direct proof that gap is closed.

## What's being tested

`instantiate_agent(DigestAgent, config=...)` reads `memory.trajectory` and attaches the
post-run hook. Episodic records are read back through a **fresh** `SqliteMemoryClient` over
the same file, standing in for a separate process.

| # | Case | Checks |
|---|------|--------|
| 1 | OFF by default | no `trajectory:` block → run writes no episodic record |
| 2 | durable persistence | 3 runs → 3 episodic records, readable by a fresh client |
| 3 | failures recorded | blank query → `ValueError`, record has `success:false` + the error |
| 4 | reflect has input | `MemoryAgent` consolidates 2 runs → semantic notes (was structurally 0) |
| 5 | no prompt leakage | recall injects the semantic note only; no raw `"task"` in the block |
| 6 | write gate holds | injection-like query → rejected fail-closed, nothing stored |

Cases 5 and 6 are the security-relevant ones. Trajectories store **raw task text**, so the
round proves (5) that raw text is confined to the EPISODIC tier which recall never reads,
and (6) that the `MemoryContentGate` still screens every write regardless of tier.

## Run

```bash
.venv/bin/python rounds/round-25a-trajectory/_trajectory_driver.py
```

## Result

**6/6 PASS.** Validated locally against the orchestrator `feat/v2-s3a-trajectory-persistence`
branch (lab venv is an editable install pointing at the orchestrator working copy).
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

```
PASS  1. trajectory off by default writes no episodic record — episodic=0
PASS  2. 3 runs persist 3 episodic records, readable by a fresh client — episodic=3
PASS  3. failed run recorded with success=false and its error — episodic=1
PASS  4. MemoryAgent consolidates the runs (was structurally 0 before S3a) — consolidated=2, semantic=1
PASS  5. recall injects semantic notes only — no raw trajectory in the prompt — prefix_len=253
PASS  6. injection-like trajectory rejected by the write gate, not stored — episodic=0
```

## Outstanding lab debt

Rounds **R22 (S0 store), R23 (S1 gateway red-team), R24 (S2 reflection)** were never built —
those slices merged without lab validation. R23 in particular is the memory-poisoning
red-team round the V2 epic lists as mandatory for the v2.0.0 DoD. Tracked as debt to be
cleared before the release slice.
