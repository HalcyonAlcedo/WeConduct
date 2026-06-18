import json
import sys
from pathlib import Path

from weconduct.application import CompilationWorkbenchService
from weconduct.cli import main as cli_main


def _build_python_project_file(project_path: Path) -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name="CLI Run Project Smoke")
    service.save_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-python",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-python",
                    "expansion_role": "action:run_python",
                    "display_name": "Run Python",
                    "node_kind": "python.run",
                    "node_config": {
                        "code": "result = 42\nresult_variable = 'answer'\n",
                    },
                    "position": {"x": 120, "y": 80},
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    service.save_project_as(project_path=project_path)


def test_cli_run_project_opens_project_file_and_executes_runtime(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_path = tmp_path / "cli-run-project.weconduct.json"
    _build_python_project_file(project_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "run-project",
            str(project_path),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["project"]["project_name"] == "CLI Run Project Smoke"
    assert payload["runtime_session"]["status"] == "completed"
    assert payload["result"]["status"] == "succeeded"
    assert payload["result"]["outputs"]["node-python"]["result"] == 42
    assert payload["result"]["variables"]["answer"] == 42
    assert payload["execution_summary"]["status"] == "succeeded"
    assert payload["execution_summary"]["node_status_counts"]["completed"] == 1
    assert payload["runtime_preview_summary"]["scheduler_mode"] == "legacy_sequence"
