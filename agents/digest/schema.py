"""Typed input/output models for DigestAgent."""
from __future__ import annotations
from pydantic import BaseModel


class DigestAgentInput(BaseModel):
    """Input for DigestAgent."""
    query: str


class DigestAgentOutput(BaseModel):
    """Output from DigestAgent."""
    result: str
