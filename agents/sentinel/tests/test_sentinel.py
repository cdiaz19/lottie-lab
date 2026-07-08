"""SentinelAgent unit tests (MockLLM). S6 rails are exercised end-to-end in round-20."""
from __future__ import annotations

import pytest

from lottie.core.base_agent import TurnLimitExceeded
from lottie.llm import MockLLMProvider

from agents.sentinel.agent import SentinelAgent
from agents.sentinel.schema import SentinelAgentInput


def _agent(responses: list[str]) -> SentinelAgent:
    return SentinelAgent(MockLLMProvider(responses), enable_benchmarks=False)


def test_runs_two_completions_and_returns_final() -> None:
    out = _agent(["plan", "answer"]).run(SentinelAgentInput(query="q"))
    assert out.result == "answer"


def test_max_turns_caps_completions() -> None:
    agent = _agent(["one", "two"])
    agent.set_run_limits(max_turns=1)
    with pytest.raises(TurnLimitExceeded):
        agent.run(SentinelAgentInput(query="q"))


def test_verify_rejects_banned_output() -> None:
    with pytest.raises(ValueError, match="post-condition"):
        _agent(["one", "BAD answer"]).run(SentinelAgentInput(query="q"))
