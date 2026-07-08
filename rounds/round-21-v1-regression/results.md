# Round 21 — Results

**6/6 v1 rounds PASS** — full regression against orchestrator `v1.0.0` (main).

| Round | Slice | Cases | Outcome |
|---|---|---|---|
| 15 | S1 capability | 5/5 | PASS |
| 16 | S2 security gate | 5/5 | PASS |
| 17 | S3 cost caps | 5/5 | PASS |
| 18 | S4 http hardening | 6/6 | PASS |
| 19 | S5 hitl edited_input | 3/3 | PASS |
| 20 | S6 agentic hygiene | 4/4 | PASS |

All six V1 hardening slices remain green together on the merged main — the downstream
definition-of-done for the v1.0.0 tag. Lab CI red on ORCH_REPO_TOKEN (known non-bug).
