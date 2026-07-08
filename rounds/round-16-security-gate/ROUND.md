# Round 16 — BaseAgent/CLI security gate (orchestrator S2)

> Validate the SHIPPED input/output security gate at the **BaseAgent chokepoint** (v1 epic
> slice S2): `lottie run` / instantiate-built agents now pass through the same rules-8-&-9 gate
> as serve, fail-closed, without double-gating the serve path.

## Goal

Before S2, only the serve path gated. S2 moves the gate to `BaseAgent.run` (injected via
`instantiate_agent(security_gate=...)`). Prove downstream that:

- a clean gated run passes;
- a **prompt-injection input** is refused (`InputSecurityViolation`) at the chokepoint, before
  the LLM is called;
- an output carrying a **secret** is withheld (`OutputSecurityViolation`) after `_execute`;
- the **serve wiring** (`security_gate=None`) leaves the agent's gate `Null` — serve gates
  externally, so no run is double-gated;
- a **directly-constructed** BaseAgent is ungated (back-compat, like policy/cost/capability).

## What's being tested

The driver runs the real shipped path in-process: `instantiate_agent(DigestAgent, security_gate=…)`
— the CLI wiring passes a real `serve.security.SecurityGate`; the serve wiring passes `None`.
MockLLMProvider (API keys unset).

| # | Case | Checks |
|---|------|--------|
| 1 | clean passes | gated run, clean I/O → ok |
| 2 | injection refused | injection input → `InputSecurityViolation` before the LLM |
| 3 | secret withheld | output with a secret → `OutputSecurityViolation` |
| 4 | serve single-gated | `security_gate=None` → `NullSecurityGate` on the agent (serve gates externally) |
| 5 | direct ungated | hand-constructed BaseAgent → `NullSecurityGate`, runs unenforced |

## Run

```bash
uv run python rounds/round-16-security-gate/_security_gate_driver.py
```

## Result

**5/5 PASS.** See `results.md` and `outputs/`. Lab CI red on `ORCH_REPO_TOKEN` (known non-bug);
validated locally against the S2 branch.
