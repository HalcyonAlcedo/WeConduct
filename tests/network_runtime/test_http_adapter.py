from __future__ import annotations

import asyncio
from concurrent.futures import Future
import socket
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.network_runtime.http_adapter import HttpxAdapter
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.models import NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.network_runtime.transport import PinnedDnsAsyncHTTPTransport
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


def test_httpx_adapter_default_client_uses_pinned_dns_transport(tmp_path) -> None:
    adapter = HttpxAdapter(response_root_directory=tmp_path)
    try:
        assert isinstance(adapter._client._transport, PinnedDnsAsyncHTTPTransport)
    finally:
        adapter.close()
        asyncio.run(adapter.aclose())


def test_httpx_adapter_binds_connection_to_prevalidated_dns_answer(
    tmp_path,
    monkeypatch,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    hostname_resolution_count = 0
    original_getaddrinfo = socket.getaddrinfo

    def resolve_target(host: str, port: int | None, *args: object, **kwargs: object):
        nonlocal hostname_resolution_count
        if host == "rebind.example.test":
            hostname_resolution_count += 1
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", port),
                )
            ]
        return original_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_target)
    adapter = HttpxAdapter(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allow_loopback=True),
    )
    try:
        result = adapter.execute(
            NetworkOperation(
                operation_id="dns-pin",
                session_id="dns-pin-session",
                method="GET",
                url=f"http://rebind.example.test:{server.server_port}/status",
            ),
            NetworkContextSnapshot(context_id="dns-pin-context"),
        )
    finally:
        adapter.close()
        asyncio.run(adapter.aclose())
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()

    assert result.status == "succeeded"
    assert result.status_code == 204
    assert hostname_resolution_count == 1


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


def test_httpx_adapter_drops_credentials_cookies_and_source_query_on_cross_origin_redirect(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "source.example.test":
            return httpx.Response(
                302,
                headers={"location": "https://target.example.test/next?target=kept"},
                request=request,
            )
        return httpx.Response(200, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(
            allowed_hostnames={"source.example.test", "target.example.test"}
        ),
    )
    operation = NetworkOperation(
        operation_id="request-cross-origin-redirect",
        session_id="session-1",
        method="GET",
        url="https://source.example.test/start?source=url",
        headers={"Authorization": "Bearer operation-token"},
        query={"source": "operation"},
    )

    result = adapter.execute(
        operation,
        NetworkContextSnapshot(
            context_id="context-1",
            query={"source": "context"},
            cookies={"session": "context-cookie"},
        ),
    )

    assert result.status == "succeeded"
    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer operation-token"
    assert requests[0].headers["cookie"] == "session=context-cookie"
    assert str(requests[1].url) == "https://target.example.test/next?target=kept"
    assert "authorization" not in requests[1].headers
    assert "cookie" not in requests[1].headers


def test_httpx_adapter_returns_structured_error_context_for_policy_rejection(tmp_path) -> None:
    from weconduct.network_runtime.errors import NetworkExecutionError

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
        operation_id="request-structured-error",
        session_id="session-structured-error",
        method="GET",
        url="https://example.test/redirect",
    )

    result = adapter.execute(
        operation,
        NetworkContextSnapshot(context_id="context-structured-error"),
    )

    assert isinstance(result.error, NetworkExecutionError)
    assert result.error.error_code == "network.access_denied"
    assert result.error.request_id == operation.request_id
    assert result.error.node_id is None
    assert result.error.network_context_id == "context-structured-error"
    assert result.error.retry_attempt == 1


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


def test_httpx_adapter_applies_static_bearer_auth_from_network_context(tmp_path) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        result = adapter.execute(
            NetworkOperation(
                operation_id="request-auth",
                session_id="session-auth",
                method="GET",
                url="https://example.test/auth",
            ),
            NetworkContextSnapshot(
                context_id="context-auth",
                auth={"type": "bearer", "token": "context-token"},
            ),
        )
    finally:
        adapter.close()

    assert result.status == "succeeded"
    assert observed["authorization"] == "Bearer context-token"


