"""CuratorAgent — a downstream agent that CALLS a skill inside `_execute`.

Exists to exercise orchestrator rule 11 (per-skill-call capability enforcement, S1)
from a downstream project: the agent invokes `SummarizerSkill` (capability name
"summarizer"), so whether the call is allowed depends on the agent's declared
`capabilities` list in config.yaml.
"""
from __future__ import annotations

from lottie.core import BaseAgent
from lottie.llm import LLMProvider

from skills.summarizer.schema import SummarizerSkillInput
from skills.summarizer.skill import SummarizerSkill

from .schema import CuratorAgentInput, CuratorAgentOutput


class CuratorAgent(BaseAgent[CuratorAgentInput, CuratorAgentOutput]):
    """Calls SummarizerSkill in `_execute` — gated by declared capabilities (rule 11)."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        enable_benchmarks: bool | None = None,
    ) -> None:
        super().__init__(llm, enable_benchmarks=enable_benchmarks)
        self._summarizer = SummarizerSkill(enable_benchmarks=enable_benchmarks)

    def _execute(self, data: CuratorAgentInput) -> CuratorAgentOutput:
        out = self._summarizer.run(SummarizerSkillInput(text=data.text))
        return CuratorAgentOutput(result=out.result)
