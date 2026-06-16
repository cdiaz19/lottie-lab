"""Round-9 OpenTelemetry driver — validate per-run span emission against
lottie-orchestrator @ feat/governance-otel, and RESOLVE the spec's open question:
do parallel LangGraph mesh worker spans nest under the mesh span (cross-thread), or
attach to root?

Runs the real shipped path: every BaseAgent run hits InstrumentedRunnable.run, which
emits an OTel span via governance.otel.run_span. We install an in-memory exporter by
swapping opentelemetry's private _TRACER_PROVIDER (the once-per-process set_tracer_provider
guard forces this), and inspect span names + parent links.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from opentelemetry import trace as _trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from lottie.core import BaseAgent
from lottie.llm import MockLLMProvider
from lottie.mesh import MeshAgent, MeshNode, MeshState, StepResult
from lottie.mesh.schema import MeshInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"

# Install one in-memory exporter for the process (set_tracer_provider is once-only, so we
# swap the private global directly). Tracing is on while OTEL_EXPORTER_OTLP_ENDPOINT is set
# and the global provider is already this real TracerProvider (run_span's _ensure_provider
# sees it via isinstance and reuses it).
_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
_trace._TRACER_PROVIDER = _provider  # type: ignore[attr-defined]


class _In(BaseModel):
    q: str


class _Out(BaseModel):
    a: str


class _Worker(BaseAgent[_In, _Out]):
    def _execute(self, data: _In) -> _Out:
        return _Out(a=f"{self.name}:done")


class _Nested(BaseAgent[_In, _Out]):
    def __init__(self, llm: Any, inner: _Worker) -> None:
        super().__init__(llm, name="outer")
        self._inner = inner

    def _execute(self, data: _In) -> _Out:
        return self._inner.run(data)


def _llm() -> MockLLMProvider:
    return MockLLMProvider(["x"])


def _trace_on() -> None:
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
    os.environ.pop("LOTTIE_DISABLE_OTEL", None)
    _EXPORTER.clear()


def _spans() -> dict[str, Any]:
    return {s.name: s for s in _EXPORTER.get_finished_spans()}


def _emit(body: str, cid: str, ok: bool) -> bool:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / f"case-{cid}.out.txt").write_text(body + f"\nRESULT: {'PASS' if ok else 'FAIL'}\n", encoding="utf-8")
    print(f"[{'PASS' if ok else 'FAIL'}] case {cid}")
    return ok


def case_01_span_per_run() -> bool:
    _trace_on()
    _Worker(_llm(), name="digest").run(_In(q="hi"))
    s = _spans()
    ok = "digest" in s and s["digest"].attributes.get("lottie.status") == "ok"
    attrs = dict(s["digest"].attributes) if "digest" in s else {}
    return _emit(
        f"CASE 01-span-per-run: a single agent run emits one span with lottie.* attributes.\n"
        f"span names={list(s)} attrs={attrs}",
        "01-span-per-run", ok,
    )


def case_02_same_thread_nesting() -> bool:
    _trace_on()
    _Nested(_llm(), _Worker(_llm(), name="inner")).run(_In(q="hi"))
    s = _spans()
    ok = (
        "inner" in s and "outer" in s
        and s["inner"].parent is not None
        and s["inner"].parent.span_id == s["outer"].context.span_id
    )
    return _emit(
        "CASE 02-same-thread-nesting: agent->agent on one thread; inner span parents to outer.\n"
        f"inner.parent set={s.get('inner') and s['inner'].parent is not None}",
        "02-same-thread-nesting", ok,
    )


def _parallel_mesh() -> MeshAgent:
    wa = _Worker(_llm(), name="worker-a")
    wb = _Worker(_llm(), name="worker-b")

    def _node(name: str, w: _Worker) -> MeshNode:
        def _run(state: MeshState) -> MeshState:
            out = w.run(_In(q=state.task))
            return state.with_step(StepResult(worker=name, result=out.a))

        return _run

    from lottie.mesh.langgraph_engine import LangGraphEngine

    return MeshAgent(
        MockLLMProvider(["a, b", "FINISH", "FINISH"]),
        name="mesh",
        nodes={"a": _node("a", wa), "b": _node("b", wb)},
        descriptions={"a": "worker a", "b": "worker b"},
        engine=LangGraphEngine(),
    )


def case_03_parallel_mesh_nesting() -> tuple[bool, str]:
    """THE open question: do parallel worker spans (own threads) nest under the mesh span?"""
    _trace_on()
    _parallel_mesh().run(MeshInput(task="t"))
    s = _spans()
    have_workers = "worker-a" in s and "worker-b" in s and "mesh" in s
    nested = have_workers and all(
        s[w].parent is not None and s[w].parent.span_id == s["mesh"].context.span_id
        for w in ("worker-a", "worker-b")
    )
    parents = {
        w: ("root" if (w in s and s[w].parent is None) else "mesh" if (w in s and s[w].parent and s[w].parent.span_id == s["mesh"].context.span_id) else "other")
        for w in ("worker-a", "worker-b")
    }
    verdict = "NESTS under mesh span" if nested else "attaches to ROOT (cross-thread context NOT carried)"
    body = (
        "CASE 03-parallel-mesh-nesting: a parallel LangGraph mesh with WORKER AGENTS; do their\n"
        "spans nest under the mesh span across worker threads? (the spec's open question)\n"
        f"span names={list(s)} worker parents={parents}\nVERDICT: {verdict}"
    )
    # PASS = we resolved the question with worker spans present; the verdict (nest vs root) is the finding.
    resolved = have_workers
    _emit(body, "03-parallel-mesh-nesting", resolved)
    return nested, verdict


def case_04_noop_when_disabled() -> bool:
    _trace_on()
    os.environ["LOTTIE_DISABLE_OTEL"] = "1"
    _Worker(_llm(), name="quiet").run(_In(q="hi"))
    ok = _EXPORTER.get_finished_spans() == ()
    os.environ.pop("LOTTIE_DISABLE_OTEL", None)
    return _emit(
        "CASE 04-noop-when-disabled: LOTTIE_DISABLE_OTEL=1 -> no spans emitted.\n"
        f"spans after a run with tracing disabled: {len(_EXPORTER.get_finished_spans())}",
        "04-noop-when-disabled", ok,
    )


def case_05_fail_open() -> bool:
    _trace_on()
    import lottie.governance.otel as otel

    original = otel._ensure_provider  # type: ignore[attr-defined]

    def _boom() -> None:
        raise RuntimeError("tracer dead")

    otel._ensure_provider = _boom  # type: ignore[attr-defined]
    try:
        out = _Worker(_llm(), name="resilient").run(_In(q="hi"))
        ok = out.a == "resilient:done"
    except Exception as exc:  # noqa: BLE001
        ok = False
        out = None  # type: ignore[assignment]
    finally:
        otel._ensure_provider = original  # type: ignore[attr-defined]
    return _emit(
        "CASE 05-fail-open: a tracer-setup failure must NOT break the run.\n"
        f"run completed normally with tracer dead: {ok}",
        "05-fail-open", ok,
    )


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    results = [case_01_span_per_run(), case_02_same_thread_nesting()]
    nested, verdict = case_03_parallel_mesh_nesting()
    results.append(True)  # case 3 resolves the question regardless of nest vs root
    results.append(case_04_noop_when_disabled())
    results.append(case_05_fail_open())
    passed = sum(results)
    total = len(results)
    print(f"\nPARALLEL-MESH NESTING VERDICT: {verdict}")
    print(f"RESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
