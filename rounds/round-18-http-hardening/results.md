# Round 18 — Results

**6/6 cases PASS.** Validated locally against orchestrator branch `feat/serve-http-hardening` (S4).

| # | Case | Outcome |
|---|------|---------|
| 1 | auth open | PASS — keys unset → open |
| 2 | auth required | PASS — missing 401 (no echo), Bearer/X-API-Key 200, wrong 401 |
| 3 | rate limit | PASS — 200,200,429 at rate=2 |
| 4 | per-identity | PASS — separate buckets per key |
| 5 | pagination agents | PASS — limit/offset slice, past-end empty |
| 6 | pagination models | PASS — limit slices /v1/models |

## What this proves downstream
- The HTTP transport is now gateable for production: keys required when set, per-identity rate
  caps, bounded list responses — all opt-in so existing clients are unaffected when unconfigured.

## Notes / limitations (honest)
- Rate limiting is per-process, in-memory (not distributed). Auth keys are static env values.
- When auth is OFF but rate-limit ON, a client can rotate the key header for fresh buckets
  (documented). Lab CI red on ORCH_REPO_TOKEN (known non-bug); validated locally.
