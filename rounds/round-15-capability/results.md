# Round 15 — Results

**5/5 cases PASS.** Validated locally against orchestrator branch
`feat/governance-capability-enforcer` (S1, PR #24) via the lab's editable install.

| # | Case | Outcome |
|---|------|---------|
| 1 | declared allowed | PASS — `capabilities=[summarizer]`, `CuratorAgent.run` → `result="hello world"` |
| 2 | undeclared blocked | PASS — `capabilities=[something-else]` → `CapabilityDenied`, message names `summarizer`, skill never ran |
| 3 | empty no-enforcement | PASS — `capabilities=[]` → run succeeds (`NullCapabilityGate`) |
| 4 | name derivation | PASS — `SummarizerSkill.resolved_capability_name() == "summarizer"` |
| 5 | framework exempt (HTTP) | PASS — REST run 200 `complete`; SecurityGate's security skills exempt (outside `_execute`) |

## What this proves downstream

- Rule 11 is enforced at the real invocation seam (`BaseSkill.run`), not by convention: a
  project agent calling an undeclared skill is stopped **fail-closed** before the skill runs.
- The enforcement is **opt-in per agent** via the declared whitelist (empty = off), so existing
  downstream agents that don't declare capabilities are unaffected — no forced migration.
- The `_execute`-scoped gate does NOT block the framework's own security skills, so a
  narrowly-scoped agent still passes through the full serve SecurityGate. This is the invariant
  that lets S2 (BaseAgent/CLI security gate) layer on without agents having to "declare" the
  security skills.

## Notes / limitations (honest)

- `CapabilityDenied` surfaces to a REST caller as a 500-class run error if it ever fired on the
  serve path (it does not here — curator declares its skill). A distinct HTTP mapping is
  deferred in S1 (it's a misconfiguration, not caller input).
- Capability identity is derived from the skill class name; a skill whose config name differs
  from its de-`Skill`-ed class name would set an explicit `capability_name` (not exercised here).
- Lab CI remains red on `ORCH_REPO_TOKEN` (known non-bug). Round validated locally.
