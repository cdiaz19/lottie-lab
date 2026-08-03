# Round 28 — Runtime kernel (orchestrator V3 S1)

> S1 ships a kernel with **no consumers**, so there is no agent behaviour to observe.
> What a downstream round can still prove is that the kernel behaves as advertised when a
> real project drives it directly — and, critically, that its guarantees are **structural
> rather than conventional**.
>
> **This round found a real hole and closed it.**

## The finding

Case 6 failed on the first run. The driver injected a fake hasher —
`f"h:{model_dump_json()}"` — and the raw payload landed straight on the event bus.

D6 says events carry hashes, never raw content. The kernel enforced field *names* and
*types*, but had no way to know the "hash" was not a hash. The guarantee was
**"trust the caller."** That matters because V3 E7 opens this bus to third-party plugins.

Fixed upstream: `Pipeline` now verifies every digest against `^[0-9a-f]{64}$` before it
reaches the bus and raises `UnsafeHasherError` otherwise. Case **6b** was added to prove
the refusal, and asserts that **no event escapes at all** when the hasher is rejected.

## Cases

| # | Case | Result |
|---|------|--------|
| 1 | a realistic gate chain runs pre low→high, post high→low | PASS |
| 2 | **`RunCompleted` reaches observers before the cost settle** | PASS |
| 3 | two modules using the same state key do not collide | PASS |
| 4 | a denied run still releases the outer reservation | PASS |
| 5 | **a sabotaging subscriber cannot fail a run** nor starve the next | PASS |
| 6 | a subscriber cannot read raw input off the bus | PASS |
| 6b | **an echoing hasher is REFUSED**, no event escapes | PASS |
| 7 | one subscriber cannot mutate what later subscribers observe | PASS |
| 8 | **a plugin claiming an occupied order is rejected at registration** | PASS |
| 9 | a refused run emits `RunBlocked` naming the gate that refused | PASS |
| 10 | **no shipped module consumes the kernel yet** (zero behaviour change) | PASS |

## Why these

**Case 2** is the invariant S2 depends on. Today `BaseAgent.run` hand-maintains
audit-before-settle through nested `finally` blocks; the kernel gets it from emitting
`RunCompleted` in the innermost frame. The driver observes the real ordering:
`reserve:cost → reserve:capability → RunStarted → RunCompleted → settle:capability →
settle:cost`.

**Cases 5, 6b, 7 and 8** are adversarial — each is something a plugin author (E7) could
otherwise exploit: sabotage a run by raising in a subscriber, read payloads off the bus,
tamper with what later subscribers see, or take a security middleware's slot.

**Case 10** verifies S1's central claim mechanically: `grep` over the installed package
confirms nothing outside `runtime/` imports it. Zero behaviour change is asserted, not
asserted-about.

## Run

```bash
.venv/bin/python rounds/round-28-runtime-kernel/_kernel_driver.py
```

## Result

**11/11 PASS** against orchestrator `feat/v3-s1-runtime-kernel`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
