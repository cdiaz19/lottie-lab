"""Unit tests for SummarizerSkill (deterministic — no LLM)."""
from __future__ import annotations
import pytest
from pydantic import ValidationError
from skills.summarizer.schema import SummarizerSkillInput, SummarizerSkillOutput
from skills.summarizer.skill import SummarizerSkill


def test_summarizer_happy_path() -> None:
    skill = SummarizerSkill()
    result = skill.run(SummarizerSkillInput(text="hello"))
    assert isinstance(result, SummarizerSkillOutput)
    assert result.result == "hello"


def test_summarizer_handles_empty_text() -> None:
    skill = SummarizerSkill()
    result = skill.run(SummarizerSkillInput(text=""))
    assert isinstance(result, SummarizerSkillOutput)
    assert result.result == ""


def test_summarizer_rejects_wrong_type() -> None:
    with pytest.raises(ValidationError):
        SummarizerSkillInput(text=123)  # type: ignore[arg-type]
