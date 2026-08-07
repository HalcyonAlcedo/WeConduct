from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace

from weconduct.api.external_v1 import router
from weconduct.api.server import build_api_server
from weconduct.application.operations.models import (
    IdempotencyCapability,
    InMemoryOperationAuditTrail,
    InMemoryOperationIdempotencyStore,
    OperationInvocationResult,
)


class _Handler:
    def __init__(self) -> None:
        self.path = "/api/ext/v1/host/capabilities"
        self.headers = {"Authorization": "Bearer route-test-token"}
        self.server = SimpleNamespace(
            external_api_enabled=True,
            external_api_token="route-test-token",
            external_api_instance_id="instance-route-test",
            external_api_project_allowed_roots=(),
        )
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def _get_service(self) -> object:
        return object()

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.responses.append((status, payload))


def test_external_rest_route_invokes_shared_operation_service_with_derived_caller(
    monkeypatch,
) -> None:
    invocations: list[dict[str, object]] = []

    class _RecordingOperationService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def describe(self, _operation_id: str) -> object:
            return SimpleNamespace(
                contract_version="1",
                idempotency_capability=IdempotencyCapability.UNSUPPORTED,
            )

        def invoke(
            self,
            operation_id: str,
            payload: dict[str, object],
            *,
            caller: object,
            idempotency_key: str | None,
        ) -> dict[str, object]:
            invocations.append(
                {
                    "operation_id": operation_id,
                    "payload": payload,
                    "caller": caller,
                    "idempotency_key": idempotency_key,
                }
            )
            return OperationInvocationResult(
                {"capabilities": {"network": {"available": True}}},
                replayed=False,
            )

    monkeypatch.setattr(router, "HostOperationService", _RecordingOperationService)
    handler = _Handler()

    assert router.ExternalV1Router(handler).handle(method="GET") is True

    assert handler.responses == [
        (
            HTTPStatus.OK,
            {
                    "operation_id": "host.capabilities",
                    "contract_version": "1",
                    "request_id": handler.responses[0][1]["request_id"],
                    "idempotency_replayed": False,
                    "result": {"capabilities": {"network": {"available": True}}},
            },
        )
    ]
    assert len(invocations) == 1
    caller = invocations[0]["caller"]
    assert caller.caller_id.startswith("external:")
    assert caller.permissions == frozenset({"operation.invoke"})
    assert "route-test-token" not in caller.caller_id


def test_external_route_maps_execution_parameter_unlock() -> None:
    operation_id, payload = router.resolve_external_operation(
        method="POST",
        request_path="/api/ext/v1/executions/execution-1/unlock",
        read_payload=lambda: {"password": "test-password"},
    )

    assert operation_id == "execution.parameters.unlock"
    assert payload == {
        "execution_id": "execution-1",
        "password": "test-password",
    }


def test_external_router_replays_idempotent_result_across_requests() -> None:
    class _ProjectService:
        def __init__(self) -> None:
            self.create_count = 0

        def create_project(
            self,
            *,
            project_name: str,
            project_directory: str | None,
        ) -> dict[str, object]:
            self.create_count += 1
            return {
                "project_name": project_name,
                "project_directory": project_directory,
                "create_count": self.create_count,
            }

    service = _ProjectService()
    server = SimpleNamespace(
        external_api_enabled=True,
        external_api_token="idempotency-token",
        external_api_instance_id="instance-idempotency",
        external_api_project_allowed_roots=(),
        external_api_idempotency_store=InMemoryOperationIdempotencyStore(),
    )

    class _Handler:
        def __init__(self) -> None:
            self.path = "/api/ext/v1/projects"
            self.headers = {
                "Authorization": "Bearer idempotency-token",
                "Idempotency-Key": "project-create-1",
            }
            self.server = server
            self.response: tuple[HTTPStatus, dict[str, object]] | None = None

        def _get_service(self) -> object:
            return service

        def _read_optional_json_request_body(self) -> dict[str, object]:
            return {"project_name": "demo"}

        def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            self.response = status, payload

    first_handler = _Handler()
    second_handler = _Handler()

    assert router.ExternalV1Router(first_handler).handle(method="POST") is True
    assert router.ExternalV1Router(second_handler).handle(method="POST") is True

    assert service.create_count == 1
    assert first_handler.response is not None
    assert second_handler.response is not None
    assert second_handler.response[1]["result"] == first_handler.response[1]["result"]


def test_external_router_includes_event_bounds_when_cursor_is_expired() -> None:
    class _Service:
        def get_runtime_stream_events_since(
            self,
            *,
            session_id: str,
            after_event_id: int | None,
        ) -> dict[str, object]:
            raise ValueError("execution.event_cursor_expired")

        def get_runtime_stream_event_bounds(self, *, session_id: str) -> dict[str, object]:
            assert session_id == "execution-expired"
            return {"oldest_event_id": 12, "latest_event_id": 42}

        def get_runtime_session(self, *, session_id: str) -> dict[str, object]:
            return {"runtime_session": {"session_id": session_id, "status": "running"}}

    server = SimpleNamespace(
        external_api_enabled=True,
        external_api_token="expired-token",
        external_api_instance_id="instance-expired",
        external_api_project_allowed_roots=(),
    )

    class _Handler:
        def __init__(self) -> None:
            self.path = "/api/ext/v1/executions/execution-expired/events"
            self.headers = {
                "Authorization": "Bearer expired-token",
                "Last-Event-ID": "2",
            }
            self.server = server
            self.response: tuple[HTTPStatus, dict[str, object]] | None = None

        def _get_service(self) -> object:
            return _Service()

        def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            self.response = status, payload

    handler = _Handler()
    assert router.ExternalV1Router(handler).handle(method="GET") is True
    assert handler.response is not None
    status, payload = handler.response
    assert status == HTTPStatus.CONFLICT
    assert payload["details"] == {"oldest_event_id": 12, "latest_event_id": 42}


def test_api_server_owns_external_operation_idempotency_and_audit_state(tmp_path) -> None:
    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "workspace-state.json",
        preferences_path=tmp_path / "preferences.json",
        ui_dist_path=tmp_path / "ui-dist",
        external_api_enabled=True,
        external_api_token="server-state-token",
    )
    try:
        assert isinstance(
            server.external_api_idempotency_store,
            InMemoryOperationIdempotencyStore,
        )
        assert isinstance(server.external_api_audit_trail, InMemoryOperationAuditTrail)
    finally:
        server.server_close()
