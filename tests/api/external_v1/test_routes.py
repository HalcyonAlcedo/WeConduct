from __future__ import annotations

import ast
from http import HTTPStatus
import inspect
from types import SimpleNamespace
import textwrap

import pytest

from weconduct.api.external_v1 import router
from weconduct.api.server import build_api_server
from weconduct.application.operations.registry import OperationRegistry
from weconduct.application.operations.service import HostOperationService
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


_STABLE_OPERATION_ROUTE_CASES: dict[str, tuple[str, str, dict[str, object]]] = {
    "configuration.schema.get": ("GET", "/api/ext/v1/configuration/project/schema", {}),
    "configuration.values.get": ("GET", "/api/ext/v1/configuration/project/values", {}),
    "configuration.preview": ("POST", "/api/ext/v1/configuration/project/preview", {}),
    "configuration.apply": ("POST", "/api/ext/v1/configuration/project/apply", {}),
    "configuration.reset": ("POST", "/api/ext/v1/configuration/project/reset", {}),
    "operation.list": ("GET", "/api/ext/v1/operations", {}),
    "operation.get": ("GET", "/api/ext/v1/operations/host.describe", {}),
    "host.describe": ("GET", "/api/ext/v1/host", {}),
    "host.capabilities": ("GET", "/api/ext/v1/host/capabilities", {}),
    "debug.prepare": ("POST", "/api/ext/v1/debug/prepare", {}),
    "debug.start": ("POST", "/api/ext/v1/debug", {}),
    "debug.list": ("GET", "/api/ext/v1/debug", {}),
    "debug.history.list": ("GET", "/api/ext/v1/debug/history", {}),
    "debug.history.get": ("GET", "/api/ext/v1/debug/history/debug-1", {}),
    "debug.history.events": ("GET", "/api/ext/v1/debug/history/debug-1/events", {}),
    "debug.history.projection": ("GET", "/api/ext/v1/debug/history/debug-1/projection", {}),
    "debug.live_projection": ("GET", "/api/ext/v1/debug/debug-1/projection", {}),
    "debug.get": ("GET", "/api/ext/v1/debug/debug-1", {}),
    "debug.continue": ("POST", "/api/ext/v1/debug/debug-1/continue", {}),
    "debug.pause": ("POST", "/api/ext/v1/debug/debug-1/pause", {}),
    "debug.step_over": ("POST", "/api/ext/v1/debug/debug-1/step-over", {}),
    "debug.step_into": ("POST", "/api/ext/v1/debug/debug-1/step-into", {}),
    "debug.step_out": ("POST", "/api/ext/v1/debug/debug-1/step-out", {}),
    "debug.abort": ("POST", "/api/ext/v1/debug/debug-1/abort", {}),
    "debug.variables.apply": ("POST", "/api/ext/v1/debug/debug-1/variables", {}),
    "debug.node_debugger.apply": ("POST", "/api/ext/v1/debug/debug-1/node-debugger", {}),
    "debug.parameters.unlock": ("POST", "/api/ext/v1/debug/debug-1/unlock", {}),
    "resource.list": ("GET", "/api/ext/v1/resources", {}),
    "component.list": ("GET", "/api/ext/v1/components", {}),
    "resource.user_component.save": ("POST", "/api/ext/v1/resources/user-components", {}),
    "resource.subgraph.save": ("POST", "/api/ext/v1/resources/subgraphs", {}),
    "resource.custom_node_graph.save": ("POST", "/api/ext/v1/resources/custom-node-graphs", {}),
    "resource.custom_node_graph.create": ("POST", "/api/ext/v1/resources/custom-node-graphs/empty", {}),
    "resource.enabled.set": ("POST", "/api/ext/v1/resources/resource-1/enabled", {}),
    "resource.tags.set": ("POST", "/api/ext/v1/resources/resource-1/tags", {}),
    "resource.metadata.update": ("POST", "/api/ext/v1/resources/metadata", {}),
    "resource.rename": ("POST", "/api/ext/v1/resources/rename", {}),
    "resource.delete": ("POST", "/api/ext/v1/resources/delete", {}),
    "project.current.get": ("GET", "/api/ext/v1/project/current", {}),
    "project.resource_audit.get": ("GET", "/api/ext/v1/project/resource-audit", {}),
    "project.create": ("POST", "/api/ext/v1/projects", {}),
    "project.open": ("POST", "/api/ext/v1/project/open", {}),
    "project.save": ("POST", "/api/ext/v1/project/save", {}),
    "project.close": ("POST", "/api/ext/v1/project/close", {}),
    "graph.get": ("GET", "/api/ext/v1/graph", {}),
    "graph.context": ("POST", "/api/ext/v1/graph/context", {}),
    "project.documents.list": ("GET", "/api/ext/v1/graph/documents", {}),
    "graph.document.get": ("GET", "/api/ext/v1/graph/documents/document-1", {}),
    "graph.document.replace": ("PUT", "/api/ext/v1/graph/documents/document-1", {}),
    "graph.replace": ("PUT", "/api/ext/v1/graph", {}),
    "graph.patch.preview": ("POST", "/api/ext/v1/graph/patch/preview", {}),
    "graph.patch.apply": ("POST", "/api/ext/v1/graph/patch", {}),
    "graph.validate": ("POST", "/api/ext/v1/graph/validate", {}),
    "graph.normalize": ("POST", "/api/ext/v1/graph/normalize", {}),
    "graph.compile": ("POST", "/api/ext/v1/graph/compile", {}),
    "graph.node_draft.build": ("POST", "/api/ext/v1/graph/node-drafts", {}),
    "graph.source_projection": ("GET", "/api/ext/v1/graph/source-projection", {}),
    "runtime.list": ("GET", "/api/ext/v1/runtimes", {}),
    "execution.history.get": ("GET", "/api/ext/v1/execution-history", {}),
    "execution.prepare": ("POST", "/api/ext/v1/executions/prepare", {}),
    "execution.start": ("POST", "/api/ext/v1/executions", {}),
    "execution.get": ("GET", "/api/ext/v1/executions/execution-1", {}),
    "execution.cancel": ("POST", "/api/ext/v1/executions/execution-1/cancel", {}),
    "execution.parameters.unlock": ("POST", "/api/ext/v1/executions/execution-1/unlock", {}),
    "execution.events.subscribe": ("GET", "/api/ext/v1/executions/execution-1/events", {}),
    "pending_input.get": ("GET", "/api/ext/v1/executions/execution-1/pending-input", {}),
    "pending_input.submit": (
        "POST",
        "/api/ext/v1/executions/execution-1/pending-input/request-1/submit",
        {},
    ),
}


