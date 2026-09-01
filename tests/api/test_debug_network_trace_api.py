from pathlib import Path
from threading import Thread

from weconduct.api import build_api_server
from weconduct.application import CompilationWorkbenchService
from weconduct.application.workspace_state_store import FileWorkspaceStateStore
from weconduct.network_runtime.trace import NetworkTraceRecorder


def _build_minimal_workspace_graph() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {
                    "initial_variables": {"username": "original-user"},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            }
        ],
        "edges": [],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _get_json(url: str, *, token: str) -> dict:
    import json
    import urllib.request

    request = urllib.request.Request(url, headers={"X-WeConduct-Token": token})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def test_api_exposes_debug_network_routes(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    preferences_path = tmp_path / "runtime" / "preferences.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    service.save_graph_document(_build_minimal_workspace_graph())
    service.save_project_as(project_path=str(tmp_path / "project.weconduct.json"))
    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    recorder = NetworkTraceRecorder()
    recorder.start_operation(
        trace_id="trace-1",
        debug_session_id=session_id,
        runtime_session_id=session_id,
        node_id="node-http",
        operation_id="network.http_request",
        method="POST",
        url="https://example.test/api",
        request_headers={"content-type": "application/json"},
        request_body='{"name":"item"}',
    )
    recorder.complete_operation(
        trace_id="trace-1",
        status="succeeded",
        response_status=201,
        response_headers={"content-type": "application/json"},
        response_body='{"created":true}',
    )
    setattr(service, "_debug_network_trace_recorders", {session_id: recorder})
    session_document = service.get_debug_session(session_id=session_id)
    session_document["network_trace_snapshot"] = {
        "trace_order": ["trace-1"],
        "traces": {"trace-1": recorder.get_trace("trace-1")},
        "summary": recorder.summary(debug_session_id=session_id),
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    server.workbench_service = service
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        summary_payload = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/network/summary",
            token=server.api_token,
        )
        trace_payload = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/network/trace-1",
            token=server.api_token,
        )
        body_payload = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/network/trace-1/body",
            token=server.api_token,
        )
        request_body_payload = _get_json(
            f"{base_url}/api/workbench/debug/{session_id}/network/trace-1/body?part=request",
            token=server.api_token,
        )
        history_payload = _get_json(
            f"{base_url}/api/workbench/debug/history/{session_id}/network/summary",
            token=server.api_token,
        )

        assert summary_payload["summary"]["total_operations"] == 1
        assert trace_payload["trace"]["trace_id"] == "trace-1"
        assert "request_body" not in trace_payload["trace"]["operation"]
        assert body_payload["request_body"]["value"] == '{"name":"item"}'
        assert request_body_payload["request_body"]["value"] == '{"name":"item"}'
        assert "response_body" not in request_body_payload
        assert history_payload["summary"]["total_operations"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
