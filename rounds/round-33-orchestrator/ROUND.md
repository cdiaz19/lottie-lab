# Round 33 — Module orchestrator (orchestrator V3 S6)

> S6 made the runtime chain **visible and configurable**. The operator-facing question it
> answers — *"what is actually wrapping my agent's runs?"* — was previously answerable
> only by reading source.

| # | Case | Result |
|---|------|--------|
| 1 | the mounted chain is reportable, in execution order | PASS — 11 |
| 2 | every chain position is distinct and ordered | PASS |
| 3 | a module can be disabled per agent | PASS |
| 4 | a disabled module is **never constructed** | PASS |
| 5 | an agent with a module removed still runs | PASS |
| 6 | **a typo'd module name is detectable, not silently inert** | PASS |
| 7 | disabling a fail-closed gate is visible | PASS |
| 8 | **two modules claiming one slot is rejected at composition** | PASS |
| 9 | `KNOWN_MODULES` matches the real chain | PASS |

## The three that are about safety, not ergonomics

**Case 6 — a typo does nothing, which is the dangerous kind of nothing.** Write
`recal: {enabled: false}` and the operator believes recall is off while it is still
mounted. The round asserts the unknown name is *detectable* and that the module is
genuinely still there — so `lottie doctor` has something real to warn about.

**Case 8 — two modules cannot quietly share a slot.** Rejected at composition, not at run
time, with a message naming both claimants:
`module 'policy' claims order 20, already held by 'security_input'`. A plugin (E7) must
never be able to displace a security gate by picking its number.

**Case 9 — `doctor` cannot drift.** If a module were added without updating
`KNOWN_MODULES`, doctor would start reporting a legitimate config line as a typo. Pinned
against the real chain.

## Run

```bash
.venv/bin/python rounds/round-33-orchestrator/_orchestrator_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v3-s6-orchestrator`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
