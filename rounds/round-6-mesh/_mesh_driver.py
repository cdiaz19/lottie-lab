"""Round-6 in-process driver: prove routing -> parallel -> HITL -> resume -> time-travel.

The CLI cannot script the supervisor (build_provider always returns LiteLLMProvider),
so the full mesh cycle is exercised here with a scripted MockLLMProvider, in one
process (the in-memory checkpointer is process-local). Prints a PASS/FAIL summary.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lottie.llm import MockLLMProvider
from lottie.mesh.schema import ApprovalDecision
from lottie.project.config import AgentConfig

from agents.editor.agent import EditorMesh
from agents.editor.schema import EditorInput

_SCRIPT = ["plan", "draft, factcheck", "review", "publish", "FINISH", "FINISH"]


def _build() -> EditorMesh:
    config = AgentConfig.model_validate(
        {
            "provider": "mock/x",
            "workers": ["plan", "draft", "factcheck", "review", "publish"],
            "interrupt_before": ["publish"],
            "policies": ["base"],
        }
    )
    return EditorMesh.from_project(
        llm=MockLLMProvider(_SCRIPT), root=Path("."), config=config
    )


def main() -> int:
    mesh = _build()

    # A+B: route + parallel fan-out, pausing before the publish gate.
    out = mesh.run(EditorInput(task="ship the launch post"))
    workers = [s.worker for s in out.history]
    print(f"run status      = {out.status}")
    print(f"history workers = {workers}")
    print(f"pending worker  = {out.pending.worker if out.pending else None}")
    print(f"thread_id       = {out.thread_id}")

    ok = out.status == "interrupted"
    ok = ok and out.pending is not None and out.pending.worker == "publish"
    ok = ok and "draft" in workers and "factcheck" in workers  # parallel branches

    # C: approve -> resume -> complete.
    resumed = mesh.resume(out.thread_id or "", ApprovalDecision(action="approve"))
    print(f"resumed status  = {resumed.status}")
    print(f"final           = {resumed.final}")
    ok = ok and resumed.status == "complete" and resumed.final.startswith("PUBLISHED:")

    # D: time-travel -- the engine exposes the checkpoint timeline for the thread.
    engine = mesh._engine
    history = engine.history(  # type: ignore[attr-defined]
        out.thread_id or "", nodes=mesh._nodes, route=mesh._route_fn()
    )
    print(f"checkpoints     = {len(history)}")
    ok = ok and len(history) > 0

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
