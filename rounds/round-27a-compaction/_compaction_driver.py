"""Round-27a compaction driver — validate orchestrator V2 S5a from downstream.

Compaction sits in the hot path of every completion, so this round checks the three
things that would matter most if it were wrong:

  - it does not fire on runs that do not need it (cost)
  - it never removes the recall-as-data block (security, the S2a contract)
  - a summariser failure degrades to a full prompt instead of failing the run
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

from lottie.governance.cost import TokenCapExceeded
from lottie.llm import Message, MockLLMProvider
from lottie.memory.compaction import SUMMARY_PREFIX
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


def _agent(*, enabled: bool, max_tokens: int = 200, keep_recent: int = 2) -> DigestAgent:
    cfg = AgentConfig.model_validate(
        {
            "provider": "mock/sim",
            "harness": {
                "compaction": {
                    "enabled": enabled,
                    "max_context_tokens": max_tokens,
                    "keep_recent": keep_recent,
                }
            },
        }
    )
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=MockLLMProvider(["summarised"] * 8),
        root=LAB_ROOT,
        config=cfg,
        enable_benchmarks=False,
    )


def _history(n: int) -> list[Message]:
    return [Message(role="user", content=f"turn {i} " + "x" * 400) for i in range(n)]


def _sent(agent: DigestAgent) -> list[Message]:
    return list(agent.llm.calls[-1])  # type: ignore[attr-defined]


# --- Case 1: config flows through instantiate_agent -------------------------
agent = _agent(enabled=True, max_tokens=500, keep_recent=3)
check(
    "1. harness.compaction config reaches the agent via instantiate_agent",
    agent._compaction_enabled and agent._max_context_tokens == 500 and agent._keep_recent == 3,
    f"max={agent._max_context_tokens}, keep={agent._keep_recent}",
)

# --- Case 2: OFF by default -------------------------------------------------
plain = instantiate_agent(
    DigestAgent,
    llm=MockLLMProvider(["ok"]),
    root=LAB_ROOT,
    config=AgentConfig.model_validate({"provider": "mock/sim"}),
    enable_benchmarks=False,
)
check("2. compaction is OFF by default", plain._compaction_enabled is False)

# --- Case 3: a short context is untouched and costs no extra call -----------
short = _agent(enabled=True, max_tokens=1_000_000)
short.complete(_history(10))
check(
    "3. a context under the threshold is not compacted (no wasted LLM call)",
    len(_sent(short)) == 10 and len(short.llm.calls) == 1,  # type: ignore[attr-defined]
    f"sent={len(_sent(short))}, llm_calls={len(short.llm.calls)}",  # type: ignore[attr-defined]
)

# --- Case 4: a long context IS compacted ------------------------------------
long_agent = _agent(enabled=True, max_tokens=200, keep_recent=2)
long_agent.complete(_history(12))
sent = _sent(long_agent)
check(
    "4. a context over the threshold is compacted to a summary + recent turns",
    len(sent) < 12 and any(m.content.startswith(SUMMARY_PREFIX) for m in sent),
    f"sent={len(sent)}",
)

# --- Case 5: recent turns survive verbatim ----------------------------------
check(
    "5. the most recent turns survive verbatim",
    sent[-1].content.startswith("turn 11"),
    f"last={sent[-1].content[:12]!r}",
)

# --- Case 6: the recall block is PINNED -------------------------------------
# Recall-as-data is the S2a anti-poisoning contract. Compacting it away would weaken a
# security guarantee with no signal.
pinned = _agent(enabled=True, max_tokens=200, keep_recent=2)
pinned._recall_prefix = "<recalled-notes>" + "y" * 400 + "</recalled-notes>"
pinned.complete(_history(12))
check(
    "6. the recall-as-data block survives compaction (S2a contract held)",
    any("recalled-notes" in m.content for m in _sent(pinned)),
)

# --- Case 7: summariser failure degrades, never fails the run ---------------
degraded = _agent(enabled=True, max_tokens=200, keep_recent=2)


def _boom(messages: list[Message]) -> str:
    raise RuntimeError("summariser down")


degraded._summarize_span = _boom  # type: ignore[method-assign]
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    degraded.complete(_history(12))
check(
    "7. a summariser failure sends the FULL context rather than failing the run",
    len(_sent(degraded)) == 12,
    f"sent={len(_sent(degraded))}",
)

# --- Case 8: a budget stop is NOT swallowed ---------------------------------
capped = _agent(enabled=True, max_tokens=200, keep_recent=2)


def _cap(messages: list[Message]) -> str:
    raise TokenCapExceeded("cap reached")


capped._summarize_span = _cap  # type: ignore[method-assign]
raised = False
try:
    capped.complete(_history(12))
except TokenCapExceeded:
    raised = True
check(
    "8. a token-cap trip propagates — compaction does not keep spending",
    raised,
    "TokenCapExceeded raised",
)

# --- Case 9: a real run end-to-end ------------------------------------------
runner = _agent(enabled=True, max_tokens=1_000_000)
out = runner.run(DigestAgentInput(query="what is a mesh"))
check(
    "9. a normal agent run still works with compaction enabled",
    out.result == "summarised",
    f"result={out.result!r}",
)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "27a",
            "slice": "V2 S5a — context compaction",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
