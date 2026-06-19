"""Round-12 durable-resume driver — validate the SHIPPED `POST /v1/agents/{name}/resume`
endpoint + durable sqlite checkpointing (orchestrator PR #17, now on main) from a downstream
project.

Drives the real shipped path in-process: `build_http_app(LAB_ROOT)` (the same app `lottie serve
--port` serves) via Starlette's TestClient. The lab's `editor` mesh (EditorMesh: plan →
parallel[draft,factcheck] → review → publish(HITL gate)) is the worked example — a `POST /run`
interrupts at the `publish` gate, and `POST /resume {thread_id, decision}` continues it.

`LOTTIE_MESH_CHECKPOINT=sqlite` (what `lottie serve --port` sets) makes the engine persist the
mesh state to `<cwd>/.lottie/mesh/checkpoints.db`, so a FRESH app instance (new worker / after a
restart — empty agent cache) can resume the same `thread_id` from disk. `build_provider` is
patched per-case to a MockLLMProvider (the supervisor is the only LLM consumer; workers are
deterministic stubs). API keys unset.
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

os.chdir(LAB_ROOT)  # engine's sqlite db (root=None) is cwd-derived; lottie serve sets cwd=project root
os.environ["LOTTIE_MESH_CHECKPOINT"] = "sqlite"  # what `lottie serve --port` setdefaults
os.environ["LOTTIE_DISABLE_AUDIT"] = "1"  # default off; case 08 opts back in

# Drives EditorMesh to the publish interrupt: supervisor routes plan -> draft+factcheck ->
# review -> publish (interrupt_before), consuming 4 calls; the trailing FINISHes complete it.
_RUN_SCRIPT = ["plan", "draft, factcheck", "review", "publish", "FINISH", "FINISH"]
_FINISH_SCRIPT = ["FINISH", "FINISH", "FINISH"]  # post-publish supervisor on a fresh resume app

_SCRIPT: list[str] = list(_RUN_SCRIPT)


def _provider(_name: str) -> MockLLMProvider:
    return MockLLMProvider(list(_SCRIPT))


service_mod.build_provider = _provider  # type: ignore[assignment]


def _client(script: list[str]) -> TestClient:
    """Fresh combined app+client with the given supervisor script (fresh AgentService = empty
    agent cache; only the on-disk sqlite checkpoint links instances)."""
    global _SCRIPT
    _SCRIPT = list(script)
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


def case_01_run_interrupts() -> bool:
    resp = _client(_RUN_SCRIPT).post("/v1/agents/editor/run", json={"task": "write a launch post"})
    body = resp.json()
    ok = (
        resp.status_code == 200
        and body.get("status") == "interrupted"
        and bool(body.get("thread_id"))
        and body.get("pending") is not None  # the HITL publish gate
    )
    return _emit(
        "01-run-interrupts",
        "POST /v1/agents/editor/run drives the mesh to the publish HITL gate -> 200 interrupted\n"
        f"with a thread_id + pending. status={body.get('status')} thread_id={body.get('thread_id')} "
        f"pending={body.get('pending')}",
        ok,
    )


def case_02_resume_same_app() -> bool:
    client = _client(_RUN_SCRIPT)  # one app: run + resume share the cached agent (script continues)
    started = client.post("/v1/agents/editor/run", json={"task": "write a launch post"}).json()
    tid = started["thread_id"]
    resp = client.post(
        "/v1/agents/editor/resume",
        json={"thread_id": tid, "decision": {"action": "approve"}},
    )
    body = resp.json()
    final = str(body.get("output", {}).get("final", ""))
    ok = resp.status_code == 200 and body.get("status") == "complete" and final.startswith("PUBLISHED:")
    return _emit(
        "02-resume-same-app",
        "POST /v1/agents/editor/resume (approve) continues past the gate -> 200 complete.\n"
        f"status={body.get('status')} final={final!r}",
        ok,
    )


def case_03_durable_cross_process() -> bool:
    """THE headline: a FRESH app instance (empty cache) resumes a checkpoint written by another,
    via the shared on-disk sqlite db — durable cross-process resume (FU-9)."""
    _clean_db()
    app_a = _client(_RUN_SCRIPT)  # "process A"
    started = app_a.post("/v1/agents/editor/run", json={"task": "write a launch post"}).json()
    tid = started["thread_id"]
    db_exists = (LAB_ROOT / ".lottie" / "mesh" / "checkpoints.db").exists()

    # "process B": brand-new build_http_app -> new AgentService -> empty agent cache. The ONLY
    # link to app_a is the sqlite checkpoint on disk. Its supervisor only needs to FINISH after
    # the (deterministic) publish worker runs on resume.
    app_b = _client(_FINISH_SCRIPT)
    resp = app_b.post(
        "/v1/agents/editor/resume",
        json={"thread_id": tid, "decision": {"action": "approve"}},
    )
    body = resp.json()
    final = str(body.get("output", {}).get("final", ""))
    ok = (
        db_exists  # the interrupt persisted to disk
        and resp.status_code == 200  # found the checkpoint (NOT 404 thread_not_found)
        and body.get("agent") == "editor"
        and body.get("status") == "complete"
        and final.startswith("PUBLISHED:")
    )
    return _emit(
        "03-durable-cross-process",
        "Durable resume (FU-9): app A runs to the gate (checkpoint -> sqlite); a FRESH app B\n"
        "(empty cache) resumes the same thread_id from the shared on-disk db -> 200 complete.\n"
        f"db_persisted={db_exists} resume_status={resp.status_code}/{body.get('status')} final={final!r}",
        ok,
    )


def case_04_resume_unknown_agent() -> bool:
    resp = _client(_RUN_SCRIPT).post(
        "/v1/agents/nope/resume", json={"thread_id": "t", "decision": {"action": "approve"}}
    )
    ok = resp.status_code == 404 and resp.json()["error"]["type"] == "not_found"
    return _emit(
        "04-resume-unknown-agent",
        f"Resume an unknown agent -> 404 not_found. status={resp.status_code}/{resp.json()['error']['type']}",
        ok,
    )


def case_05_resume_non_mesh() -> bool:
    resp = _client(["x"]).post(
        "/v1/agents/digest/resume", json={"thread_id": "t", "decision": {"action": "approve"}}
    )
    ok = resp.status_code == 400 and resp.json()["error"]["type"] == "not_resumable"
    return _emit(
        "05-resume-non-mesh",
        "Resume a non-mesh agent (digest) -> 400 not_resumable.\n"
        f"status={resp.status_code}/{resp.json()['error']['type']}",
        ok,
    )


def case_06_resume_unknown_thread() -> bool:
    client = _client(_RUN_SCRIPT)
    client.post("/v1/agents/editor/run", json={"task": "write a launch post"})  # a real checkpoint exists
    resp = client.post(
        "/v1/agents/editor/resume",
        json={"thread_id": "no-such-thread", "decision": {"action": "approve"}},
    )
    ok = resp.status_code == 404 and resp.json()["error"]["type"] == "thread_not_found"
    return _emit(
        "06-resume-unknown-thread",
        "Resume a bogus thread_id -> 404 thread_not_found (typed; no raw langgraph/pydantic leak).\n"
        f"status={resp.status_code}/{resp.json()['error']['type']}",
        ok,
    )


def case_07_resume_bad_body() -> bool:
    resp = _client(["x"]).post(
        "/v1/agents/editor/resume", json={"decision": {"action": "approve"}}  # no thread_id
    )
    ok = resp.status_code == 400 and resp.json()["error"]["type"] == "invalid_request"
    return _emit(
        "07-resume-bad-body",
        "Resume with a malformed body (no thread_id) -> 400 invalid_request.\n"
        f"status={resp.status_code}/{resp.json()['error']['type']}",
        ok,
    )


def case_08_governance_inherited() -> bool:
    """A resume run is audited (governance inherited on the resume path, no second gate)."""
    from lottie.governance.audit import SqliteAuditLogger

    audit_db = LAB_ROOT / ".lottie" / "audit.db"
    if audit_db.exists():
        audit_db.unlink()
    os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
    try:
        client = _client(_RUN_SCRIPT)
        started = client.post("/v1/agents/editor/run", json={"task": "write a launch post"}).json()
        client.post(
            "/v1/agents/editor/resume",
            json={"thread_id": started["thread_id"], "decision": {"action": "approve"}},
        )
        records = SqliteAuditLogger(LAB_ROOT).query(agent="EditorMesh")
        ok = len(records) >= 1 and any(r.status == "ok" for r in records)
        detail = f"records={len(records)} statuses={[r.status for r in records]}"
    finally:
        os.environ["LOTTIE_DISABLE_AUDIT"] = "1"
    return _emit(
        "08-governance-inherited",
        "A resume run is audited via AgentService.resume_agent -> BaseAgent.run (no second gate).\n"
        f"{detail}",
        ok,
    )


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    _clean_db()
    cases = [
        case_01_run_interrupts,
        case_02_resume_same_app,
        case_03_durable_cross_process,
        case_04_resume_unknown_agent,
        case_05_resume_non_mesh,
        case_06_resume_unknown_thread,
        case_07_resume_bad_body,
        case_08_governance_inherited,
    ]
    results = [c() for c in cases]
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
