# Round 27a — Context compaction (orchestrator V2 S5a)

> Compaction sits in the **hot path of every completion**, so this round checks the three
> things that would matter most if it were wrong.

## What's being tested

| # | Case | Result |
|---|------|--------|
| 1 | `harness.compaction` config reaches the agent via `instantiate_agent` | PASS |
| 2 | OFF by default | PASS |
| 3 | **a short context is not compacted** — no wasted LLM call | PASS — 1 call |
| 4 | a long context becomes summary + recent turns | PASS — 12 → 3 |
| 5 | the most recent turns survive verbatim | PASS |
| 6 | **the recall-as-data block survives** (S2a contract) | PASS |
| 7 | **a summariser failure sends the FULL context**, never fails the run | PASS |
| 8 | **a token-cap trip propagates** — compaction does not keep spending | PASS |
| 9 | a normal agent run still works with compaction enabled | PASS |

## The three that matter

**Case 3 — cost.** Compaction runs on every completion. If it fired when it wasn't needed
it would double the LLM calls of every short run. The cheap `estimate_tokens` guard runs
before any summarisation, and this case pins that exactly one provider call was made.

**Case 6 — security.** Recall-as-data is the S2a anti-poisoning contract: recalled memory
reaches the model framed as data, never as instructions. If compaction summarised that
block away, the guarantee would disappear with no signal at all. `BaseAgent` pins system
messages precisely so this cannot happen.

**Cases 7 and 8 — the failure modes are opposites, deliberately.** A summariser outage
degrades to sending the full prompt, because the provider's own context error is a clearer
diagnosis than a summariser failure disguised as a task failure. But a `TokenCapExceeded`
propagates: a budget stop is the *run's* decision, and compaction has no business
converting it into a warning and continuing to spend.

## Run

```bash
.venv/bin/python rounds/round-27a-compaction/_compaction_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v2-s5a-compaction`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## Not covered here

`SessionStore`, progress hooks, and `lottie run --session` are orchestrator slice **S5b**
and get round **R27b**.
