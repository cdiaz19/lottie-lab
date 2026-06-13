"""EditorMesh — content pipeline: plan -> [draft, factcheck] -> review -> publish (HITL)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lottie.llm import LLMProvider
from lottie.mesh import MeshAgent, MeshEngine, MeshNode, MeshState, StepResult
from lottie.mesh.errors import MeshError
from lottie.project.config import AgentConfig

_DESCRIPTIONS = {
    "plan": "Outline a short plan for the task.",
    "draft": "Write a draft answer for the task.",
    "factcheck": "Check the draft's facts.",
    "review": "Review the drafted work and approve it.",
    "publish": "Publish/finalize the reviewed answer.",
}

_Render = Callable[[MeshState], str]


def _worker(name: str, render: _Render) -> MeshNode:
    """Build a pure, deterministic worker node (no LLM call)."""

    def _run(state: MeshState) -> MeshState:
        return state.with_step(StepResult(worker=name, result=render(state)))

    return _run


class EditorMesh(MeshAgent):
    """Reference content-pipeline mesh with a HITL gate before `publish`."""

    @classmethod
    def from_project(
        cls,
        *,
        llm: LLMProvider,
        root: Path,
        config: AgentConfig,
        enable_benchmarks: bool | None = None,
    ) -> EditorMesh:
        declared = set(config.workers)
        if declared and declared != set(_DESCRIPTIONS):
            raise ValueError(
                f"editor config.yaml workers {sorted(declared)} "
                f"do not match the mesh's worker adapters {sorted(_DESCRIPTIONS)}"
            )
        if not set(config.interrupt_before) <= set(_DESCRIPTIONS):
            raise ValueError(
                f"editor config.yaml interrupt_before {sorted(config.interrupt_before)} "
                f"contains workers not in the mesh's adapters {sorted(_DESCRIPTIONS)}"
            )

        # interrupt_before requires the checkpointed LangGraph engine. Import it
        # lazily so `import agents.editor.agent` works without the [mesh] extra.
        engine: MeshEngine | None = None
        if config.interrupt_before:
            try:
                from lottie.mesh.langgraph_engine import LangGraphEngine
            except ImportError as exc:
                raise MeshError(
                    "editor interrupt_before requires the [mesh] extra: "
                    "pip install lottie-orchestrator[mesh]"
                ) from exc
            engine = LangGraphEngine(interrupt_before=config.interrupt_before)

        mesh = cls(
            llm,
            nodes={},
            descriptions=_DESCRIPTIONS,
            engine=engine,
            enable_benchmarks=enable_benchmarks,
        )
        mesh._nodes = {
            "plan": _worker("plan", lambda s: f"PLAN: {s.task}"),
            "draft": _worker("draft", lambda s: f"DRAFT: {s.task}"),
            "factcheck": _worker("factcheck", lambda _s: "FACTCHECK: ok"),
            "review": _worker("review", lambda _s: "REVIEW: approved"),
            "publish": _worker("publish", lambda s: f"PUBLISHED: {s.task}"),
        }
        return mesh
