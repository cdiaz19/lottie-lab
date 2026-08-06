"""Round-34 context-compiler driver — validate orchestrator E4 S1 from downstream.

E4 gave message assembly an ordering authority, a cross-source budget, and provenance.
The behavioural claim is that **nothing changes for existing agents**: `complete(messages)`
keeps its signature and a prompt made only of pinned sources comes out byte-identical.

Cases 5-8 exercise the drop policy with a synthetic DROPPABLE source, because every
source the orchestrator ships today is pinned — so the policy is real but not yet
reachable through a shipped agent. Verifying it here is what stops it rotting before
knowledge is wired in as a source.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

from lottie.context.compiler import StaticSource, compile_context
from lottie.governance.cost import TokenCapExceeded
from lottie.llm import Message, MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _agent(**cfg: object) -> DigestAgent:
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=MockLLMProvider(["an answer"] * 4),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim", **cfg}),
        enable_benchmarks=False,
    )


def _sent(agent: DigestAgent) -> list[Message]:
    return list(agent.llm.calls[-1])  # type: ignore[attr-defined]


def _msgs(n: int, tag: str) -> list[Message]:
    return [Message(role="system", content=f"{tag}{i}".ljust(400, "x")) for i in range(n)]


def _src(name: str, order: int, n: int, *, pinned: bool = False) -> StaticSource:
    return StaticSource(name, order, _msgs(n, name), pinned=pinned)


# --- Case 1: an ordinary agent is byte-identical ----------------------------
agent = _agent()
agent.run(DigestAgentInput(query="what is a mesh"))
sent = _sent(agent)
check(
    "1. an ordinary agent's prompt is unchanged by the compiler",
    len(sent) == 2 and sent[-1].content == "what is a mesh",
    f"messages={len(sent)}",
)

# --- Case 2: recall is ordered ahead of the agent's messages ----------------
# Not a hardcoded prepend any more — an ordering authority (recall 20, agent 90).
recalled = _agent()
recalled._recall_prefix = "<recalled-notes>prefer backoff</recalled-notes>"
recalled.complete([Message(role="user", content="task")])
check(
    "2. recall is assembled ahead of the agent's messages, by declared order",
    "recalled-notes" in _sent(recalled)[0].content,
    "recall first",
)

# --- Case 3: recall is declared PINNED --------------------------------------
# S2a's anti-poisoning contract is a SOURCE property now, not a role check.
pinning = {s.name: s.pinned for s in recalled._context_sources([])}
check(
    "3. recall and the agent's messages are both pinned sources",
    pinning.get("recall") is True and pinning.get("agent") is True,
    f"pinning={pinning}",
)

# --- Case 4: provenance is queryable ----------------------------------------
result = compile_context([_src("knowledge", 10, 3), _src("task", 90, 1, pinned=True)])
by_name = {c.name: c for c in result.contributions}
check(
    "4. provenance answers 'which source filled the window?'",
    by_name["knowledge"].tokens == 300 and by_name["task"].tokens == 100,
    f"knowledge={by_name['knowledge'].tokens}, task={by_name['task'].tokens}",
)

# --- Case 5: the drop policy gives up the LOWEST-order droppable source -----
# Lowest order == furthest from the task == least contextually relevant.
result = compile_context(
    [_src("knowledge", 10, 20), _src("task", 90, 1, pinned=True)], max_tokens=150
)
check(
    "5. over budget, the lowest-order droppable source is given up first",
    result.dropped == ["knowledge"],
    f"dropped={result.dropped}",
)

# --- Case 6: a PINNED source is never dropped -------------------------------
result = compile_context([_src("recall", 20, 20, pinned=True)], max_tokens=10)
check(
    "6. a pinned source is never dropped, even far over budget",
    result.dropped == [] and len(result.messages) == 20,
    f"dropped={result.dropped}",
)

# --- Case 7: dropping stops as soon as it is under budget ------------------
# The decision compaction could not make before: give up ONE source, not all.
result = compile_context(
    [_src("a", 10, 10), _src("b", 20, 1), _src("task", 90, 1, pinned=True)],
    max_tokens=250,
)
check(
    "7. dropping stops once under budget rather than dropping everything it could",
    result.dropped == ["a"],
    f"dropped={result.dropped}",
)

# --- Case 8: summarising is preferred over dropping ------------------------
result = compile_context(
    [_src("knowledge", 10, 20), _src("task", 90, 1, pinned=True)],
    max_tokens=150,
    summarize=lambda ms: f"summary of {len(ms)}",
)
check(
    "8. a summariser is preferred over outright dropping",
    result.dropped == [] and any("[compacted knowledge]" in m.content for m in result.messages),
    "summarised, not dropped",
)

# --- Case 9: no LLM call when under the ceiling ----------------------------
calls: list[int] = []
compile_context(
    [_src("a", 10, 1)], max_tokens=100_000, summarize=lambda ms: calls.append(len(ms)) or "s"
)
check(
    "9. nothing is summarised when the prompt already fits (no wasted LLM call)",
    calls == [],
    f"summariser_calls={len(calls)}",
)

# --- Case 10: an assembly failure degrades, never fails the run -----------
degraded = _agent()


def _boom(messages: list[Message]) -> list[StaticSource]:
    raise RuntimeError("assembly down")


degraded._context_sources = _boom  # type: ignore[method-assign]
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    out = degraded.run(DigestAgentInput(query="q"))
check(
    "10. an assembly failure sends the prompt as-is rather than failing the run",
    out.result == "an answer" and len(_sent(degraded)) == 2,
    f"result={out.result!r}",
)

# --- Case 11: a budget stop during assembly PROPAGATES ---------------------
# Summarisation spends tokens. If a cap trip there were swallowed by the same handler
# that tolerates an assembly outage, the run would keep spending past its ceiling.
capped = _agent()


def _cap(messages: list[Message]) -> list[StaticSource]:
    raise TokenCapExceeded("cap reached")


capped._context_sources = _cap  # type: ignore[method-assign]
raised = False
try:
    capped.run(DigestAgentInput(query="q"))
except TokenCapExceeded:
    raised = True
check("11. a budget stop during assembly propagates, never swallowed", raised)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "34",
            "slice": "E4 S1 — Context Compiler",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
