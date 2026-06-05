"""Integration tests for ReviewerAgent (MockLLMProvider — no real LLM)."""
from __future__ import annotations
from lottie.llm import MockLLMProvider
from agents.reviewer.agent import ReviewerAgent
from agents.reviewer.schema import ReviewerAgentInput, ReviewerAgentOutput


def test_reviewer_returns_llm_content() -> None:
    agent = ReviewerAgent(llm=MockLLMProvider(["hello from mock"]))
    result = agent.run(ReviewerAgentInput(query="hi"))
    assert isinstance(result, ReviewerAgentOutput)
    assert result.result == "hello from mock"


def test_reviewer_makes_one_llm_call() -> None:
    mock = MockLLMProvider(["ok"])
    agent = ReviewerAgent(llm=mock)
    agent.run(ReviewerAgentInput(query="hi"))
    assert len(mock.calls) == 1


def test_reviewer_handles_empty_query() -> None:
    agent = ReviewerAgent(llm=MockLLMProvider(["fallback"]))
    result = agent.run(ReviewerAgentInput(query=""))
    assert isinstance(result, ReviewerAgentOutput)
    assert result.result == "fallback"
