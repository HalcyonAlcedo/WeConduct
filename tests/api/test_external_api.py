from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep
import urllib.error
import urllib.request

import pytest

from weconduct.api import build_api_server
from weconduct.application.configuration.program_repository import (
    FileProgramConfigurationRepository,
)
from weconduct.application.pending_input.models import PendingInputField, PendingInputRequest
from weconduct.runtime.engine import CancellationContext


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
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


def test_external_router_keeps_bearer_semantics_and_maps_the_fixed_host_route() -> None:
    from weconduct.api.external_v1.auth import ExternalApiAuthenticator
    from weconduct.api.external_v1.router import resolve_external_operation

    assert ExternalApiAuthenticator(expected_token="token").accepts("Bearer token")
    assert not ExternalApiAuthenticator(expected_token="token").accepts("Bearer other")
    assert resolve_external_operation(method="GET", request_path="/api/ext/v1/host") == (
        "host.describe",
        {},
    )


def test_external_api_non_loopback_bind_requires_explicit_confirmation() -> None:
    from weconduct.api.server import _validate_external_api_bind_host

    with pytest.raises(ValueError, match="external_api.non_loopback_confirmation_required"):
        _validate_external_api_bind_host("0.0.0.0", allow_non_loopback=False)

    with pytest.raises(ValueError, match="external_api.non_loopback_confirmation_required"):
        build_api_server(host="0.0.0.0", port=0)

    _validate_external_api_bind_host("0.0.0.0", allow_non_loopback=True)
    _validate_external_api_bind_host("127.0.0.1", allow_non_loopback=False)


def test_build_api_server_loads_external_api_settings_from_program_configuration(
    tmp_path: Path,
) -> None:
    preferences_path = tmp_path / "runtime" / "preferences.json"
    allowed_root = tmp_path / "allowed-projects"
    FileProgramConfigurationRepository(preferences_path).save(
        {
            "security": {
                "external_api_enabled": True,
                "external_api_token": "configured-external-token",
                "external_api_project_allowed_roots": [str(allowed_root)],
            }
        }
    )

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=preferences_path,
        ui_dist_path=tmp_path / "ui-dist",
    )
    try:
        assert server.external_api_enabled is True
        assert server.external_api_token == "configured-external-token"
        assert server.external_api_project_allowed_roots == (allowed_root.resolve(),)
    finally:
        server.server_close()


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
        assert graph["result"]["revision"] == 0

        status, validated = _request_json(
            f"{base_url}/api/ext/v1/graph/validate",
            method="POST",
            payload={"graph_document": graph_document},
            token="external-secret",
        )
        assert status == 200
        assert validated["operation_id"] == "graph.validate"

        status, rejected = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload={"graph_document": graph_document},
            token="external-secret",
        )
        assert status == 422
        assert rejected["error_code"] == "operation.input_invalid"
        assert rejected["operation_id"] == "graph.replace"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_rejects_project_open_outside_configured_allowed_roots(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    server.external_api_project_allowed_roots = (tmp_path / "allowed-projects",)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/project/open",
            method="POST",
            payload={"project_path": str(tmp_path / "outside-projects" / "project.weconduct.json")},
            token="external-secret",
        )

        assert status == 403
        assert payload["error_code"] == "operation.path_denied"
        assert payload["operation_id"] == "project.open"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_requires_idempotency_key_for_project_save(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/project/save",
            method="POST",
            payload={},
            token="external-secret",
        )

        assert status == 428
        assert payload["error_code"] == "operation.idempotency_key_required"
        assert payload["operation_id"] == "project.save"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_returns_revision_conflict_for_stale_graph_replace(tmp_path: Path) -> None:
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
        payload = {
            "graph_document": graph["result"]["graph_model"],
            "expected_revision": graph["result"]["revision"],
        }

        first_status, _ = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload=payload,
            token="external-secret",
        )
        stale_status, stale = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload=payload,
            token="external-secret",
        )

        assert first_status == 200
        assert stale_status == 409
        assert stale["error_code"] == "graph.revision_conflict"
        assert stale["details"] == {"expected_revision": 0, "current_revision": 1}
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


