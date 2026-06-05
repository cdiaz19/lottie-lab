"""Integration tests for DigestAgent (MockLLMProvider — no real LLM)."""
from __future__ import annotations
from lottie.llm import MockLLMProvider
from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput, DigestAgentOutput


def test_digest_returns_llm_content() -> None:
    agent = DigestAgent(llm=MockLLMProvider(["hello from mock"]))
    result = agent.run(DigestAgentInput(query="hi"))
    assert isinstance(result, DigestAgentOutput)
    assert result.result == "hello from mock"


def test_digest_makes_one_llm_call() -> None:
    mock = MockLLMProvider(["ok"])
    agent = DigestAgent(llm=mock)
    agent.run(DigestAgentInput(query="hi"))
    assert len(mock.calls) == 1


def test_digest_handles_empty_query() -> None:
    agent = DigestAgent(llm=MockLLMProvider(["fallback"]))
    result = agent.run(DigestAgentInput(query=""))
    assert isinstance(result, DigestAgentOutput)
    assert result.result == "fallback"


def test_digest_rejects_empty_query() -> None:
    import pytest
    from lottie.llm import MockLLMProvider
    agent = DigestAgent(llm=MockLLMProvider(["should not reach"]))
    with pytest.raises(ValueError, match="query cannot be empty"):
        agent.run(DigestAgentInput(query=""))


def test_digest_rejects_whitespace_query() -> None:
    import pytest
    from lottie.llm import MockLLMProvider
    agent = DigestAgent(llm=MockLLMProvider(["should not reach"]))
    with pytest.raises(ValueError, match="query cannot be empty"):
        agent.run(DigestAgentInput(query="   "))

def test_digest_handles_empty_query() -> None:
    import pytest
    from lottie.llm import MockLLMProvider
    agent = DigestAgent(llm=MockLLMProvider(["fallback"]))
    with pytest.raises(ValueError, match="query cannot be empty"):
        agent.run(DigestAgentInput(query=""))
