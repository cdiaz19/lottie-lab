# Round 7 — Governance — Results

**Framework under test:** `lottie-orchestrator @ feat/governance-policy-engine` (PR #12, stacked on
audit PR #11), installed editable in the lab venv.
**Harness:** `_policy_driver.py` — real `instantiate_agent` + real `DigestAgent` + scripted
`MockLLMProvider` (offline). A blocked run leaves `MockLLMProvider._index == 0`, proving `_execute`
never ran.

**Headline: 9/9 cases pass. Case 8 originally surfaced finding FG-1 (fail-closed but untyped error);
FG-1 was fixed in `lottie-orchestrator` (commit `6b79f80`) and the round re-run now passes clean.**

## Test matrix

| # | Case | Expected | Observed | LLM calls | Audit row | Result |
|---|------|----------|----------|-----------|-----------|--------|
| 1 | No policy declared | run succeeds | `ok` | 1 | `ok` | ✅ |
| 2 | 0-byte policy file | run succeeds | `ok` | 1 | `ok` | ✅ |
| 3 | `deny` matches cap | `PolicyDenied` before `_execute` | `PolicyDenied` | **0** | `denied` | ✅ |
| 4 | `escalate` matches | `PolicyEscalation` (distinct) | `PolicyEscalation` | **0** | `escalated` | ✅ |
| 5 | `allow` whitelist, cap not listed | denied | `PolicyDenied` ("not in allow-list") | 0 | `denied` | ✅ |
| 6 | `deny` + `allow` same cap | deny wins | `PolicyDenied` | 0 | `denied` | ✅ |
| 7 | two files unioned (both orders) | denied, order-independent | `PolicyDenied` for `[base,extra]` **and** `[extra,base]` | 0 | `denied` | ✅ |
| 8 | malformed policy YAML | `PolicyConfigError`, fail-closed | `PolicyConfigError` (fail-closed) — after FG-1 fix `6b79f80` | 0 | (none) | ✅ |
| 9 | audit integration | denied/escalated/ok logged + `lottie audit` renders | all three statuses present; `lottie audit` exit 0, table shows `escalated`/`denied`/`ok` for `DigestAgent` | — | — | ✅ |

## Proof points

- **Blocked before `_execute`** (cases 3–7): every blocked run reports `llm_calls=0`. `DigestAgent._execute`
  is the only caller of `self.complete`; zero completions ⇒ the agent body never ran ⇒ the policy gate
  blocks at the chokepoint, before the agent sees the input.
- **Distinct escalate vs deny** (case 4): `escalate` raises `PolicyEscalation`, a separate type from
  `PolicyDenied`, and audits as `escalated` (not `denied`).
- **Whitelist default-deny** (case 5): a non-empty `allow` that omits the declared capability denies it.
- **Precedence** (case 6): a capability in both `deny` and `allow` is denied — `deny` wins.
- **Union, order-independent** (case 7): the deny in the *second* declared file applies, and reversing
  the declared order (`[base,extra]` vs `[extra,base]`) yields the same `PolicyDenied` — merging is
  set-based.
- **Backward-compatible** (cases 1–2): no policy / empty policy ⇒ run proceeds (status `ok`). The repo's
  0-byte `policies/base.yaml` and existing agents are unaffected.
- **Audit integration** (case 9): `denied`, `escalated`, and `ok` rows all land in `.lottie/audit.db`
  and render through the real `lottie audit` CLI (exit 0).

## Findings

### FG-1 — FOUND → FIXED: malformed policy YAML failed closed but with an unwrapped error
**Found (this round, case 8):** `load_policy` called `yaml.safe_load(...)` without catching parse
errors, so a genuinely malformed policy file raised `yaml.parser.ParserError` straight out of
`instantiate_agent`, not the framework's typed `PolicyConfigError`. Fail-closed was preserved (the run
was blocked, never a silent allow) — not a security hole — but the error contract was leaky: callers
catching `PolicyConfigError` (the documented "bad policy config" signal) would have missed it. The
slice-2 unit tests didn't cover this; Round 7 caught it.

**Fixed:** `lottie-orchestrator` commit **`6b79f80`** (branch `feat/governance-policy-engine`) wraps
the `yaml.safe_load` call: `try/except yaml.YAMLError → raise PolicyConfigError(<file path> …) from exc`
— still fail-closed, now typed. A regression unit test
(`test_load_policy_malformed_yaml_raises_config_error`) was added next to the other policy tests so it
can't recur. Round 7 re-run after the fix: **case 8 → ✅ (`PolicyConfigError`)**, matrix 9/9.

> Note: `load_policy` already raised `PolicyConfigError` for a *missing* file and a *wrong-shape*
> (non-mapping) file; FG-1 closed the remaining gap — true YAML **parse** errors.

### Observation (not a defect): MockLLM ok-runs log 0 tokens
The `ok` audit rows show `0/0` tokens because `MockLLMProvider` reports no usage. Real-provider runs
populate tokens/cost. Out of scope for this round (we validate policy + audit wiring, not metering).

## §7 Sign-off checklist

- [x] Policy gate attached on the real `instantiate_agent` path (CLI/serve construction seam)
- [x] `deny` → `PolicyDenied`, blocked before `_execute` (llm_calls=0)
- [x] `escalate` → `PolicyEscalation`, distinct type, blocked
- [x] `allow` whitelist denies an unlisted declared capability
- [x] Precedence `deny > escalate > allow` (deny beats allow on the same capability)
- [x] Multiple policy files union, order-independent
- [x] No policy / empty (0-byte) policy ⇒ run succeeds (backward-compatible)
- [x] Malformed policy config fails **closed** (no silent allow) and raises the typed `PolicyConfigError` (after **FG-1** fix `6b79f80`)
- [x] Blocked runs audited with `status="denied"`/`"escalated"`; normal run `status="ok"`
- [x] `lottie audit` renders the rows (exit 0)
- [x] Findings recorded honestly (FG-1 found → fixed)

**Verdict:** audit trail + policy engine validated end-to-end from a downstream project — **9/9**. Round
7 found FG-1 (malformed YAML untyped error); it was fixed in `lottie-orchestrator` `6b79f80` (still
fail-closed, now typed, regression-tested) and the re-run passes clean. **No orchestrator PR merged** —
#11 → #12 await review.
