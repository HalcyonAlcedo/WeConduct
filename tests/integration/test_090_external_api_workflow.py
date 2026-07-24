from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
import urllib.error
import urllib.request

from weconduct.api import build_api_server


def _request_json(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": "Bearer integration-secret",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _graph_document() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "start",
                "lowered_kind": "control",
                "source_anchor_ref": "start",
                "expansion_role": "flow.start",
                "display_name": "Start",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "next",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {"initial_variables": {}},
            }
        ],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_090_external_api_workflow_starts_execution_and_replays_terminal_sse(tmp_path: Path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        external_api_enabled=True,
        external_api_token="integration-secret",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, started = _request_json(
            f"{base_url}/api/ext/v1/executions",
            method="POST",
            payload={"graph_document": _graph_document()},
        )
        assert status == 202
        execution_id = started["result"]["runtime_session"]["session_id"]

        request = urllib.request.Request(
            f"{base_url}/api/ext/v1/executions/{execution_id}/events",
            headers={"Authorization": "Bearer integration-secret"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")

        assert response.status == 200
        assert "event: runtime.completed" in body
        assert execution_id in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
