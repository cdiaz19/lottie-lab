# Round 36 — Provider router (orchestrator E5 S1)

> `lottie.yaml` has declared `providers.fallback` **since Phase 0** and nothing read it.
> A user who set one got nothing — worse than an absent feature, because the config
> claimed a resilience property the runtime did not have, and the failure mode was
> discovering that during an outage.
>
> This round's first job is proving the config stopped lying.

| # | Case | Result |
|---|------|--------|
| 1 | **`providers.fallback` is finally honoured** | PASS |
| 2 | a project with no fallback is not wrapped at all | PASS |
| 3 | a transient failure advances to the fallback | PASS |
| 4 | **a content-policy refusal is NEVER retried elsewhere** | PASS |
| 5 | **an auth error fails fast rather than doubling the spend** | PASS |
| 6 | an unrecognised error defaults to NOT transient | PASS |
| 7 | `model` reports who actually served, for the audit record | PASS |
| 8 | a fallback notifies — it is never silent | PASS |
| 9 | **a mid-stream failure never falls back** | PASS |
| 10 | a failure before the first delta does fall back | PASS |

## What the router REFUSES to do is the load-bearing half

**Case 4** is the one retry this framework must never make. Shopping a refused request to
a second model would launder a provider's safety decision through a framework that
advertises fail-closed gates. The case asserts the secondary is **never even called**.

**Case 5** — an auth error or bad request fails identically on the fallback, so retrying
buys nothing and spends twice. Failing fast is the correct behaviour, not a limitation.

**Case 6** — `is_transient` defaults to **False**. A new error type introduced by a
provider SDK cannot silently widen the fallback surface, which is the safe direction when
being wrong means either double-spending or evading a refusal.

**Case 9** — once bytes have shipped, switching providers would splice two models' answers
into one response. A silently corrupt answer is worse than a clean failure, so a
mid-stream failure propagates.

## Observability

A fallback leaves **two** traces: the notification at the moment it happens (case 8), and
the audit record afterwards, because `RoutedProvider.model` reports whoever actually served
(case 7) and that is what feeds `agent.provider`.

## Run

```bash
.venv/bin/python rounds/round-36-provider-router/_router_driver.py
```

## Result

**10/10 PASS** against orchestrator `feat/e5-provider-router`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
