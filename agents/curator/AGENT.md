# CuratorAgent

Downstream fixture agent for validating orchestrator **rule 11** (per-skill-call
capability enforcement, S1 of the v1 hardening epic).

## What it does

`_execute` calls `SummarizerSkill` (capability name `summarizer`) on the input text and
returns the skill's result. It performs no LLM reasoning of its own — the point is the
skill call, not the output.

## Capability contract

- `config.yaml` declares `capabilities: [summarizer]`, so the call is allowed.
- Remove `summarizer` (or set a different capability) → the call raises `CapabilityDenied`
  before the skill runs (fail-closed).
- An empty `capabilities` list → no enforcement (whitelist-when-nonempty).

## I/O

| | Model | Field |
|---|---|---|
| Input | `CuratorAgentInput` | `text: str` |
| Output | `CuratorAgentOutput` | `result: str` |
