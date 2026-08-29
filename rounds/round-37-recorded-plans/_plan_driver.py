"""Round-37 recorded-plan driver — validate orchestrator E6 S1 from downstream.

A mesh routes DYNAMICALLY: the supervisor decides step N+1 from the result of step N. That
makes a multi-agent flow non-deterministic, so a mesh test today either hand-mocks the
router or cannot assert on the path taken at all.

Case 5 is the payoff: a replayed run is driven by a mock with NO responses left. Any
supervisor call would raise, so the assertion is that routing cost nothing.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from lottie.llm import MockLLMProvider
from lottie.mesh.local import LocalEngine
from lottie.mesh.plan import (
    PlanDivergence,
    PlanNotFound,
    PlanRecorder,
    list_plans,
    load_plan,
    plan_path,
    replay_route,
)
from lottie.mesh.schema import FINISH, MeshInput, MeshState, RouteDecision, StepResult


HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round37-"))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _nodes() -> dict[str, object]:
    def _make(name: str):  # type: ignore[no-untyped-def]
        def node(state: MeshState) -> MeshState:
            return state.with_step(StepResult(worker=name, result=f"{name}-out"))

        return node

    return {"draft": _make("draft"), "review": _make("review")}


def _mesh(root: Path | None, responses: list[str]):  # type: ignore[no-untyped-def]
    from lottie.mesh.base import MeshAgent

    agent = MeshAgent(
        MockLLMProvider(responses),
        nodes=_nodes(),  # type: ignore[arg-type]
        descriptions={"draft": "drafts", "review": "reviews"},
        enable_benchmarks=False,
    )
    agent.set_plans_root(root)
    return agent


try:
    # --- Case 1: a completed run records its plan ---------------------------
    _mesh(_SCRATCH, ["draft", "review", "FINISH"]).run(MeshInput(task="write it"))
    threads = list_plans(_SCRATCH, "MeshAgent")
    check(
        "1. a completed mesh run records the routing decisions it made",
        len(threads) == 1,
        f"plans={len(threads)}",
    )

    # --- Case 2: the plan matches the path taken ---------------------------
    plan = load_plan(_SCRATCH, "MeshAgent", threads[0])
    check(
        "2. the recorded plan matches the path actually taken",
        [s.workers for s in plan.steps] == [["draft"], ["review"]],
        f"steps={[s.workers for s in plan.steps]}",
    )

    # --- Case 3: the task text never reaches disk --------------------------
    raw = plan_path(_SCRATCH, "MeshAgent", threads[0]).read_text()
    check(
        "3. the plan stores a task HASH, never the task text",
        "write it" not in raw and plan.task_sha256,
        "hash-only, like the audit ledger",
    )

    # --- Case 4: a plan is bound to its task -------------------------------
    check(
        "4. a plan knows which task it belongs to",
        plan.matches("write it") and not plan.matches("a different task"),
    )

    # --- Case 5: replay makes ZERO supervisor calls ------------------------
    # The mock is given NO responses. Any routing call would raise, so reaching the end
    # proves the replay never asked.
    # One canned response that is NOT a valid worker: if replay ever asked the
    # supervisor, routing would raise CapabilityViolation rather than pass quietly.
    starved = MockLLMProvider(["NOT-A-WORKER"])
    replayed = LocalEngine().run(
        MeshState(task="write it"),
        nodes=_nodes(),  # type: ignore[arg-type]
        route=replay_route(plan, declared={"draft", "review"}),
        max_steps=8,
    )
    check(
        "5. a replayed run makes ZERO supervisor calls",
        [s.worker for s in replayed.state.history] == ["draft", "review"]
        and len(starved.calls) == 0,
        f"path={[s.worker for s in replayed.state.history]}",
    )

    # --- Case 6: divergence fails closed -----------------------------------
    diverged = False
    try:
        replay_route(plan, declared={"draft"})  # 'review' no longer declared
    except PlanDivergence:
        diverged = True
    check(
        "6. replaying against a changed worker roster fails LOUDLY",
        diverged,
        "a silent divergence looks like a reproduction and is not",
    )

    # --- Case 7: a parallel fan-out records as ONE step --------------------
    # The case that broke the first implementation: inferring from StepResult.step only
    # works on LangGraphEngine, which is the one that populates it.
    decisions = iter(
        [RouteDecision(next=FINISH, parallel=["draft", "review"]), RouteDecision(next=FINISH)]
    )
    recorder = PlanRecorder(lambda state: next(decisions))
    state = MeshState(task="t")
    recorder(state)
    recorder(state)
    check(
        "7. a parallel fan-out is recorded as ONE step, not two",
        [s.workers for s in recorder.plan("t").steps] == [["draft", "review"]],
        f"steps={[s.workers for s in recorder.plan('t').steps]}",
    )

    # --- Case 8: sequential steps stay separate ----------------------------
    seq = iter([RouteDecision(next="draft"), RouteDecision(next="review"),
                RouteDecision(next=FINISH)])
    rec2 = PlanRecorder(lambda state: next(seq))
    for _ in range(3):
        rec2(MeshState(task="t"))
    check(
        "8. sequential steps are recorded separately (LocalEngine leaves step=0)",
        [s.workers for s in rec2.plan("t").steps] == [["draft"], ["review"]],
        f"steps={[s.workers for s in rec2.plan('t').steps]}",
    )

    # --- Case 9: no plans root means no artefacts --------------------------
    clean = Path(tempfile.mkdtemp(prefix="round37-clean-"))
    _mesh(None, ["draft", "FINISH"]).run(MeshInput(task="t"))
    check(
        "9. a mesh with no plans root leaves no artefacts",
        list_plans(clean, "MeshAgent") == [],
    )

    # --- Case 10: a missing plan raises ------------------------------------
    missing = False
    try:
        load_plan(_SCRATCH, "MeshAgent", "never-ran")
    except PlanNotFound:
        missing = True
    check("10. loading a plan that was never recorded raises", missing)

    # --- Case 11: traversal is refused -------------------------------------
    blocked = False
    try:
        plan_path(_SCRATCH, "MeshAgent", "../../etc")
    except PlanDivergence:
        blocked = True
    check(
        "11. a traversing thread id cannot escape .lottie/plans/",
        blocked,
        "same guard as distill drafts and sessions",
    )

finally:
    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "37",
            "slice": "E6 S1 — recorded plans and replay",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
