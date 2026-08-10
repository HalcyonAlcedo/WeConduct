from __future__ import annotations

import json
from pathlib import Path
import socket
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
from weconduct.application.sensitive_values.encryption import SensitiveUnlockError
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


def test_external_api_head_keeps_bearer_authentication_and_options_resolves_routes(
    tmp_path: Path,
) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        endpoint = f"{base_url}/api/ext/v1/host"
        with urllib.request.urlopen(
            urllib.request.Request(
                endpoint,
                method="HEAD",
                headers={"Authorization": "Bearer external-secret"},
            )
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Length"] != "0"
            assert response.read() == b""

        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(urllib.request.Request(endpoint, method="HEAD"))
        assert unauthorized.value.code == 401

        with urllib.request.urlopen(
            urllib.request.Request(endpoint, method="OPTIONS")
        ) as response:
            assert response.status == 204
            assert response.headers["Allow"] == "GET, OPTIONS"
            assert response.read() == b""

        with pytest.raises(urllib.error.HTTPError) as unknown:
            urllib.request.urlopen(
                urllib.request.Request(f"{base_url}/api/ext/v1/unknown", method="OPTIONS")
            )
        assert unknown.value.code == 404

        with pytest.raises(urllib.error.HTTPError) as method_not_allowed:
            urllib.request.urlopen(
                urllib.request.Request(
                    endpoint,
                    data=b"{}",
                    method="PUT",
                    headers={"Authorization": "Bearer external-secret"},
                )
            )
        assert method_not_allowed.value.code == 405
        assert method_not_allowed.value.headers["Allow"] == "GET, OPTIONS"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_host_capabilities_preserve_boolean_protocol_flags(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host/capabilities",
            token="external-secret",
        )

        assert status == 200
        protocols = payload["result"]["capabilities"]["network"]["protocols"]
        assert protocols
        assert all(isinstance(value, bool) for value in protocols.values())
        assert protocols["oauth_client_credentials"] is True
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


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


def test_build_api_server_uses_configured_local_api_port_when_port_is_zero(
    tmp_path: Path,
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        configured_port = probe.getsockname()[1]
    preferences_path = tmp_path / "runtime" / "preferences.json"
    FileProgramConfigurationRepository(preferences_path).save(
        {"security": {"local_api_port": configured_port}}
    )

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=preferences_path,
        ui_dist_path=tmp_path / "ui-dist",
    )
    try:
        assert server.server_address[1] == configured_port
    finally:
        server.server_close()
def test_build_api_server_reports_fixed_port_conflict_without_dynamic_fallback(
    tmp_path: Path,
) -> None:
    from weconduct.api.server import ExternalApiBindError

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        probe.listen(1)
        configured_port = probe.getsockname()[1]
        preferences_path = tmp_path / "runtime" / "preferences.json"
        FileProgramConfigurationRepository(preferences_path).save(
            {"security": {"local_api_port": configured_port}}
        )

        with pytest.raises(ExternalApiBindError, match="external_api.port_in_use") as failure:
            build_api_server(
                host="127.0.0.1",
                port=0,
                workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
                preferences_path=preferences_path,
                ui_dist_path=tmp_path / "ui-dist",
            )

    assert failure.value.configured_port == configured_port
    assert failure.value.active_port is None


def test_build_api_server_rejects_second_fixed_listener(
    tmp_path: Path,
) -> None:
    from weconduct.api.server import ExternalApiBindError

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        configured_port = probe.getsockname()[1]

    first_server = build_api_server(
        host="127.0.0.1",
        port=configured_port,
        workspace_state_path=tmp_path / "first" / "workspace-state.json",
        preferences_path=tmp_path / "first" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    try:
        with pytest.raises(ExternalApiBindError, match="external_api.port_in_use"):
            build_api_server(
                host="127.0.0.1",
                port=configured_port,
                workspace_state_path=tmp_path / "second" / "workspace-state.json",
                preferences_path=tmp_path / "second" / "preferences.json",
                ui_dist_path=tmp_path / "ui-dist",
            )
    finally:
        first_server.server_close()


def test_program_config_reset_disables_external_api_in_current_process(
    tmp_path: Path,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        api_token="internal-ui-token",
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        external_api_enabled=True,
        external_api_token="external-secret",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, _ = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 200

        status, _ = _request_json(
            f"{base_url}/api/workbench/config/reset",
            method="POST",
            payload={"scope": "program"},
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200

        status, body = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 404
        assert body["error_code"] == "external_api.disabled"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize("invalid_port", [-1, 65536, 12.5, True, "12345"])
def test_external_api_preferences_reject_invalid_port_and_keep_previous_value(
    tmp_path: Path,
    invalid_port: object,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        api_token="internal-ui-token",
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        valid_port = 62681
        status, saved = _request_json(
            f"{base_url}/api/workbench/preferences/external-api",
            method="POST",
            payload={
                "enabled": False,
                "clear_token": False,
                "local_api_port": valid_port,
                "project_allowed_roots": [],
                "confirm_high_risk": True,
            },
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert saved["local_api_port"] == valid_port
        assert saved["active_listener"] == {
            "host": "127.0.0.1",
            "port": server.server_address[1],
        }
        assert saved["restart_required"] is True

        status, rejected = _request_json(
            f"{base_url}/api/workbench/preferences/external-api",
            method="POST",
            payload={
                "enabled": False,
                "clear_token": False,
                "local_api_port": invalid_port,
                "project_allowed_roots": [],
                "confirm_high_risk": True,
            },
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 400
        assert rejected["error"] == "invalid_request"

        status, current = _request_json(
            f"{base_url}/api/workbench/preferences/external-api",
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert current["local_api_port"] == valid_port
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize("token", [None, "wrong-token", "external-secret"])
def test_disabled_external_api_rejects_all_bearer_tokens_but_keeps_internal_ui_available(
    tmp_path: Path,
    token: str | None,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        api_token="internal-ui-token",
        external_api_enabled=False,
        external_api_token="external-secret",
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host",
            token=token,
        )
        assert status == 404
        assert payload["error_code"] == "external_api.disabled"

        status, health = _request_json(
            f"{base_url}/api/health",
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert health["status"] in {"ok", "healthy", "degraded"}
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_internal_and_external_tokens_are_not_interchangeable(
    tmp_path: Path,
) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        api_token="internal-ui-token",
        external_api_enabled=True,
        external_api_token="external-secret",
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="internal-ui-token",
        )
        assert status == 401
        assert payload["error_code"] == "external_api.unauthorized"

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 200
        assert payload["operation_id"] == "host.describe"

        status, payload = _request_json(
            f"{base_url}/api/health",
            extra_headers={"X-WeConduct-Token": "external-secret"},
        )
        assert status == 401
        assert payload["error"] == "unauthorized"

        status, health = _request_json(
            f"{base_url}/api/health",
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert health["status"] in {"ok", "healthy", "degraded"}
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_enabled_state_persists_across_server_rebuilds(
    tmp_path: Path,
) -> None:
    preferences_path = tmp_path / "runtime" / "preferences.json"
    common = {
        "host": "127.0.0.1",
        "port": 0,
        "api_token": "internal-ui-token",
        "workspace_state_path": tmp_path / "runtime" / "workspace-state.json",
        "preferences_path": preferences_path,
        "ui_dist_path": tmp_path / "ui-dist",
    }

    first = build_api_server(**common)
    first_thread = Thread(target=first.serve_forever, daemon=True)
    first_thread.start()
    try:
        base_url = f"http://{first.server_address[0]}:{first.server_address[1]}"
        status, enabled = _request_json(
            f"{base_url}/api/workbench/preferences/external-api",
            method="POST",
            payload={
                "enabled": True,
                "token": "external-secret",
                "clear_token": False,
                "local_api_port": 0,
                "project_allowed_roots": [],
                "confirm_high_risk": True,
            },
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert enabled["enabled"] is True
    finally:
        first.shutdown()
        first_thread.join(timeout=2)
        first.server_close()

    second = build_api_server(**common)
    second_thread = Thread(target=second.serve_forever, daemon=True)
    second_thread.start()
    try:
        base_url = f"http://{second.server_address[0]}:{second.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/host",
            token="external-secret",
        )
        assert status == 200
        assert payload["operation_id"] == "host.describe"

        status, disabled = _request_json(
            f"{base_url}/api/workbench/preferences/external-api",
            method="POST",
            payload={
                "enabled": False,
                "clear_token": False,
                "local_api_port": 0,
                "project_allowed_roots": [],
                "confirm_high_risk": True,
            },
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert disabled["enabled"] is False
    finally:
        second.shutdown()
        second_thread.join(timeout=2)
        second.server_close()

    third = build_api_server(**common)
    third_thread = Thread(target=third.serve_forever, daemon=True)
    third_thread.start()
    try:
        base_url = f"http://{third.server_address[0]}:{third.server_address[1]}"
        for token in (None, "wrong-token", "external-secret"):
            status, payload = _request_json(
                f"{base_url}/api/ext/v1/host",
                token=token,
            )
            assert status == 404
            assert payload["error_code"] == "external_api.disabled"
    finally:
        third.shutdown()
        third_thread.join(timeout=2)
        third.server_close()


def test_internal_workbench_routes_require_the_explicit_ui_token(tmp_path: Path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        api_token="internal-ui-token",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(f"{base_url}/api/workbench/snapshot")
        assert status == 401
        assert payload["error"] == "unauthorized"

        request = urllib.request.Request(
            f"{base_url}/api/workbench/snapshot",
            headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_internal_startup_recovery_requires_the_explicit_ui_token(tmp_path: Path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        api_token="internal-ui-token",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/startup/recover",
            method="POST",
            payload={},
        )
        assert status == 401
        assert payload["error"] == "unauthorized"

        status, payload = _request_json(
            f"{base_url}/api/startup/recover",
            method="POST",
            payload={},
            extra_headers={"X-WeConduct-Token": "internal-ui-token"},
        )
        assert status == 200
        assert payload["status"] == "recovered"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_internal_get_does_not_leak_workspace_state_errors_before_authentication(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    workspace_state_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_state_path.write_text("{invalid-json", encoding="utf-8")
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        preferences_path=tmp_path / "runtime" / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        api_token="internal-ui-token",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(f"{base_url}/api/workbench/snapshot")
        assert status == 401
        assert payload == {
            "error": "unauthorized",
            "message": "invalid or missing API token",
        }
    finally:
        server.shutdown()
        thread.join(timeout=2)
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


def test_external_api_error_response_generates_request_id_when_header_is_absent(
    tmp_path: Path,
) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/graph",
            method="PUT",
            payload={"graph_document": {}},
            token="external-secret",
        )

        assert status == 422
        assert payload["error_code"] == "operation.input_invalid"
        assert isinstance(payload["request_id"], str)
        assert payload["request_id"].startswith("request-")
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


def test_external_api_pending_input_type_error_returns_422_with_safe_details(tmp_path: Path) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        request = PendingInputRequest(
            request_id="request-type-error-api",
            execution_id="execution-type-error-api",
            node_id="node-type-error-api",
            fields=(
                PendingInputField(
                    field_id="attempt_count",
                    label="Attempts",
                    value_type="integer",
                ),
            ),
        )
        service._pending_input_service.create(request)  # type: ignore[attr-defined]
        service._pending_input_service.activate(request.request_id)  # type: ignore[attr-defined]

        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/{request.execution_id}/pending-input/{request.request_id}/submit",
            method="POST",
            payload={"values": {"attempt_count": "not-an-integer"}},
            token="external-secret",
        )

        assert status == 422
        assert payload["error_code"] == "operation.input_invalid"
        assert payload["details"] == {
            "validation_kind": "type_mismatch",
            "field_id": "attempt_count",
            "expected_type": "integer",
            "actual_type": "string",
        }
        assert service._pending_input_service.get_snapshot(request.request_id).status == "waiting"  # type: ignore[attr-defined]
        assert "not-an-integer" not in json.dumps(payload)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_external_api_pending_input_validation_boundaries_are_structured_and_atomic(
    tmp_path: Path,
) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")
        service = server.workbench_service
        request = PendingInputRequest(
            request_id="request-validation-boundaries",
            execution_id="execution-validation-boundaries",
            node_id="node-validation-boundaries",
            fields=(
                PendingInputField(field_id="attempt_count", label="Attempts", value_type="integer"),
                PendingInputField(field_id="secret", label="Secret", sensitive=True),
            ),
        )
        service._pending_input_service.create(request)  # type: ignore[attr-defined]
        service._pending_input_service.activate(request.request_id)  # type: ignore[attr-defined]

        cases = (
            (
                {"values": {"attempt_count": True, "secret": "do-not-leak"}},
                {
                    "validation_kind": "type_mismatch",
                    "field_id": "attempt_count",
                    "expected_type": "integer",
                    "actual_type": "boolean",
                },
            ),
            (
                {"values": {"attempt_count": 1, "secret": "do-not-leak", "unknown": "x"}},
                {"validation_kind": "unknown_field", "field_ids": ["unknown"]},
            ),
            (
                {"values": {"attempt_count": 1}},
                {"validation_kind": "missing_required", "field_ids": ["secret"]},
            ),
            (
                {"values": []},
                {
                    "validation_kind": "invalid_payload",
                    "expected_type": "object",
                    "actual_type": "array",
                },
            ),
            (
                {"values": "do-not-leak"},
                {
                    "validation_kind": "invalid_payload",
                    "expected_type": "object",
                    "actual_type": "string",
                },
            ),
        )
        for payload, details in cases:
            status, response = _request_json(
                f"{base_url}/api/ext/v1/executions/{request.execution_id}/pending-input/{request.request_id}/submit",
                method="POST",
                payload=payload,
                token="external-secret",
            )
            assert status == 422
            assert response["error_code"] == "operation.input_invalid"
            assert response["details"] == details
            assert "do-not-leak" not in json.dumps(response)

        assert service._pending_input_service.get_snapshot(request.request_id).status == "waiting"  # type: ignore[attr-defined]
        assert "do-not-leak" not in json.dumps(
            [record.input_summary for record in server.external_api_audit_trail.records]
        )
    finally:
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


def test_external_api_parameter_unlock_failure_returns_422_without_secret_details(
    tmp_path: Path,
) -> None:
    server = _build_server(tmp_path, enabled=True, token="external-secret")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        _request_json(f"{base_url}/api/ext/v1/host", token="external-secret")

        def reject_unlock(*, session_id: str, password: str) -> dict:
            raise SensitiveUnlockError()

        server.workbench_service.unlock_runtime_session_parameters = reject_unlock  # type: ignore[method-assign]
        status, payload = _request_json(
            f"{base_url}/api/ext/v1/executions/runtime-1/unlock",
            method="POST",
            payload={"password": "wrong-password"},
            token="external-secret",
        )

        assert status == 422
        assert payload["error_code"] == "sensitive.unlock_failed"
        assert "wrong-password" not in json.dumps(payload)
        assert "external-secret" not in json.dumps(payload)
    finally:
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
        assert second["result"] == first["result"]
        assert first["idempotency_replayed"] is False
        assert second["idempotency_replayed"] is True
        assert second["request_id"] != first["request_id"]
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
