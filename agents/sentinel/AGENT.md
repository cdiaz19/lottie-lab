# SentinelAgent

Downstream fixture for orchestrator **S6** (agentic-loop hygiene). Makes two LLM completions per
run — so `max_turns` bounds it — and overrides `_verify` to reject outputs containing `BAD`
(a fail-closed post-condition check before the output leaves the agent).

| | Model | Field |
|---|---|---|
| Input | `SentinelAgentInput` | `query: str` |
| Output | `SentinelAgentOutput` | `result: str` |
