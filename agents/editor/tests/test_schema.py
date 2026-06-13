from __future__ import annotations

from lottie.mesh.schema import MeshInput, MeshOutput

from agents.editor.schema import EditorInput, EditorOutput


def test_editor_io_are_mesh_models() -> None:
    assert issubclass(EditorInput, MeshInput)
    assert issubclass(EditorOutput, MeshOutput)
    # task is required; max_steps defaults
    inp = EditorInput(task="ship the post")
    assert inp.task == "ship the post"
    assert inp.max_steps >= 1
