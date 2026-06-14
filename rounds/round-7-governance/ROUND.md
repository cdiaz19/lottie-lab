# Round 7 — Governance (audit trail + policy engine)

> Validate two SHIPPED governance slices against `lottie-orchestrator @
> feat/governance-policy-engine`: the **audit trail** (PR #11) and the **declarative
> capability policy engine** (PR #12, stacked on #11). Does NOT cover cost governance or
> OpenTelemetry — those are later slices, not built yet.

## Goal

Prove, from a downstream project, that capability policy is enforced at the run chokepoint
(`deny`→`PolicyDenied`, `escalate`→`PolicyEscalation`, `allow`→whitelist, precedence deny >
escalate > allow), that empty/absent rules block nothing (backward-compatible), that malformed
policy config fails **closed** (never a silent allow), and that blocked runs are recorded in the
immutable audit trail with a distinct `status` and surfaced by `lottie audit`.

## What's being tested

Exercised through the **real shipped path** in-process: `instantiate_agent` (which attaches the
policy gate) + the real **`DigestAgent`** + a scripted `MockLLMProvider` (offline, deterministic).
A blocked run leaves the MockLLM unconsumed (`llm._index == 0`) — proving `_execute` never ran.
Each case also reads back its audit row, and a final case renders `lottie audit`.

| # | Case | Expected |
|---|------|----------|
| 1 | No policy declared / no policy file | run succeeds (baseline) |
| 2 | Declared policy is a 0-byte file | run succeeds (no rules) |
| 3 | `deny` matches declared capability | `PolicyDenied`, blocked before `_execute` |
| 4 | `escalate` matches | `PolicyEscalation` (distinct), blocked |
| 5 | non-empty `allow`, capability not listed | denied (default-deny whitelist) |
| 6 | `deny` + `allow` both match | deny wins (precedence) |
| 7 | two policy files unioned (both orders) | combined rules apply, order-independent |
| 8 | malformed policy YAML | fail-closed at instantiate (no silent allow) |
| 9 | audit integration | cases 3/4 log `denied`/`escalated`, a normal run logs `ok`, `lottie audit` renders them |

## Build / verify sequence

```bash
# From lottie-lab, with the orchestrator installed editable on the policy branch:
#   uv pip install -e '../lottie-orchestrator'   (already -e; checkout feat/governance-policy-engine)
source .venv/bin/activate
python3 rounds/round-7-governance/_policy_driver.py    # writes inputs/ + outputs/, prints PASS/FAIL
```

The driver is the harness: it writes `inputs/case-*.json` (scenarios) and `outputs/case-*.out.txt`
(captured results), and seeds `outputs/audit-demo/` for the `lottie audit` render.

## Definition of done

Every §-checklist box in `results.md` signed off; policy enforced before `_execute` on `deny`/
`escalate`; whitelist + precedence + multi-file union correct; empty/absent rules block nothing;
malformed config fails closed; audit rows written with `denied`/`escalated`/`ok` and rendered by
`lottie audit`; findings recorded honestly.

## Deviations / notes

- `LOTTIE_LAB_PLAN.md` does not exist in the repo; this round follows the existing round-4 / round-6
  folder convention (`ROUND.md`, `inputs/`, `outputs/`, `results.md`, sign-off table).
- Validated **in-process via the real `instantiate_agent`** rather than a live `lottie run` subprocess
  per case, so the success cases stay offline/deterministic (scripted `MockLLMProvider`) and don't
  burn API quota — the policy gate, `BaseAgent.run` enforcement, and audit logging are the real
  shipped code. `lottie audit` IS exercised as a real CLI subprocess (case 9).
- Scope is audit + policy only. Cost governance and OpenTelemetry are later slices and out of scope.
