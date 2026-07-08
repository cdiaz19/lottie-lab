"""Typed I/O for SentinelAgent."""
from __future__ import annotations
from pydantic import BaseModel


class SentinelAgentInput(BaseModel):
    query: str


class SentinelAgentOutput(BaseModel):
    result: str