def _dispatch_operation_ids() -> set[str]:
    source = textwrap.dedent(inspect.getsource(HostOperationService._dispatch))
    tree = ast.parse(source)
    operation_ids: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Name) or node.left.id != "operation_id":
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                operation_ids.add(comparator.value)
            elif isinstance(comparator, ast.Set):
                operation_ids.update(
                    element.value
                    for element in comparator.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    return operation_ids


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


@pytest.mark.parametrize(
    ("method", "request_path", "expected_operation_id"),
    [
        ("GET", "/api/ext/v1/operations", "operation.list"),
        ("GET", "/api/ext/v1/operations/graph.replace", "operation.get"),
        ("GET", "/api/ext/v1/resources", "resource.list"),
        ("GET", "/api/ext/v1/components", "component.list"),
        ("GET", "/api/ext/v1/graph/documents", "project.documents.list"),
        ("GET", "/api/ext/v1/graph/documents/resource:custom-node-graph", "graph.document.get"),
        ("POST", "/api/ext/v1/resources/user-components", "resource.user_component.save"),
        ("POST", "/api/ext/v1/resources/subgraphs", "resource.subgraph.save"),
        ("POST", "/api/ext/v1/resources/custom-node-graphs", "resource.custom_node_graph.save"),
    ],
)
def test_external_routes_map_discovery_endpoints_to_explicit_operations(
    method: str,
    request_path: str,
    expected_operation_id: str,
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method=method,
        request_path=request_path,
    )

    assert operation_id == expected_operation_id
    assert payload == (
        {"operation_id": "graph.replace"}
        if expected_operation_id == "operation.get"
        else {"document_id": "resource:custom-node-graph"}
        if expected_operation_id == "graph.document.get"
        else {}
    )


def test_external_route_maps_custom_graph_document_replace() -> None:
    operation_id, payload = router.resolve_external_operation(
        method="PUT",
        request_path="/api/ext/v1/graph/documents/resource:custom-node-graph",
        read_payload=lambda: {
            "graph_document": {"document_id": "resource:custom-node-graph", "nodes": []},
            "expected_revision": 5,
        },
    )

    assert operation_id == "graph.document.replace"
    assert payload == {
        "document_id": "resource:custom-node-graph",
        "graph_document": {"document_id": "resource:custom-node-graph", "nodes": []},
        "expected_revision": 5,
    }


@pytest.mark.parametrize(
    ("method", "request_path", "expected_operation_id"),
    [
        ("POST", "/api/ext/v1/debug/prepare", "debug.prepare"),
        ("POST", "/api/ext/v1/debug", "debug.start"),
        ("GET", "/api/ext/v1/debug", "debug.list"),
        ("GET", "/api/ext/v1/debug/debug-1", "debug.get"),
        ("POST", "/api/ext/v1/debug/debug-1/continue", "debug.continue"),
        ("POST", "/api/ext/v1/debug/debug-1/pause", "debug.pause"),
        ("POST", "/api/ext/v1/debug/debug-1/step-over", "debug.step_over"),
        ("POST", "/api/ext/v1/debug/debug-1/step-into", "debug.step_into"),
        ("POST", "/api/ext/v1/debug/debug-1/step-out", "debug.step_out"),
        ("POST", "/api/ext/v1/debug/debug-1/abort", "debug.abort"),
        ("POST", "/api/ext/v1/debug/debug-1/variables", "debug.variables.apply"),
        ("POST", "/api/ext/v1/debug/debug-1/node-debugger", "debug.node_debugger.apply"),
        ("POST", "/api/ext/v1/debug/debug-1/unlock", "debug.parameters.unlock"),
    ],
)
def test_external_routes_map_debug_controls_to_explicit_operations(
    method: str,
    request_path: str,
    expected_operation_id: str,
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method=method,
        request_path=request_path,
        read_payload=lambda: {},
    )

    assert operation_id == expected_operation_id
    assert payload.get("session_id") == "debug-1" or expected_operation_id in {"debug.prepare", "debug.start", "debug.list"}


@pytest.mark.parametrize(
    ("method", "request_path", "expected_operation_id", "expected_payload"),
    [
        ("GET", "/api/ext/v1/configuration/program/schema", "configuration.schema.get", {"scope": "program"}),
        ("GET", "/api/ext/v1/configuration/graph/values", "configuration.values.get", {"scope": "graph"}),
        ("POST", "/api/ext/v1/configuration/project/preview", "configuration.preview", {"scope": "project"}),
        ("POST", "/api/ext/v1/configuration/graph/apply", "configuration.apply", {"scope": "graph"}),
        ("POST", "/api/ext/v1/configuration/project/reset", "configuration.reset", {"scope": "project"}),
    ],
)
def test_external_routes_map_configuration_scopes_to_explicit_operations(
    method: str,
    request_path: str,
    expected_operation_id: str,
    expected_payload: dict[str, object],
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method=method,
        request_path=request_path,
        read_payload=lambda: {},
    )
    assert operation_id == expected_operation_id
    assert payload == expected_payload


@pytest.mark.parametrize(
    ("request_path", "expected_operation_id", "expected_payload"),
    [
        ("/api/ext/v1/runtimes", "runtime.list", {}),
        ("/api/ext/v1/execution-history", "execution.history.get", {}),
        ("/api/ext/v1/debug/history", "debug.history.list", {}),
        ("/api/ext/v1/debug/history/debug-1", "debug.history.get", {"session_id": "debug-1"}),
        ("/api/ext/v1/debug/history/debug-1/events", "debug.history.events", {"session_id": "debug-1"}),
        ("/api/ext/v1/debug/history/debug-1/projection", "debug.history.projection", {"session_id": "debug-1"}),
        ("/api/ext/v1/debug/debug-1/projection", "debug.live_projection", {"session_id": "debug-1"}),
        ("/api/ext/v1/graph/source-projection", "graph.source_projection", {}),
    ],
)
def test_external_routes_map_observability_endpoints_to_explicit_operations(
    request_path: str,
    expected_operation_id: str,
    expected_payload: dict[str, object],
) -> None:
    operation_id, payload = router.resolve_external_operation(method="GET", request_path=request_path)
    assert operation_id == expected_operation_id
    assert payload == expected_payload


def test_external_debug_history_projection_route_forwards_one_replay_selector() -> None:
    operation_id, payload = router.resolve_external_operation(
        method="GET",
        request_path="/api/ext/v1/debug/history/debug-1/projection",
        query_params={"event_index": ["3"]},
    )

    assert operation_id == "debug.history.projection"
    assert payload == {"session_id": "debug-1", "event_index": "3"}


def test_external_catalogue_routes_forward_search_filters_and_limit() -> None:
    operation_id, payload = router.resolve_external_operation(
        method="GET",
        request_path="/api/ext/v1/components",
        query_params={"query": ["while"], "tags": ["control", "builtin"], "limit": ["5"]},
    )

    assert operation_id == "component.list"
    assert payload == {"query": "while", "tags": ["control", "builtin"], "limit": "5"}


def test_external_operation_discovery_lists_every_stable_descriptor_and_resolves_each_detail() -> None:
    registry_ids = {
        descriptor.operation_id
        for descriptor in OperationRegistry.build_stable_public().list_descriptors()
    }
    assert len(registry_ids) == 67

    class _DiscoveryService:
        def get_runtime_health(self) -> dict[str, object]:
            return {"api_version": "0.9", "host_mode": "test", "capabilities": {}}

    service = _DiscoveryService()
    operation_service = router.HostOperationService(service=service)
    discovered = operation_service.invoke(
        "operation.list",
        {},
        caller=router.OperationCaller(
            caller_id="test:discovery",
            permissions=frozenset({"operation.invoke"}),
        ),
    )
    discovered_ids = {item["operation_id"] for item in discovered["operations"]}
    assert discovered_ids == registry_ids
    for operation_id in registry_ids:
        detail = operation_service.invoke(
            "operation.get",
            {"operation_id": operation_id},
            caller=router.OperationCaller(
                caller_id="test:discovery",
                permissions=frozenset({"operation.invoke"}),
            ),
        )
        assert detail["operation"]["operation_id"] == operation_id


def test_stable_public_operations_have_explicit_handler_and_http_route_coverage() -> None:
    stable_operation_ids = {
        descriptor.operation_id
        for descriptor in OperationRegistry.build_stable_public().list_descriptors()
    }

    assert set(_STABLE_OPERATION_ROUTE_CASES) == stable_operation_ids
    assert _dispatch_operation_ids() == stable_operation_ids

    resolved_operation_ids: set[str] = set()
    for expected_operation_id, (method, request_path, payload) in _STABLE_OPERATION_ROUTE_CASES.items():
        operation_id, resolved_payload = router.resolve_external_operation(
            method=method,
            request_path=request_path,
            read_payload=lambda payload=payload: payload,
        )
        assert operation_id == expected_operation_id
        assert isinstance(resolved_payload, dict)
        resolved_operation_ids.add(operation_id)

    assert resolved_operation_ids == stable_operation_ids

@pytest.mark.parametrize(
    ("request_path", "expected_operation_id"),
    [
        ("/api/ext/v1/graph/context", "graph.context"),
        ("/api/ext/v1/graph/patch/preview", "graph.patch.preview"),
        ("/api/ext/v1/graph/patch", "graph.patch.apply"),
    ],
)
def test_external_graph_context_and_patch_routes_map_to_stable_operations(
    request_path: str,
    expected_operation_id: str,
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method="POST",
        request_path=request_path,
        read_payload=lambda: {"expected_revision": 4, "operations": []},
    )

    assert operation_id == expected_operation_id
    assert payload == {"expected_revision": 4, "operations": []}


@pytest.mark.parametrize(
    ("method", "request_path", "expected_operation_id", "expected_payload"),
    [
        ("GET", "/api/ext/v1/project/resource-audit", "project.resource_audit.get", {}),
        ("POST", "/api/ext/v1/graph/normalize", "graph.normalize", {"graph_document": {"document_id": "graph:workspace"}}),
        ("POST", "/api/ext/v1/executions/prepare", "execution.prepare", {}),
    ],
)
def test_external_routes_map_read_only_assistance_endpoints_to_explicit_operations(
    method: str,
    request_path: str,
    expected_operation_id: str,
    expected_payload: dict[str, object],
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method=method,
        request_path=request_path,
        read_payload=lambda: expected_payload,
    )

    assert operation_id == expected_operation_id
    assert payload == expected_payload


@pytest.mark.parametrize(
    ("request_path", "expected_operation_id", "expected_payload"),
    [
        ("/api/ext/v1/resources/user-1/enabled", "resource.enabled.set", {"resource_id": "user-1", "enabled": False}),
        ("/api/ext/v1/resources/user-1/tags", "resource.tags.set", {"resource_id": "user-1", "tags": ["team:ops"]}),
        ("/api/ext/v1/resources/delete", "resource.delete", {"resource_id": "user-1"}),
        ("/api/ext/v1/resources/rename", "resource.rename", {"resource_id": "user-1", "display_name": "新名称"}),
    ],
)
def test_external_routes_map_resource_mutations_to_explicit_operations(
    request_path: str,
    expected_operation_id: str,
    expected_payload: dict[str, object],
) -> None:
    operation_id, payload = router.resolve_external_operation(
        method="POST",
        request_path=request_path,
        read_payload=lambda: (
            {
                key: value for key, value in expected_payload.items() if key != "resource_id"
            }
            if request_path.endswith(("/enabled", "/tags"))
            else expected_payload
        ),
    )

    assert operation_id == expected_operation_id
    assert payload == expected_payload


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
