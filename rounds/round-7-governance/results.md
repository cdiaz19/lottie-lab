# Round 7 — Governance — Results

**Framework under test:** `lottie-orchestrator @ feat/governance-policy-engine` (PR #12, stacked on
audit PR #11), installed editable in the lab venv.
**Harness:** `_policy_driver.py` — real `instantiate_agent` + real `DigestAgent` + scripted
`MockLLMProvider` (offline). A blocked run leaves `MockLLMProvider._index == 0`, proving `_execute`
never ran.

**Headline: 8/9 cases pass clean; case 8 surfaces one real finding (FG-1) — fail-closed holds, but
the error type is unwrapped.**

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
| 8 | malformed policy YAML | `PolicyConfigError`, fail-closed | **fail-closed ✅** but raises `yaml.parser.ParserError`, not `PolicyConfigError` | 0 | (none) | ⚠️ **FG-1** |
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

### FG-1 (minor, recommend fixing before #12 merges): malformed policy YAML fails closed but with an unwrapped error
`load_policy` calls `yaml.safe_load(...)` without catching parse errors. A genuinely malformed policy
file therefore raises `yaml.parser.ParserError` straight out of `instantiate_agent`, not the framework's
typed `PolicyConfigError`. **Fail-closed is preserved** — the run is blocked, never a silent allow — so
this is not a security hole, but the error contract is leaky: callers catching `PolicyConfigError` (the
documented "bad policy config" signal) would miss it.
**Recommended fix** (one line, in `src/lottie/governance/policy.py` `load_policy`): wrap the
`yaml.safe_load` call in `try/except yaml.YAMLError as exc: raise PolicyConfigError(...) from exc`. After
that, case 8 would observe `PolicyConfigError` and flip to ✅.

> Note: `load_policy` already raises `PolicyConfigError` for a *missing* file and for a *wrong-shape*
> (non-mapping) file — only true YAML **parse** errors slip through untyped.

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
- [x] Malformed policy config fails **closed** (no silent allow) — ⚠️ raises `yaml.ParserError` not `PolicyConfigError` (**FG-1**, fix recommended before #12 merge)
- [x] Blocked runs audited with `status="denied"`/`"escalated"`; normal run `status="ok"`
- [x] `lottie audit` renders the rows (exit 0)
- [x] Findings recorded honestly (FG-1)

**Verdict:** audit trail + policy engine validated end-to-end from a downstream project. 8/9 clean;
case 8 is fail-closed with one recommended one-line hardening (FG-1). **No PR merged, nothing pushed to
main** — awaiting review before merging #11 then #12.
