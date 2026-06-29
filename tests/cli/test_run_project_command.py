import json
import sys
from pathlib import Path

from weconduct.application import CompilationWorkbenchService
from weconduct.cli import main as cli_main


def _build_project_file(project_path: Path) -> None:
    service = CompilationWorkbenchService()
    service.create_project(project_name="CLI Run Project Smoke")
    service.save_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-start",
                    "lowered_kind": "control",
                    "source_anchor_ref": "n-start",
                    "expansion_role": "flow:start",
                    "display_name": "Flow Start",
                    "node_kind": "flow.start",
                    "position": {"x": 0, "y": 80},
                    "ports": [
                        {
                            "port_id": "out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "out.control",
                        },
                        {
                            "port_id": "out:variables",
                            "direction": "output",
                            "relation_layer": "data",
                            "semantic_slot": "out.variables",
                        },
                    ],
                    "node_config": {
                        "initial_variables": {},
                        "browser_config": {
                            "headless": True,
                            "slow_mo_ms": 0,
                        },
                    },
                },
                {
                    "node_id": "node-batch",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-batch",
                    "expansion_role": "action:set_variables_batch",
                    "display_name": "Set Variables Batch",
                    "node_kind": "data.set_variables_batch",
                    "node_config": {
                        "variables": {
                            "answer": 42,
                        },
                    },
                    "position": {"x": 120, "y": 80},
                    "ports": [
                        {
                            "port_id": "in",
                            "direction": "input",
                            "relation_layer": "control",
                            "semantic_slot": "in.control",
                        },
                        {
                            "port_id": "out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "out.control",
                        },
                    ],
                }
            ],
            "edges": [
                {
                    "edge_id": "edge-control-1",
                    "relation_layer": "control",
                    "from_node_id": "node-start",
                    "to_node_id": "node-batch",
                    "from_port_id": "out",
                    "to_port_id": "in",
                }
            ],
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
    _build_project_file(project_path)

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
    batch_state = next(item for item in payload["node_states"] if item["node_id"] == "node-batch")

    assert exit_code == 0
    assert payload["project"]["project_name"] == "CLI Run Project Smoke"
    assert payload["runtime_session"]["status"] == "completed"
    assert payload["result"]["status"] == "succeeded"
    assert payload["result"]["variables"]["answer"] == 42
    assert payload["result"]["outputs"]["node-batch"]["variable_names"] == ["answer"]
    assert batch_state["input_snapshot"] == {"variables": {"answer": 42}}
    assert payload["execution_summary"]["status"] == "succeeded"
    assert payload["execution_summary"]["node_status_counts"]["completed"] == 2
    assert payload["runtime_preview_summary"]["scheduler_mode"] == "flow_graph"
