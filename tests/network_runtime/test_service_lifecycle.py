from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
from threading import Thread
from time import sleep

import httpx

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService
from weconduct.application.sensitive_values.service import SensitiveValueService


@contextmanager
def _local_http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/ok")
                self.end_headers()
                return
            if self.path == "/slow":
                sleep(0.2)
            status_code = {
                "/ok": 200,
                "/missing": 404,
                "/error": 500,
                "/slow": 200,
            }.get(self.path, 404)
            self.send_response(status_code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(status_code).encode("ascii"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@contextmanager
def _local_sse_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"id: service-event\\ndata: payload\\n\\n")
            self.wfile.flush()
            sleep(1)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/events"
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def test_network_runtime_service_executes_on_its_owned_loop_and_closes_cleanly(tmp_path) -> None:
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(204, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    operation = NetworkOperation(
        operation_id="request-1",
        session_id="session-1",
        method="GET",
        url="https://example.test/ok",
    )

    result = service.submit(
        operation,
        NetworkContextSnapshot(context_id="context-1"),
    ).result(timeout=1)
    service.close()

    assert result.status_code == 204
    assert service.is_closed is True


def test_network_runtime_service_resolves_and_caches_oauth_client_credentials(tmp_path) -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path == "/token":
            return httpx.Response(
                200,
                request=request,
                json={"access_token": "oauth-access-token", "token_type": "Bearer", "expires_in": 60},
            )
        assert request.headers["Authorization"] == "Bearer oauth-access-token"
        return httpx.Response(204, request=request)

    sensitive_values = SensitiveValueService()
    secret = sensitive_values.create(
        "oauth-client-secret",
        scope_id="oauth-session",
        source="runtime_input",
    )
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=sensitive_values,
    )
    snapshot = NetworkContextSnapshot(
        context_id="oauth-context",
        auth={
            "type": "oauth_client_credentials",
            "token_url": "https://example.test/token",
            "client_id": "oauth-client",
            "client_secret": secret,
            "scope": "read",
        },
    )
    try:
        for operation_id in ("oauth-request-1", "oauth-request-2"):
            result = service.submit(
                NetworkOperation(
                    operation_id=operation_id,
                    session_id="oauth-session",
                    method="GET",
                    url="https://example.test/resource",
                ),
                snapshot,
            ).result(timeout=2)
            assert result.status_code == 204
    finally:
        service.close()

    assert [request.url.path for request in observed] == ["/token", "/resource", "/resource"]
    assert all("oauth-client-secret" not in repr(request) for request in observed)


def test_network_runtime_service_returns_structured_error_for_invalid_oauth_config(tmp_path) -> None:
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(lambda request: httpx.Response(204, request=request)),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=SensitiveValueService(),
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="oauth-invalid",
                session_id="oauth-invalid-session",
                method="GET",
                url="https://example.test/resource",
                node_id="oauth-invalid-node",
            ),
            NetworkContextSnapshot(
                context_id="oauth-invalid-context",
                auth={"type": "oauth_client_credentials"},
            ),
        ).result(timeout=2)
    finally:
        service.close()

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.error_code == "network.oauth_failed"
    assert result.error.node_id == "oauth-invalid-node"
    assert result.error.network_context_id == "oauth-invalid-context"


