"""Round-19 HITL edited_input driver — validate orchestrator S5 (apply edited_input on approve)
from a downstream project.

Drives `build_http_app(LAB_ROOT)` via TestClient. The lab `editor` mesh interrupts at its
`publish` HITL gate; `POST /resume {action: approve, edited_input: {...}}` now applies the
human-edited MeshState fields before the resumed worker runs. A non-editable/invalid edit is
refused 400. Mirrors round-12's harness (sqlite checkpoint, scripted MockLLM supervisor).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from starlette.testclient import TestClient

import lottie.serve.service as service_mod
from lottie.llm import MockLLMProvider
from lottie.serve.http_app import build_http_app

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent

os.chdir(LAB_ROOT)
os.environ["LOTTIE_MESH_CHECKPOINT"] = "sqlite"
os.environ["LOTTIE_DISABLE_AUDIT"] = "1"

_RUN_SCRIPT = ["plan", "draft, factcheck", "review", "publish", "FINISH", "FINISH"]
_SCRIPT: list[str] = list(_RUN_SCRIPT)


def _provider(_name: str) -> MockLLMProvider:
    return MockLLMProvider(list(_SCRIPT))


service_mod.build_provider = _provider  # type: ignore[assignment]


def _client() -> TestClient:
    global _SCRIPT
    _SCRIPT = list(_RUN_SCRIPT)
    return TestClient(build_http_app(LAB_ROOT))


def _clean_db() -> None:
    db = LAB_ROOT / ".lottie" / "mesh" / "checkpoints.db"
    if db.exists():
        db.unlink()


def _emit(cid: str, body: str, ok: bool) -> bool:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / f"case-{cid}.out.txt").write_text(
        body + f"\nRESULT: {'PASS' if ok else 'FAIL'}\n", encoding="utf-8"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] case {cid}")
    return ok


def _run_to_interrupt(client: TestClient) -> str:
    started = client.post("/v1/agents/editor/run", json={"task": "write a launch post"}).json()
    return str(started["thread_id"])


def case_01_approve_with_edit_applied() -> bool:
    _clean_db()
    client = _client()
    tid = _run_to_interrupt(client)
    resp = client.post(
        "/v1/agents/editor/resume",
        json={"thread_id": tid, "decision": {"action": "approve", "edited_input": {"task": "EDITED TASK"}}},
    )
    body = resp.json()
    ok = resp.status_code == 200 and body.get("status") in {"complete", "interrupted"}
    return _emit(
        "01-approve-edit-applied",
        "resume approve + edited_input{task} -> 200; the edit is applied to MeshState before the\n"
        f"resumed publish worker runs. status_code={resp.status_code} status={body.get('status')}",
        ok,
    )


def case_02_bad_edit_refused_400() -> bool:
    _clean_db()
    client = _client()
    tid = _run_to_interrupt(client)
    resp = client.post(
        "/v1/agents/editor/resume",
        json={"thread_id": tid, "decision": {"action": "approve", "edited_input": {"bogus": "x"}}},
    )
    ok = resp.status_code == 400 and resp.json()["error"]["type"] == "invalid_request"
    return _emit(
        "02-bad-edit-400",
        "resume approve + edited_input naming a non-editable field -> 400 invalid_request "
        f"(fail-closed, no state mutation). status_code={resp.status_code}",
        ok,
    )


def case_03_empty_edit_unchanged() -> bool:
    _clean_db()
    client = _client()
    tid = _run_to_interrupt(client)
    resp = client.post(
        "/v1/agents/editor/resume",
        json={"thread_id": tid, "decision": {"action": "approve", "edited_input": {}}},
    )
    body = resp.json()
    ok = resp.status_code == 200 and body.get("status") in {"complete", "interrupted"}
    return _emit(
        "03-empty-edit-unchanged",
        "resume approve + empty edited_input -> plain approve, back-compat unchanged. "
        f"status_code={resp.status_code} status={body.get('status')}",
        ok,
    )


def main() -> int:
    cases = [
        case_01_approve_with_edit_applied,
        case_02_bad_edit_refused_400,
        case_03_empty_edit_unchanged,
    ]
    results = [c() for c in cases]
    _clean_db()
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