def test_httpx_adapter_applies_static_basic_auth_from_network_context(tmp_path) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, request=request)

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        result = adapter.execute(
            NetworkOperation(
                operation_id="request-auth-basic",
                session_id="session-auth-basic",
                method="GET",
                url="https://example.test/auth",
            ),
            NetworkContextSnapshot(
                context_id="context-auth-basic",
                auth={"type": "basic", "username": "alice", "password": "secret"},
            ),
        )
    finally:
        adapter.close()

    assert result.status == "succeeded"
    assert observed["authorization"] == "Basic YWxpY2U6c2VjcmV0"


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


def test_httpx_adapter_resolves_environment_proxy_without_silent_direct_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test:3128")
    adapter = HttpxAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )

    client = adapter._client_for_snapshot(  # type: ignore[attr-defined]
        NetworkContextSnapshot(
            context_id="proxy-env",
            proxy={"mode": "environment"},
        ),
        "https://example.test/api",
    )

    assert client is not adapter._client  # type: ignore[attr-defined]


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

    sensitive_values = SensitiveValueService()
    service = StubNetworkRuntimeService()
    registry = RuntimeExecutorRegistry(network_runtime_service=service)
    context = RuntimeContext(flow_runtime={"sensitive_value_service": sensitive_values})
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
    response_cookie = service.snapshots[1].cookies["sid"]
    assert isinstance(response_cookie, SensitiveRef)
    assert sensitive_values.resolve(
        response_cookie,
        consumer=SensitiveConsumer.NETWORK_RUNTIME,
    ) == "response-cookie"


def test_network_http_request_forwards_node_auth_tls_and_proxy_to_service_snapshot() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.snapshot: NetworkContextSnapshot | None = None
            self.operation: NetworkOperation | None = None

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
                    status_code=200,
                )
            )
            return future

    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.http_request",
        {
            "node_id": "network-configured-request",
            "node_kind": "network.http_request",
            "node_config": {
                "context_strategy": "new",
                "url": "https://example.test/resource",
                "auth": {"type": "bearer", "token": "runtime-token"},
                "tls": {"verify": "insecure"},
                "proxy": {"mode": "manual", "url": "http://proxy.example.test:8080"},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.snapshot is not None
    assert isinstance(service.snapshot.auth, dict)
    assert service.snapshot.auth["type"] == "bearer"
    assert isinstance(service.snapshot.auth["token"], SensitiveRef)
    assert service.snapshot.tls == {"verify": "insecure"}
    assert service.snapshot.proxy == {"mode": "manual", "url": "http://proxy.example.test:8080"}


def test_network_http_request_converts_node_credentials_to_sensitive_refs() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.snapshot: NetworkContextSnapshot | None = None
            self.operation: NetworkOperation | None = None

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
                    status_code=200,
                )
            )
            return future

    sensitive_values = SensitiveValueService()
    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.http_request",
        {
            "node_id": "network-sensitive-request",
            "node_kind": "network.http_request",
            "node_config": {
                "context_strategy": "new",
                "url": "https://example.test/resource",
                "headers": {
                    "Authorization": "Bearer node-header-secret",
                    "Cookie": "session=node-cookie-secret",
                    "Accept": "application/json",
                },
                "auth": {
                    "type": "basic",
                    "username": "node-basic-user",
                    "password": "node-basic-password",
                },
                "proxy": {
                    "mode": "manual",
                    "url": "http://proxy-user:proxy-password@proxy.example.test:8080",
                },
            },
        },
        RuntimeContext(flow_runtime={"sensitive_value_service": sensitive_values}),
    )

    assert output["status"] == "succeeded"
    assert service.snapshot is not None
    assert isinstance(service.snapshot.auth, dict)
    assert isinstance(service.snapshot.auth["username"], SensitiveRef)
    assert isinstance(service.snapshot.auth["password"], SensitiveRef)
    assert sensitive_values.resolve(
        service.snapshot.auth["username"],
        consumer=SensitiveConsumer.NETWORK_RUNTIME,
    ) == "node-basic-user"
    assert isinstance(service.snapshot.headers["Authorization"], SensitiveRef)
    assert isinstance(service.snapshot.headers["Cookie"], SensitiveRef)
    assert service.snapshot.headers["Accept"] == "application/json"
    assert service.operation is not None
    assert isinstance(service.operation.headers["Authorization"], SensitiveRef)
    assert isinstance(service.operation.headers["Cookie"], SensitiveRef)
    assert isinstance(service.snapshot.proxy, dict)
    assert service.snapshot.proxy["url"] == "http://proxy.example.test:8080"
    assert isinstance(service.snapshot.proxy["username"], SensitiveRef)
    assert isinstance(service.snapshot.proxy["password"], SensitiveRef)
    assert "node-header-secret" not in repr(service.snapshot)
    assert "proxy-password" not in repr(service.snapshot)


