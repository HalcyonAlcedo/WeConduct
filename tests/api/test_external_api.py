from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
import urllib.error
import urllib.request

from weconduct.api import build_api_server
from weconduct.application.pending_input.models import PendingInputField, PendingInputRequest
from weconduct.runtime.engine import CancellationContext


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _build_server(tmp_path: Path, *, enabled: bool, token: str | None = None):
    return build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        external_api_enabled=enabled,
        external_api_token=token,
    )


def test_external_api_is_disabled_by_default(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=False)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(f"{base_url}/api/ext/v1/host")
        assert status == 404
        assert payload["error_code"] == "external_api.disabled"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_requires_bearer_token_and_does_not_accept_internal_header(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(f"{base_url}/api/ext/v1/host")
        assert status == 401
        assert payload["error_code"] == "external_api.unauthorized"

        request = urllib.request.Request(
            f"{base_url}/api/ext/v1/host",
            headers={"X-WeConduct-Token": "external-secret"},
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 200
        assert payload["operation_id"] == "host.describe"
        assert payload["result"]["service"] == "weconduct"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_dispatches_graph_get_and_graph_validate(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, graph = _request_json(
            f"{base_url}/api/ext/v1/graph",
            token="external-secret",
        )
        assert status == 200
        assert graph["operation_id"] == "graph.get"
        graph_document = graph["result"]["graph_model"]

        status, validated = _request_json(
            f"{base_url}/api/ext/v1/graph/validate",
            method="POST",
            payload={"graph_document": graph_document},
            token="external-secret",
        )
        assert status == 200
        assert validated["operation_id"] == "graph.validate"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_pending_input_state_conflict_returns_409(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, _ = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 200
        service = server.workbench_service
        service._pending_input_service.create(  # type: ignore[attr-defined]
            PendingInputRequest(
                request_id="request-1",
                execution_id="execution-1",
                node_id="node-1",
                fields=(PendingInputField(field_id="name", label="Name"),),
            )
        )

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/execution-1/pending-input/request-1/submit",
            method="POST",
            payload={"values": {"name": "alice"}},
            token="external-secret",
        )

        assert status == 409
        assert payload["error_code"] == "operation.state_conflict"
        assert "alice" not in json.dumps(payload)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_pending_input_submit_returns_202_and_hides_values(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    waiter = None
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        request = PendingInputRequest(
            request_id="request-2",
            execution_id="execution-2",
            node_id="node-2",
            fields=(
                PendingInputField(field_id="name", label="Name"),
                PendingInputField(field_id="secret", label="Secret", sensitive=True),
            ),
        )
        service._pending_input_service.create(request)  # type: ignore[attr-defined]
        waiter = Thread(
            target=service._pending_input_service.wait,  # type: ignore[attr-defined]
            args=(request.request_id, CancellationContext()),
            daemon=True,
        )
        waiter.start()
        deadline = monotonic() + 1
        while monotonic() < deadline:
            snapshot = service.get_pending_input_snapshot(execution_id=request.execution_id)
            if snapshot is not None and snapshot.status == "waiting":
                break
            sleep(0.01)

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/execution-2/pending-input/request-2/submit",
            method="POST",
            payload={"values": {"name": "alice", "secret": "top-secret"}},
            token="external-secret",
        )

        assert status == 202
        assert payload["result"]["status"] == "submitted"
        assert "top-secret" not in json.dumps(payload)
    finally:
        if waiter is not None:
            waiter.join(timeout=1)
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_sse_replays_from_last_event_id(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        started = service.start_runtime_session(
            graph_document_payload={
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-start",
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
        )
        assert started["status"] == "started"
        execution_id = started["runtime_session"]["session_id"]
        service._runtime_stream_broker.publish_event(  # type: ignore[attr-defined]
            execution_id,
            "runtime.completed",
            {"session_id": execution_id, "status": "completed"},
        )

        request = urllib.request.Request(
            f"{base_url}/api/ext/v1/executions/{execution_id}/events",
            headers={
                "Authorization": "Bearer external-secret",
                "Last-Event-ID": "1",
            },
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            body = response.read().decode("utf-8")

        assert response.status == 200
        assert "id: 2" in body
        assert "event: runtime.completed" in body
        assert "Last-Event-ID" not in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
