# Round 19 — HITL edited_input-on-approve (orchestrator S5)

> Validate the SHIPPED apply-edited_input-on-approve (v1 epic slice S5): a human resuming a
> paused mesh can edit the state the resumed worker acts on; a bad edit is refused fail-closed.

## What's being tested
`build_http_app(LAB_ROOT)` via TestClient; the `editor` mesh interrupts at its `publish` HITL
gate; `POST /resume {action: approve, edited_input}` applies the edit.

| # | Case | Checks |
|---|------|--------|
| 1 | approve + edit applied | `edited_input={task:…}` → 200; edit applied before the resumed worker |
| 2 | bad edit refused | `edited_input={bogus:…}` (non-editable field) → 400 invalid_request, fail-closed |
| 3 | empty edit unchanged | `edited_input={}` → plain approve (back-compat) |

## Run
```bash
uv run python rounds/round-19-hitl-edited-input/_hitl_edited_input_driver.py
```

## Result
**3/3 PASS.** Lab CI red on `ORCH_REPO_TOKEN` (known non-bug); validated locally against S5.
