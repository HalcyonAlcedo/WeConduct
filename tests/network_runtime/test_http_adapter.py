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
            lambda request: httpx.Response(
                404,
                text="missing",
                headers={"set-cookie": "sid=from-response; Path=/"},
                request=request,
            )
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
    assert result.duration_ms is not None
    assert result.duration_ms >= 0
    assert result.set_cookies == {"sid": "from-response"}
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


def test_httpx_adapter_merges_context_and_node_query_and_cookie_values(tmp_path) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["query"] = str(request.url.query, encoding="utf-8")
        observed["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="request-context-merge",
        session_id="session-1",
        method="GET",
        url="https://example.test/search?url=present",
        query={"page": "2", "shared": "node"},
    )

    result = adapter.execute(
        operation,
        NetworkContextSnapshot(
            context_id="context-1",
            query={"locale": "zh-CN", "shared": "context"},
            cookies={"session": "context-cookie"},
        ),
    )

    assert result.status == "succeeded"
    assert observed["query"] in {
        "url=present&locale=zh-CN&shared=node&page=2",
        "url=present&page=2&shared=node&locale=zh-CN",
        "url=present&locale=zh-CN&page=2&shared=node",
    }
    assert observed["cookie"] == "session=context-cookie"


def test_httpx_adapter_isolates_non_default_tls_clients(tmp_path) -> None:
    adapter = HttpxAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )

    default_client = adapter._client  # type: ignore[attr-defined]
    insecure_client = adapter._client_for_snapshot(  # type: ignore[attr-defined]
        NetworkContextSnapshot(context_id="tls-insecure", tls={"verify": "insecure"})
    )
    same_insecure_client = adapter._client_for_snapshot(  # type: ignore[attr-defined]
        NetworkContextSnapshot(context_id="tls-insecure-2", tls={"verify": "insecure"})
    )

    assert insecure_client is not default_client
    assert same_insecure_client is insecure_client


def test_httpx_adapter_isolates_manual_proxy_clients(tmp_path) -> None:
    adapter = HttpxAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )

    direct_client = adapter._client  # type: ignore[attr-defined]
    proxy_client = adapter._client_for_snapshot(  # type: ignore[attr-defined]
        NetworkContextSnapshot(
            context_id="proxy-1",
            proxy={"mode": "manual", "url": "http://proxy.example.test:8080"},
        )
    )
    same_proxy_client = adapter._client_for_snapshot(  # type: ignore[attr-defined]
        NetworkContextSnapshot(
            context_id="proxy-2",
            proxy={"mode": "manual", "url": "http://proxy.example.test:8080"},
        )
    )

    assert proxy_client is not direct_client
    assert same_proxy_client is proxy_client


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
            "query": {"source": "node"},
            "body": {"request": "value"},
        },
    }

    output = registry.execute("network.http_request", node, context)

    assert output["status"] == "succeeded"
    assert output["status_code"] == 404
    assert output["body_ref"].read_text() == "missing"
    assert service.operation is not None
    assert service.operation.url == "https://example.test/missing"
    assert service.operation.query == {"source": "node"}
    assert service.operation.content == b'{"request": "value"}'
    assert service.operation.headers["Content-Type"] == "application/json"


def test_network_http_request_binds_and_reuses_a_session_network_context() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.snapshots: list[NetworkContextSnapshot] = []

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            self.snapshots.append(snapshot)
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                )
            )
            return future

    service = StubNetworkRuntimeService()
    registry = RuntimeExecutorRegistry(network_runtime_service=service)
    context = RuntimeContext()
    first_node = {
        "node_id": "network-node-1",
        "node_kind": "network.http_request",
        "node_config": {
            "context_strategy": "new",
            "method": "GET",
            "url": "https://example.test/first",
            "headers": {"X-Shared": "initial"},
        },
    }
    port_override_node = {
        "node_id": "network-node-2",
        "node_kind": "network.http_request",
        "node_config": {
            "context_strategy": "inherit",
            "method": "GET",
            "url": "https://example.test/second",
        },
        "__runtime_input_overrides__": {"headers": {"X-Shared": "port-input"}},
    }
    inherited_node = {
        "node_id": "network-node-3",
        "node_kind": "network.http_request",
        "node_config": {
            "context_strategy": "inherit",
            "method": "GET",
            "url": "https://example.test/third",
        },
    }

    first_output = registry.execute("network.http_request", first_node, context)
    second_output = registry.execute("network.http_request", port_override_node, context)
    third_output = registry.execute("network.http_request", inherited_node, context)

    assert first_output["network_context_id"] is not None
    assert second_output["network_context_id"] == first_output["network_context_id"]
    assert third_output["network_context_id"] == first_output["network_context_id"]
    assert service.snapshots[0].headers == {"X-Shared": "initial"}
    assert service.snapshots[1].headers == {"X-Shared": "port-input"}
    assert service.snapshots[2].headers == {"X-Shared": "initial"}


def test_network_http_request_writes_set_cookie_back_to_current_context() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.snapshots: list[NetworkContextSnapshot] = []

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            self.snapshots.append(snapshot)
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    set_cookies={"sid": "response-cookie"}
                    if len(self.snapshots) == 1
                    else {},
                )
            )
            return future

    service = StubNetworkRuntimeService()
    registry = RuntimeExecutorRegistry(network_runtime_service=service)
    context = RuntimeContext()
    first = {
        "node_id": "cookie-first",
        "node_kind": "network.http_request",
        "node_config": {"context_strategy": "new", "url": "https://example.test/first"},
    }
    second = {
        "node_id": "cookie-second",
        "node_kind": "network.http_request",
        "node_config": {"context_strategy": "inherit", "url": "https://example.test/second"},
    }

    registry.execute("network.http_request", first, context)
    registry.execute("network.http_request", second, context)

    assert service.snapshots[0].cookies == {}
    assert service.snapshots[1].cookies == {"sid": "response-cookie"}


def test_network_http_request_is_registered_as_a_builtin_component() -> None:
    registry = build_builtin_resource_registry()

    network_components = {
        item["resource_key"]: item
        for item in registry
        if item["resource_key"]
        in {"network.http_request", "network.upload", "network.download", "network.response_assert"}
    }

    assert set(network_components) == {
        "network.http_request",
        "network.upload",
        "network.download",
        "network.response_assert",
    }
    assert network_components["network.http_request"]["resource_id"] == "builtin:network.http_request"
