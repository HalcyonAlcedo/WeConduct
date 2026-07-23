from __future__ import annotations

from concurrent.futures import Future

import httpx

from weconduct.network_runtime.http_adapter import HttpxAdapter
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.models import NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.builtin_components import build_builtin_resource_registry
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_httpx_adapter_returns_404_as_a_normal_network_response(tmp_path) -> None:
    adapter = HttpxAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, text="missing", request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="request-1",
        session_id="session-1",
        method="GET",
        url="https://example.test/missing",
    )

    result = adapter.execute(operation, NetworkContextSnapshot(context_id="context-1"))

    assert result.status == "succeeded"
    assert result.status_code == 404
    assert result.transport_error is None
    assert result.body_ref.read_text() == "missing"


def test_httpx_adapter_revalidates_redirect_destinations(tmp_path) -> None:
    adapter = HttpxAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"location": "http://127.0.0.1:8080/internal"},
                request=request,
            )
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="request-redirect",
        session_id="session-1",
        method="GET",
        url="https://example.test/redirect",
    )

    result = adapter.execute(operation, NetworkContextSnapshot(context_id="context-1"))

    assert result.status == "failed"
    assert result.transport_error is not None
    assert "network.access_denied" in result.transport_error


def test_network_http_request_node_delegates_to_network_runtime_service() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None
            self.snapshot: NetworkContextSnapshot | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            self.operation = operation
            self.snapshot = snapshot
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=404,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=7,
                        content_type="text/plain",
                        _payload=b"missing",
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    registry = RuntimeExecutorRegistry(network_runtime_service=service)
    context = RuntimeContext()
    node = {
        "node_id": "network-node-1",
        "node_kind": "network.http_request",
        "node_config": {
            "method": "GET",
            "url": "https://example.test/missing",
            "body": {"request": "value"},
        },
    }

    output = registry.execute("network.http_request", node, context)

    assert output["status"] == "succeeded"
    assert output["status_code"] == 404
    assert output["body_ref"].read_text() == "missing"
    assert service.operation is not None
    assert service.operation.url == "https://example.test/missing"
    assert service.operation.content == b'{"request": "value"}'
    assert service.operation.headers["Content-Type"] == "application/json"


def test_network_http_request_is_registered_as_a_builtin_component() -> None:
    registry = build_builtin_resource_registry()

    network_http_request = next(
        item for item in registry if item["resource_key"] == "network.http_request"
    )

    assert network_http_request["resource_id"] == "builtin:network.http_request"
