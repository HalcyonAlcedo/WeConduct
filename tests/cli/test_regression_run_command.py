import json
import sys
from pathlib import Path

from weconduct.application import CompilationWorkbenchService
from weconduct.cli import main as cli_main


def _build_success_project(project_path: Path, *, variable_name: str, value: int) -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name=f"Regression {variable_name}")
    service.save_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-batch",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-batch",
                    "expansion_role": "action:set_variables_batch",
                    "display_name": "Set Variables Batch",
                    "node_kind": "data.set_variables_batch",
                    "node_config": {
                        "variables": {
                            variable_name: value,
                        }
                    },
                    "position": {"x": 120, "y": 80},
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    service.save_project_as(project_path=project_path)


def _build_runtime_failed_project(project_path: Path) -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name="Regression Runtime Failure")
    service.save_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-http",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-http",
                    "expansion_role": "action:request",
                    "display_name": "HTTP Request",
                    "node_kind": "http.request",
                    "node_config": {
                        "method": "GET",
                        "url": "__INVALID_URL__",
                    },
                    "position": {"x": 180, "y": 120},
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    service.save_project_as(project_path=project_path)


def test_cli_regression_run_executes_multiple_projects_and_prints_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_a = tmp_path / "project-a.weconduct.json"
    project_b = tmp_path / "project-b.weconduct.json"
    _build_success_project(project_a, variable_name="answer_a", value=11)
    _build_success_project(project_b, variable_name="answer_b", value=22)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            str(project_a),
            str(project_b),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["succeeded_count"] == 2
    assert payload["summary"]["failed_count"] == 0
    assert payload["projects"][0]["result"]["status"] == "succeeded"
    assert payload["projects"][0]["execution_summary"]["status"] == "succeeded"
    assert payload["projects"][0]["result_summary"] == {
        "completed_node_count": 1,
        "failed_node_count": 0,
        "event_count": 3,
        "latest_event_kind": "session.completed",
    }
    assert payload["projects"][1]["result"]["variables"]["answer_b"] == 22


def test_cli_regression_run_returns_nonzero_when_any_project_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_ok = tmp_path / "project-ok.weconduct.json"
    project_bad = tmp_path / "project-bad.weconduct.json"
    _build_success_project(project_ok, variable_name="ok_value", value=7)

    service = CompilationWorkbenchService()
    service.create_project(project_name="Regression Bad")
    service.save_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    service.save_project_as(project_path=project_bad)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            str(project_ok),
            str(project_bad),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["succeeded_count"] == 1
    assert payload["summary"]["failed_count"] == 1
    assert payload["summary"]["primary_failure_reasons"] == ["source.empty"]
    assert payload["summary"]["failed_project_count_by_reason"] == {"source.empty": 1}
    assert payload["summary"]["failed_node_count_by_error_code"] == {}
    assert payload["summary"]["failed_node_count_by_kind"] == {}
    assert payload["summary"]["total_diagnostic_event_count"] == 2
    assert payload["summary"]["failed_projects"] == [
        {
            "project_file": str(project_bad.resolve()),
            "primary_failure_reason": "source.empty",
        }
    ]
    assert payload["projects"][1]["status"] == "failed"
    assert payload["projects"][1]["primary_failure_reason"] == "source.empty"
    assert payload["projects"][1]["failed_node_ids"] == []
    assert payload["projects"][1]["diagnostic_event_count"] == 2
    assert payload["projects"][1]["result_summary"] == {
        "completed_node_count": 0,
        "failed_node_count": 0,
        "event_count": 0,
        "latest_event_kind": None,
    }


def test_cli_regression_run_exposes_failed_node_summaries_for_runtime_failures(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_path = tmp_path / "project-runtime-failed.weconduct.json"
    _build_runtime_failed_project(project_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            str(project_path),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["projects"][0]["status"] == "failed"
    assert payload["projects"][0]["primary_failure_reason"] == "http.request_failed"
    assert payload["projects"][0]["failed_node_ids"] == ["node-http"]
    assert payload["projects"][0]["failed_node_summaries"] == [
        {
            "node_id": "node-http",
            "display_name": "HTTP Request",
            "node_kind": "http.request",
            "error_code": "http.request_failed",
            "input_snapshot": {
                "method": "GET",
                "url": "__INVALID_URL__",
            },
        }
    ]
    assert payload["summary"]["failed_node_count_by_error_code"] == {
        "http.request_failed": 1,
    }
    assert payload["summary"]["failed_node_count_by_kind"] == {
        "http.request": 1,
    }


def test_cli_regression_run_supports_project_directory_scan(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    projects_dir = tmp_path / "suite"
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_a = projects_dir / "project-a.weconduct.json"
    project_b = projects_dir / "project-b.weconduct.json"
    _build_success_project(project_a, variable_name="dir_a", value=31)
    _build_success_project(project_b, variable_name="dir_b", value=32)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            "--project-dir",
            str(projects_dir),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["succeeded_count"] == 2
    assert sorted(item["project_file"] for item in payload["projects"]) == [
        str(project_a.resolve()),
        str(project_b.resolve()),
    ]


def test_cli_regression_run_supports_manifest_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_a = tmp_path / "manifest-a.weconduct.json"
    project_b = tmp_path / "manifest-b.weconduct.json"
    manifest_path = tmp_path / "regression-manifest.json"
    _build_success_project(project_a, variable_name="manifest_a", value=41)
    _build_success_project(project_b, variable_name="manifest_b", value=42)
    manifest_path.write_text(
        json.dumps({"project_files": [str(project_a), str(project_b)]}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            "--manifest",
            str(manifest_path),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["succeeded_count"] == 2
    assert payload["projects"][0]["result"]["status"] == "succeeded"


def test_cli_regression_run_can_write_payload_to_output_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_path = tmp_path / "output-sample.weconduct.json"
    output_path = tmp_path / "regression-output.json"
    _build_success_project(project_path, variable_name="output_value", value=99)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
            str(project_path),
            "--output",
            str(output_path),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    stdout_payload = json.loads(captured.out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output_path.exists() is True
    assert file_payload == stdout_payload
    assert file_payload["summary"]["project_count"] == 1
    assert file_payload["projects"][0]["result"]["variables"]["output_value"] == 99


def test_cli_regression_run_fails_when_no_project_inputs_are_provided(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "regression-run",
        ],
    )

    try:
        cli_main.main()
    except ValueError as exc:
        assert str(exc) == "regression-run requires at least one project file input"
    else:
        raise AssertionError("expected ValueError for missing regression-run inputs")
