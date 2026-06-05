"""Typed input/output models for ReviewerAgent."""
from __future__ import annotations
from pydantic import BaseModel


class ReviewerAgentInput(BaseModel):
    """Input for ReviewerAgent."""
    query: str


class ReviewerAgentOutput(BaseModel):
    """Output from ReviewerAgent."""
    result: str
