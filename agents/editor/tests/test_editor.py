from __future__ import annotations

from pathlib import Path

import pytest

from lottie.llm import MockLLMProvider
from lottie.mesh.errors import CapabilityViolation
from lottie.mesh.schema import ApprovalDecision
from lottie.project.config import AgentConfig

from agents.editor.agent import EditorMesh
from agents.editor.schema import EditorInput

# Supervisor script: plan -> (draft+factcheck parallel) -> review -> publish -> FINISH.
_SCRIPT = ["plan", "draft, factcheck", "review", "publish", "FINISH", "FINISH"]


def _config(**over: object) -> AgentConfig:
    base: dict[str, object] = {
        "provider": "mock/x",
        "workers": ["plan", "draft", "factcheck", "review", "publish"],
        "interrupt_before": ["publish"],
        "policies": ["base"],
    }
    base.update(over)
    return AgentConfig.model_validate(base)


def _mesh(responses: list[str], **over: object) -> EditorMesh:
    return EditorMesh.from_project(
        llm=MockLLMProvider(responses),
        root=Path("."),
        config=_config(**over),
    )


def test_run_pauses_before_publish() -> None:
    mesh = _mesh(_SCRIPT)
    out = mesh.run(EditorInput(task="ship the post"))
    assert out.status == "interrupted"
    assert out.pending is not None and out.pending.worker == "publish"
    assert out.thread_id


def test_parallel_branch_runs_both_workers() -> None:
    mesh = _mesh(_SCRIPT)
    out = mesh.run(EditorInput(task="ship the post"))
    workers = [s.worker for s in out.history]
    assert "draft" in workers and "factcheck" in workers  # parallel fan-out merged
    assert workers[0] == "plan"  # ordering preserved before the fan-out


def test_resume_approve_completes_and_publishes() -> None:
    mesh = _mesh(_SCRIPT)
    out = mesh.run(EditorInput(task="ship the post"))
    resumed = mesh.resume(out.thread_id or "", ApprovalDecision(action="approve"))
    assert resumed.status == "complete"
    assert resumed.final.startswith("PUBLISHED:")
    assert [s.worker for s in resumed.history][-1] == "publish"


def test_undeclared_worker_is_refused() -> None:
    # Supervisor picks a worker outside the declared roster -> capability violation.
    mesh = _mesh(["delete_everything"])
    with pytest.raises(CapabilityViolation):
        mesh.run(EditorInput(task="ship the post"))


def test_workers_must_match_config_roster() -> None:
    with pytest.raises(ValueError, match="workers"):
        _mesh(_SCRIPT, workers=["plan", "draft"])  # incomplete roster
