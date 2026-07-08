"""SentinelAgent — a downstream agent exercising orchestrator S6 agentic hygiene.

Makes TWO LLM completions per run (so `max_turns` has something to bound) and overrides
`_verify` to reject an output containing the banned marker "BAD" (a post-condition check that
fails the run before the output leaves the agent).
"""
from __future__ import annotations

from lottie.core import BaseAgent
from lottie.llm import Message

from .schema import SentinelAgentInput, SentinelAgentOutput


class SentinelAgent(BaseAgent[SentinelAgentInput, SentinelAgentOutput]):
    def _execute(self, data: SentinelAgentInput) -> SentinelAgentOutput:
        self.complete([Message(role="user", content=f"plan: {data.query}")])
        final = self.complete([Message(role="user", content=f"answer: {data.query}")])
        return SentinelAgentOutput(result=final.content)

    def _verify(self, data: SentinelAgentInput, output: SentinelAgentOutput) -> None:
        if "BAD" in output.result:
            raise ValueError("sentinel post-condition failed: banned content")
