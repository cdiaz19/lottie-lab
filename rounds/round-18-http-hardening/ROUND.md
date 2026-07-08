# Round 18 — HTTP hardening: auth + rate limit + pagination (orchestrator S4)

> Validate the SHIPPED HTTP hardening (v1 epic slice S4) from a downstream project: the
> `lottie serve --port` app gains opt-in API-key auth, per-identity rate limiting, and
> limit/offset pagination — off by default (back-compat), enforced when configured.

## What's being tested

`build_http_app(LAB_ROOT)` via Starlette TestClient, toggling env per case.

| # | Case | Checks |
|---|------|--------|
| 1 | auth open | `LOTTIE_API_KEYS` unset → 200 (open) |
| 2 | auth required | set → missing 401 (no key echo), Bearer 200, X-API-Key 200, wrong 401 |
| 3 | rate limit | `LOTTIE_RATE_LIMIT_PER_MIN=2` → 200,200,429 |
| 4 | per-identity | rate=1 + two keys → each key its own bucket |
| 5 | pagination /v1/agents | limit/offset slice; offset past end → [] |
| 6 | pagination /v1/models | limit slices the model list |

## Run
```bash
uv run python rounds/round-18-http-hardening/_http_hardening_driver.py
```

## Result
**6/6 PASS.** Lab CI red on `ORCH_REPO_TOKEN` (known non-bug); validated locally against S4.
