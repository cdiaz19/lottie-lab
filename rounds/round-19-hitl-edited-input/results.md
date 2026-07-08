# Round 19 — Results

**3/3 cases PASS.** Validated locally against orchestrator branch `feat/hitl-edited-input` (S5).

| # | Case | Outcome |
|---|------|---------|
| 1 | approve + edit applied | PASS — edited_input{task} accepted+applied → 200 complete/interrupted |
| 2 | bad edit refused | PASS — non-editable field → 400 invalid_request (fail-closed, no mutation) |
| 3 | empty edit unchanged | PASS — plain approve back-compat |

## What this proves downstream
- A human approving a paused mesh can now override editable MeshState fields (task/final) and the
  resumed worker runs on the edited state — the deferral is closed.
- The edit is fail-closed: a non-editable/unknown field is refused with a 400 (not a 500, not a
  silent no-op), so a malformed edit never mutates state.

## Notes / limitations (honest)
- Only top-level string MeshState fields (task/final) are editable; structured/per-worker inputs
  are out of scope. LocalEngine has no HITL. Lab CI red on ORCH_REPO_TOKEN (known non-bug).