def test_external_api_pending_input_submit_after_timeout_returns_410(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    waiter = None
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        request = PendingInputRequest(
            request_id="request-timeout-api",
            execution_id="execution-timeout-api",
            node_id="node-timeout-api",
            fields=(PendingInputField(field_id="name", label="Name"),),
            timeout_seconds=0.02,
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
            if snapshot is not None and snapshot.status == "timed_out":
                break
            sleep(0.01)

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/{request.execution_id}/pending-input/{request.request_id}/submit",
            method="POST",
            payload={"values": {"name": "alice"}},
            token="external-secret",
        )

        assert status == 410
        assert payload["error_code"] == "operation.state_conflict"
        assert payload["details"]["state"] == "timed_out"
    finally:
        if waiter is not None:
            waiter.join(timeout=1)
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_pending_input_get_exposes_field_types_without_defaults(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        request = PendingInputRequest(
            request_id="request-fields-api",
            execution_id="execution-fields-api",
            node_id="node-fields-api",
            fields=(
                PendingInputField(
                    field_id="count",
                    label="Count",
                    value_type="number",
                    default_value=3,
                ),
                PendingInputField(
                    field_id="secret",
                    label="Secret",
                    value_type="password",
                    sensitive=True,
                ),
            ),
        )
        service._pending_input_service.create(request)  # type: ignore[attr-defined]

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/{request.execution_id}/pending-input",
            token="external-secret",
        )

        assert status == 200
        assert payload["result"]["status"] == "created"
        assert payload["result"]["fields"] == [
            {
                "field_id": "count",
                "label": "Count",
                "required": True,
                "sensitive": False,
                "type": "number",
            },
            {
                "field_id": "secret",
                "label": "Secret",
                "required": True,
                "sensitive": True,
                "type": "password",
            },
        ]
        assert "default_value" not in json.dumps(payload)
    finally:
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


def test_external_api_replays_idempotent_graph_replace_response(tmp_path: Path) -> None:
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
        payload = {
            "graph_document": graph["result"]["graph_model"],
            "expected_revision": graph["result"]["revision"],
        }
        headers = {"Idempotency-Key": "replace-once"}

        first_status, first = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload=payload,
            token="external-secret",
            extra_headers=headers,
        )
        second_status, second = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload=payload,
            token="external-secret",
            extra_headers=headers,
        )

        assert first_status == 200
        assert second_status == first_status
        assert second == first
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_rejects_duplicate_idempotent_request_while_in_progress(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    first_result: list[tuple[int, dict]] = []
    started = Event()
    release = Event()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, graph = _request_json(
            f"{base_url}/api/ext/v1/graph",
            token="external-secret",
        )
        assert status == 200
        payload = {
            "graph_document": graph["result"]["graph_model"],
            "expected_revision": graph["result"]["revision"],
        }
        original_save = server.workbench_service.save_graph_document

        def blocked_save(*args, **kwargs):
            started.set()
            assert release.wait(timeout=2)
            return original_save(*args, **kwargs)

        server.workbench_service.save_graph_document = blocked_save  # type: ignore[method-assign]
        request_headers = {"Idempotency-Key": "replace-concurrent"}

        first_thread = Thread(
            target=lambda: first_result.append(
                _request_json(
                    f"{base_url}/api/ext/v1/graph",
                    method="PUT",
                    payload=payload,
                    token="external-secret",
                    extra_headers=request_headers,
                )
            ),
            daemon=True,
        )
        first_thread.start()
        assert started.wait(timeout=2)

        second_status, second = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload=payload,
            token="external-secret",
            extra_headers=request_headers,
        )

        assert second_status == 409
        assert second["error_code"] == "operation.in_progress"
        release.set()
        first_thread.join(timeout=2)
        assert first_result and first_result[0][0] == 200
    finally:
        release.set()
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_ignores_idempotency_key_for_non_capable_operation(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        headers = {"Idempotency-Key": "describe-once"}
        first_status, first = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
            extra_headers=headers,
        )
        second_status, second = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
            extra_headers=headers,
        )

        assert first_status == second_status == 200
        assert first["operation_id"] == second["operation_id"] == "host.describe"
        assert first["request_id"] != second["request_id"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
