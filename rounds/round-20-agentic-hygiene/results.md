# Round 20 — Results

**4/4 cases PASS.** Validated locally against orchestrator branch `feat/agentic-hygiene` (S6).

| # | Case | Outcome |
|---|------|---------|
| 1 | max_turns cap | PASS — `TurnLimitExceeded` on the completion past the cap |
| 2 | under cap | PASS — completes under a generous cap |
| 3 | verify rejects | PASS — `_verify` raises on banned output → run fails |
| 4 | verify passes | PASS — clean output returned |

## What this proves downstream
- `max_turns` bounds a runaway agent by LLM-completion count (complements S3's token cap).
- A downstream agent can add a fail-closed post-condition by overriding `_verify` — the bad
  output never leaves the agent.
- Both are opt-in (config / method override), defaults off/generous. Lab CI red on
  ORCH_REPO_TOKEN (known non-bug).