def test_network_http_request_preserves_sensitive_header_port_input_as_a_reference() -> None:
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
                    status_code=200,
                )
            )
            return future

    sensitive_values = SensitiveValueService()
    context = RuntimeContext(flow_runtime={"sensitive_value_service": sensitive_values})
    header_token = sensitive_values.create(
        "Bearer runtime-port-secret",
        scope_id=context.execution_session_context.session_id,
        source="runtime_input",
    )
    context.variables["header_token"] = header_token
    service = StubNetworkRuntimeService()

    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.http_request",
        {
            "node_id": "network-sensitive-header-port",
            "node_kind": "network.http_request",
            "node_config": {
                "context_strategy": "new",
                "url": "https://example.test/resource",
                "headers": {"Authorization": "${header_token}"},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert service.snapshot is not None
    assert service.operation is not None
    assert isinstance(service.snapshot.headers["Authorization"], SensitiveRef)
    assert isinstance(service.operation.headers["Authorization"], SensitiveRef)
    assert sensitive_values.resolve(
        service.operation.headers["Authorization"],
        consumer=SensitiveConsumer.NETWORK_RUNTIME,
    ) == "Bearer runtime-port-secret"


def test_network_http_request_is_registered_as_a_builtin_component() -> None:
    registry = build_builtin_resource_registry()

    network_components = {
        item["resource_key"]: item
        for item in registry
        if item["resource_key"]
        in {
            "network.http_request",
            "network.upload",
            "network.download",
            "network.response_assert",
            "network.graphql_request",
            "network.sse_connect",
            "network.websocket_connect",
            "network.batch_request",
        }
    }

    assert set(network_components) == {
        "network.http_request",
        "network.upload",
        "network.download",
        "network.response_assert",
        "network.graphql_request",
        "network.sse_connect",
        "network.websocket_connect",
        "network.batch_request",
    }
    assert network_components["network.http_request"]["resource_id"] == "builtin:network.http_request"
    assert network_components["network.graphql_request"]["resource_id"] == "builtin:network.graphql_request"
    assert network_components["network.sse_connect"]["resource_id"] == "builtin:network.sse_connect"
    assert network_components["network.websocket_connect"]["resource_id"] == "builtin:network.websocket_connect"
    assert network_components["network.batch_request"]["resource_id"] == "builtin:network.batch_request"


def test_legacy_http_request_is_not_exposed_or_executed() -> None:
    builtin_keys = {
        item["resource_key"]
        for item in build_builtin_resource_registry()
        if isinstance(item.get("resource_key"), str)
    }
    registry = RuntimeExecutorRegistry()

    result = registry.execute(
        "http.request",
        {"node_id": "legacy-http", "node_kind": "http.request", "node_config": {}},
        RuntimeContext(),
    )

    assert "http.request" not in builtin_keys
    assert result["status"] == "failed"
    assert result["error_code"] == "graph.upgrade_required"
