"""CuratorAgent unit tests (MockLLM). Rule-11 behaviour is exercised end-to-end in
rounds/round-15-capability; here we cover the agent's own contract."""

from __future__ import annotations

from lottie.governance.capability import CapabilityDenied, build_capability_gate
from lottie.llm import MockLLMProvider

from agents.curator.agent import CuratorAgent
from agents.curator.schema import CuratorAgentInput


def _agent() -> CuratorAgent:
    return CuratorAgent(MockLLMProvider(["x"]), enable_benchmarks=False)


def test_calls_summarizer_and_returns_result() -> None:
    out = _agent().run(CuratorAgentInput(text="a report"))
    assert out.result == "a report"


def test_declared_capability_allows_the_skill_call() -> None:
    agent = _agent()
    agent.set_capability_gate(build_capability_gate(capabilities=["summarizer"]))
    assert agent.run(CuratorAgentInput(text="ok")).result == "ok"


def test_undeclared_capability_blocks_the_skill_call() -> None:
    agent = _agent()
    agent.set_capability_gate(build_capability_gate(capabilities=["nope"]))
    try:
        agent.run(CuratorAgentInput(text="ok"))
    except CapabilityDenied as exc:
        assert "summarizer" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected CapabilityDenied")


def test_empty_capabilities_is_unenforced() -> None:
    agent = _agent()
    agent.set_capability_gate(build_capability_gate(capabilities=[]))
    assert agent.run(CuratorAgentInput(text="ok")).result == "ok"
