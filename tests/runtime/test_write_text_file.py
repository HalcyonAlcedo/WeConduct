from __future__ import annotations

from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


class _DisplayOnlyValue:
    def __str__(self) -> str:
        return "display-only"


def _execute_write(path, content: object) -> dict:
    return RuntimeExecutorRegistry().execute(
        "file.write_text_file",
        {
            "node_id": "write-text-file-1",
            "node_kind": "file.write_text_file",
            "node_config": {
                "path": str(path),
                "content": content,
            },
        },
        RuntimeContext(allowed_path_roots=(path.parent,)),
    )


def test_write_text_file_preserves_string_content(tmp_path) -> None:
    target = tmp_path / "text.txt"

    result = _execute_write(target, "plain text")

    assert result["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "plain text"


def test_write_text_file_formats_json_object(tmp_path) -> None:
    target = tmp_path / "payload.txt"

    result = _execute_write(target, {"name": "WeConduct", "items": [1, 2]})

    assert result["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == (
        '{\n  "name": "WeConduct",\n  "items": [\n    1,\n    2\n  ]\n}'
    )


def test_write_text_file_uses_string_representation_for_non_json_object(tmp_path) -> None:
    target = tmp_path / "object.txt"

    result = _execute_write(target, _DisplayOnlyValue())

    assert result["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "display-only"


def test_write_text_file_draft_accepts_arbitrary_runtime_content() -> None:
    draft = CompilationWorkbenchService().build_graph_node_draft(
        resource_key="file.write_text_file"
    )

    assert draft["parameter_schema"]["content"]["type"] == "any"
