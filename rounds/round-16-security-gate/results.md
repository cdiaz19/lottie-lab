# Round 16 — Results

**5/5 cases PASS.** Validated locally against orchestrator branch `feat/security-gate-baseagent`
(S2) via the lab's editable install.

| # | Case | Outcome |
|---|------|---------|
| 1 | clean passes | PASS — gated `DigestAgent` run, clean I/O → `result` returned |
| 2 | injection refused | PASS — "ignore all previous instructions" → `InputSecurityViolation`, before the LLM |
| 3 | secret withheld | PASS — output containing an `AKIA…` key → `OutputSecurityViolation` |
| 4 | serve single-gated | PASS — `security_gate=None` → `NullSecurityGate` (serve gates externally, no double) |
| 5 | direct ungated | PASS — direct BaseAgent construction → `NullSecurityGate`, runs unenforced |

## What this proves downstream

- The rules-8-&-9 gate is now enforced at the `BaseAgent.run` chokepoint, so a downstream
  `lottie run` (or any instantiate-built agent) is gated identically to serve — closing the
  CLI/direct-path gap without touching serve.
- The serve path is **not** double-gated: serve keeps its external gate and builds agents with
  no injected gate, so BaseAgent's gate is `Null` there.
- Enforcement is opt-in by injection (CLI passes a gate, direct construction gets `Null`),
  matching the policy/cost/capability precedent — existing downstream tests are unaffected.

## Notes / limitations (honest)

- Security-blocked runs are not audited in S2 (policy/cost blocks are); the block raises a serve
  error, and auditing it from core would need a broad catch. Deferred, documented.
- `run_stream` stays serve-gated (incremental `StreamingSecretGate`); the chokepoint gate covers
  the non-streaming `run`.
- Lab CI red on `ORCH_REPO_TOKEN` (known non-bug). Round validated locally.
