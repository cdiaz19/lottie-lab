# Round 15 — Rule 11: per-skill-call capability enforcement (orchestrator S1)

> Validate the SHIPPED **CapabilityEnforcer** (orchestrator v1 epic slice S1, PR #24) from a
> downstream project: an agent may only call skills declared in its `config.yaml`
> `capabilities` list; an undeclared skill call is blocked fail-closed, while the framework's
> own security skills stay exempt.

## Goal

Prove, from a downstream project's point of view, that orchestrator rule 11 is enforced at
the real seam (`BaseSkill.run`, gated by an `_execute`-scoped ContextVar the agent activates):

- a declared skill call runs;
- an **undeclared** skill call raises `CapabilityDenied` **before the skill executes**;
- an **empty** `capabilities` list means no enforcement (whitelist-when-nonempty — back-compat);
- the derived capability name matches the config vocabulary (`SummarizerSkill` → `summarizer`);
- the framework's OWN security skills (InputSanitizer/SecretDetection), invoked by the
  SecurityGate **outside** `_execute`, are **exempt** — a narrowly-scoped agent still serves
  over HTTP without a spurious `CapabilityDenied`.

## The downstream fixture

`agents/curator/` (`CuratorAgent`) is a new lab agent whose only job is to **call a skill**:
its `_execute` invokes `SummarizerSkill` (capability name `summarizer`). Whether the call is
allowed is decided entirely by the declared `capabilities`. This is the honest downstream
shape — a project agent composing a shipped skill through the governed chokepoint.

## What's being tested

The driver runs the real shipped path in-process: `instantiate_agent(CuratorAgent, config=…)`
— the canonical CLI/serve dispatch that attaches the capability gate from `config.capabilities`
— plus `build_http_app(LAB_ROOT)` via Starlette `TestClient` for the framework-exemption case.
`build_provider` is patched to a `MockLLMProvider` (API keys unset).

| # | Case | Checks |
|---|------|--------|
| 1 | declared allowed | `capabilities=[summarizer]` → skill runs, result returned |
| 2 | undeclared blocked | `capabilities=[something-else]` → `CapabilityDenied` (message names `summarizer`), fail-closed before the skill runs |
| 3 | empty no-enforcement | `capabilities=[]` → `NullCapabilityGate`, skill call unenforced |
| 4 | name derivation | `SummarizerSkill.resolved_capability_name() == "summarizer"` |
| 5 | framework exempt (HTTP) | `POST /v1/agents/curator/run` through the real SecurityGate → 200 `complete`; InputSanitizer/SecretDetection ran outside `_execute` and were exempt |

## Run

```bash
uv run python rounds/round-15-capability/_capability_driver.py
```

## Result

**5/5 PASS.** See `results.md` and `outputs/`.

Lab CI stays red on `ORCH_REPO_TOKEN` (private-clone auth — known non-bug; do NOT rotate until
the orchestrator repo is public). Validated locally against the S1 branch.
