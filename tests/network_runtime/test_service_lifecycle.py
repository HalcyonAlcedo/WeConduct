from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep

import httpx

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService


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