def test_network_runtime_service_refreshes_cached_oauth_token(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/token":
            grant_type = request.content.decode("utf-8")
            if "refresh_token" in grant_type:
                return httpx.Response(
                    200,
                    request=request,
                    json={"access_token": "refreshed-access", "expires_in": 60},
                )
            return httpx.Response(
                200,
                request=request,
                json={"access_token": "initial-access", "refresh_token": "refresh-secret", "expires_in": 60},
            )
        return httpx.Response(204, request=request)

    sensitive_values = SensitiveValueService()
    client_secret = sensitive_values.create("client-secret", scope_id="refresh-session", source="runtime_input")
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=sensitive_values,
    )
    snapshot = NetworkContextSnapshot(
        context_id="refresh-context",
        auth={
            "type": "oauth_client_credentials",
            "token_url": "https://example.test/token",
            "client_id": "oauth-client",
            "client_secret": client_secret,
        },
    )
    try:
        first = service.submit(
            NetworkOperation("oauth-refresh-1", "refresh-session", "GET", "https://example.test/resource"),
            snapshot,
        ).result(timeout=2)
        key = ("refresh-session", "refresh-context")
        service._oauth_tokens[key] = replace(service._oauth_tokens[key], expires_at=0)  # type: ignore[attr-defined]
        second = service.submit(
            NetworkOperation("oauth-refresh-2", "refresh-session", "GET", "https://example.test/resource"),
            snapshot,
        ).result(timeout=2)
    finally:
        service.close()

    assert first.status_code == second.status_code == 204
    assert [request.url.path for request in requests] == ["/token", "/resource", "/token", "/resource"]
    assert "grant_type=refresh_token" in requests[2].content.decode("utf-8")
    assert requests[3].headers["Authorization"] == "Bearer refreshed-access"


def test_network_runtime_service_cancels_active_session_requests(tmp_path) -> None:
    async def slow_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(204, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(slow_response),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    future = service.submit(
        NetworkOperation(
            operation_id="request-cancel",
            session_id="session-cancel",
            method="GET",
            url="https://example.test/slow",
        ),
        NetworkContextSnapshot(context_id="context-1"),
    )
    service.cancel_session("session-cancel")
    result = future.result(timeout=1)
    service.close()

    assert result.status == "failed"
    assert result.transport_error == "network.cancelled"
    assert result.error is not None
    assert result.error.error_code == "network.cancelled"
    assert result.error.request_id is not None
    assert result.error.request_id.startswith("request-cancel-")
    assert result.error.network_context_id == "context-1"
    assert result.error.retry_attempt == 1


def test_network_runtime_service_reuses_its_single_async_client(tmp_path) -> None:
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(204, request=request)
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    client = service._client  # type: ignore[attr-defined]

    for operation_id in ("request-1", "request-2"):
        result = service.submit(
            NetworkOperation(
                operation_id=operation_id,
                session_id="session-1",
                method="GET",
                url="https://example.test/ok",
            ),
            NetworkContextSnapshot(context_id="context-1"),
        ).result(timeout=1)
        assert result.status_code == 204
        assert service._client is client  # type: ignore[attr-defined]

    service.close()
    assert client.is_closed is True


def test_network_runtime_service_retries_configured_retryable_statuses(tmp_path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        status_code = 503 if attempts == 1 else 200
        return httpx.Response(status_code, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="retry-status",
                session_id="retry-status-session",
                method="GET",
                url="https://example.test/retry",
            ),
            NetworkContextSnapshot(
                context_id="retry-status-context",
                retry_policy={
                    "max_attempts": 2,
                    "retry_status_codes": [503],
                    "initial_delay_seconds": 0,
                    "jitter_ratio": 0,
                },
            ),
        ).result(timeout=1)
    finally:
        service.close()

    assert attempts == 2
    assert result.status == "succeeded"
    assert result.status_code == 200


def test_network_runtime_service_does_not_retry_non_idempotent_method_without_opt_in(tmp_path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="retry-post",
                session_id="retry-post-session",
                method="POST",
                url="https://example.test/retry",
                content=b"body",
            ),
            NetworkContextSnapshot(
                context_id="retry-post-context",
                retry_policy={
                    "max_attempts": 2,
                    "retry_status_codes": [503],
                    "initial_delay_seconds": 0,
                    "jitter_ratio": 0,
                },
            ),
        ).result(timeout=1)
    finally:
        service.close()

    assert attempts == 1
    assert result.status == "succeeded"
    assert result.status_code == 503


