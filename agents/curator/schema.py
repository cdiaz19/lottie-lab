"""Typed input/output models for CuratorAgent."""
from __future__ import annotations
from pydantic import BaseModel


class CuratorAgentInput(BaseModel):
    """Input for CuratorAgent."""
    text: str


class CuratorAgentOutput(BaseModel):
    """Output from CuratorAgent."""
    result: str
