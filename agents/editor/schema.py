"""Typed I/O for the editor mesh (discovery-named aliases over mesh models)."""

from __future__ import annotations

from lottie.mesh.schema import MeshInput, MeshOutput


class EditorInput(MeshInput):
    """Task input for the editor content-pipeline mesh."""


class EditorOutput(MeshOutput):
    """Final answer + step history from the editor mesh."""