def test_network_runtime_service_applies_auth_and_tls_snapshot_to_sse_handle(
    tmp_path,
    monkeypatch,
) -> None:
    import weconduct.network_runtime.service as service_module

    captured: dict[str, object] = {}

    class StubSSEClientHandle:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def start(self, *, timeout_seconds: float) -> dict[str, object]:
            return {"status_code": 200, "headers": {}, "url": "https://example.test/events"}

        def close(self) -> None:
            return None

    monkeypatch.setattr(service_module, "SSEClientHandle", StubSSEClientHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        service.connect_sse(
            session_id="sse-auth-tls",
            snapshot=NetworkContextSnapshot(
                context_id="sse-auth-tls-context",
                auth={"type": "bearer", "token": "stream-token"},
                tls={"certificate_pins": ["a" * 64]},
            ),
            url="https://example.test/events",
        )
    finally:
        service.close()

    assert captured["headers"] == {"Authorization": "Bearer stream-token"}
    assert isinstance(captured["ssl_context"], ssl.SSLContext)
    assert captured["certificate_pins"] == ("a" * 64,)


def test_network_runtime_service_applies_oauth_credentials_to_sse_handle(tmp_path, monkeypatch) -> None:
    import weconduct.network_runtime.service as service_module

    captured: dict[str, object] = {}

    class StubSSEClientHandle:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def start(self, *, timeout_seconds: float) -> dict[str, object]:
            return {"status_code": 200, "headers": {}, "url": "https://example.test/events"}

        def close(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        return httpx.Response(200, request=request, json={"access_token": "stream-token", "expires_in": 60})

    monkeypatch.setattr(service_module, "SSEClientHandle", StubSSEClientHandle)
    sensitive_values = SensitiveValueService()
    secret = sensitive_values.create("stream-secret", scope_id="oauth-sse", source="runtime_input")
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=sensitive_values,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="oauth-sse",
            snapshot=NetworkContextSnapshot(
                context_id="oauth-sse-context",
                auth={
                    "type": "oauth_client_credentials",
                    "token_url": "https://example.test/token",
                    "client_id": "stream-client",
                    "client_secret": secret,
                },
            ),
            url="https://example.test/events",
        )
        service.release_connection("oauth-sse", handle)
    finally:
        service.close()

    assert captured["headers"] == {"Authorization": "Bearer stream-token"}


def test_network_runtime_service_real_local_http_semantics(tmp_path) -> None:
    with _local_http_server() as base_url:
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            results = {
                path: service.submit(
                    NetworkOperation(
                        operation_id=f"request-{path[1:]}",
                        session_id="session-local-http",
                        method="GET",
                        url=f"{base_url}{path}",
                        timeout_seconds=0.05 if path == "/slow" else 1,
                    ),
                    NetworkContextSnapshot(context_id="context-1"),
                ).result(timeout=2)
                for path in ("/ok", "/missing", "/error", "/redirect", "/slow")
            }
        finally:
            service.close()

    assert results["/ok"].status_code == 200
    assert results["/missing"].status_code == 404
    assert results["/error"].status_code == 500
    assert results["/redirect"].status_code == 200
    assert results["/redirect"].final_url == f"{base_url}/ok"
    assert results["/slow"].status == "failed"
    assert results["/slow"].transport_error is not None


def test_network_runtime_service_cancels_service_owned_sse_connections(tmp_path) -> None:
    with _local_sse_server() as url:
        service = NetworkRuntimeService(
            response_root_directory=tmp_path,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            handle, metadata = service.connect_sse(
                session_id="session-sse",
                snapshot=NetworkContextSnapshot(context_id="context-sse"),
                url=url,
                timeout_seconds=1,
            )
            assert metadata["status_code"] == 200
            service.cancel_session("session-sse")
            assert handle._closed is True  # type: ignore[attr-defined]
        finally:
            service.close()
