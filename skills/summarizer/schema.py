"""Typed input/output models for SummarizerSkill."""
from __future__ import annotations
from pydantic import BaseModel


class SummarizerSkillInput(BaseModel):
    """Input for SummarizerSkill."""
    text: str


class SummarizerSkillOutput(BaseModel):
    """Output from SummarizerSkill."""
    result: str
