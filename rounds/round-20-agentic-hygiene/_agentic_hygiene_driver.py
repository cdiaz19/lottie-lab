"""Round-20 agentic-hygiene driver — validate orchestrator S6 (max_turns + _verify hook)
from a downstream project.

Runs the real shipped path in-process: `instantiate_agent(SentinelAgent, config=...)` attaches
the completion cap (config.max_turns → set_run_limits) and the agent's `_verify` override.
SentinelAgent makes 2 completions/run and rejects outputs containing "BAD".
"""

from __future__ import annotations

import sys
from pathlib import Path

from lottie.core.base_agent import TurnLimitExceeded
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.sentinel.agent import SentinelAgent
from agents.sentinel.schema import SentinelAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent


def _config(**kw: object) -> AgentConfig:
    return AgentConfig.model_validate({"provider": "mock/sim", **kw})


def _sentinel(responses: list[str], **cfg: object) -> SentinelAgent:
    return instantiate_agent(  # type: ignore[return-value]
        SentinelAgent,
        llm=MockLLMProvider(responses),
        root=LAB_ROOT,
        config=_config(**cfg),
        enable_benchmarks=False,
    )


def _emit(name: str, detail: str, ok: bool) -> bool:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / f"case-{name}.out.txt").write_text(
        f"{'PASS' if ok else 'FAIL'} — {name}\n\n{detail}\n", encoding="utf-8"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def case_01_max_turns_caps_completions() -> bool:
    a = _sentinel(["one", "two"], max_turns=1)  # 2 completions vs cap 1
    capped = False
    try:
        a.run(SentinelAgentInput(query="x"))
    except TurnLimitExceeded:
        capped = True
    return _emit(
        "01-max-turns-cap",
        f"max_turns=1, agent makes 2 completions -> TurnLimitExceeded on the 2nd. capped={capped}",
        capped,
    )


def case_02_under_cap_runs() -> bool:
    a = _sentinel(["one", "two"], max_turns=5)
    out = a.run(SentinelAgentInput(query="x"))
    return _emit(
        "02-under-cap",
        f"max_turns=5, 2 completions -> run completes. result={out.result!r}",
        out.result == "two",
    )


def case_03_verify_rejects_bad_output() -> bool:
    a = _sentinel(["one", "BAD answer"], max_turns=5)  # final output contains BAD
    rejected = False
    try:
        a.run(SentinelAgentInput(query="x"))
    except ValueError:
        rejected = True
    return _emit(
        "03-verify-rejects",
        f"_verify rejects output containing 'BAD' -> run fails fail-closed. rejected={rejected}",
        rejected,
    )


def case_04_verify_passes_clean_output() -> bool:
    a = _sentinel(["one", "clean answer"], max_turns=5)
    out = a.run(SentinelAgentInput(query="x"))
    return _emit(
        "04-verify-passes",
        f"_verify passes a clean output -> run succeeds. result={out.result!r}",
        out.result == "clean answer",
    )


def main() -> int:
    cases = [
        case_01_max_turns_caps_completions,
        case_02_under_cap_runs,
        case_03_verify_rejects_bad_output,
        case_04_verify_passes_clean_output,
    ]
    results = [c() for c in cases]
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
