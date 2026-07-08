# Round 20 — Agentic hygiene: max_turns + _verify hook (orchestrator S6)

> Validate the SHIPPED agentic-loop rails (v1 epic slice S6): a per-run LLM-completion cap and an
> optional `_verify` post-condition hook, from a downstream project.

## What's being tested
`instantiate_agent(SentinelAgent, config=...)` — SentinelAgent makes 2 completions/run and
overrides `_verify` to reject outputs containing "BAD".

| # | Case | Checks |
|---|------|--------|
| 1 | max_turns cap | `max_turns=1`, 2 completions → `TurnLimitExceeded` on the 2nd |
| 2 | under cap | `max_turns=5` → run completes |
| 3 | verify rejects | output contains "BAD" → `_verify` raises, run fails fail-closed |
| 4 | verify passes | clean output → run succeeds |

## Run
```bash
uv run python rounds/round-20-agentic-hygiene/_agentic_hygiene_driver.py
```

## Result
**4/4 PASS.** Lab CI red on `ORCH_REPO_TOKEN` (known non-bug); validated locally against S6.
