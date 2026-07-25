from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from threading import Thread
from urllib.parse import urlsplit

import pytest
import websockets

from weconduct.network_runtime.long_connection import (
    SSEClientHandle,
    WebSocketClientHandle,
)
from weconduct.network_runtime.access_policy import NetworkAccessPolicy


_LOCAL_ACCESS_POLICY = NetworkAccessPolicy(allow_loopback=True)


@contextmanager
def _sse_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"id: event-client\nevent: update\ndata: payload\n\n")
            self.wfile.flush()

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


def test_sse_client_handle_connects_and_pulls_events() -> None:
    with _sse_server() as url:
        handle = SSEClientHandle(url=url, access_policy=_LOCAL_ACCESS_POLICY)
        metadata = handle.start(timeout_seconds=2)
        try:
            assert metadata["status_code"] == 200
            event = handle.receive(timeout_seconds=2)
            assert event["event_id"] == "event-client"
            assert event["event_type"] == "update"
            assert event["data"] == "payload"
        finally:
            handle.close()


def test_sse_client_handle_uses_its_prevalidated_dns_answer(monkeypatch) -> None:
    with _sse_server() as local_url:
        parsed = urlsplit(local_url)
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
        handle = SSEClientHandle(
            url=f"http://rebind.example.test:{parsed.port}{parsed.path}",
            access_policy=_LOCAL_ACCESS_POLICY,
        )
        try:
            handle.start(timeout_seconds=2)
            assert handle.receive(timeout_seconds=2)["data"] == "payload"
        finally:
            handle.close()

    assert hostname_resolution_count == 1


def test_websocket_client_handle_supports_pull_operations_and_close() -> None:
    async def run() -> None:
        async def handler(socket) -> None:
            value = await socket.recv()
            await socket.send(f"ack:{value}")
            await asyncio.sleep(5)

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        handle = WebSocketClientHandle(
            url=f"ws://127.0.0.1:{port}",
            access_policy=_LOCAL_ACCESS_POLICY,
        )
        try:
            metadata = await asyncio.to_thread(handle.start, timeout_seconds=2)
            assert metadata["status"] == "connected"
            await asyncio.to_thread(handle.send, "hello")
            assert await asyncio.to_thread(handle.receive, timeout_seconds=2) == "ack:hello"
            await asyncio.to_thread(handle.ping, b"keepalive")
        finally:
            await asyncio.to_thread(handle.close)
            server.close()
            await server.wait_closed()

    import asyncio

    asyncio.run(run())


def test_websocket_client_handle_uses_its_prevalidated_dns_answer(monkeypatch) -> None:
    async def run() -> None:
        async def handler(connection) -> None:
            await connection.wait_closed()

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        hostname_resolution_count = 0
        original_getaddrinfo = socket.getaddrinfo

        def resolve_target(host: str, target_port: int | None, *args: object, **kwargs: object):
            nonlocal hostname_resolution_count
            if host == "rebind.example.test":
                hostname_resolution_count += 1
                return [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        ("127.0.0.1", target_port),
                    )
                ]
            return original_getaddrinfo(host, target_port, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", resolve_target)
        handle = WebSocketClientHandle(
            url=f"ws://rebind.example.test:{port}/events",
            access_policy=_LOCAL_ACCESS_POLICY,
        )
        try:
            metadata = await asyncio.to_thread(handle.start, timeout_seconds=2)
            assert metadata["status"] == "connected"
        finally:
            await asyncio.to_thread(handle.close)
            server.close()
            await server.wait_closed()

        assert hostname_resolution_count == 1

    import asyncio

    asyncio.run(run())


def test_long_connection_client_rejects_receive_after_close() -> None:
    handle = SSEClientHandle(
        url="http://127.0.0.1:1/events",
        access_policy=_LOCAL_ACCESS_POLICY,
    )
    handle.close()

    with pytest.raises(RuntimeError, match="closed"):
        handle.receive(timeout_seconds=0.1)


def test_websocket_client_receive_honors_operation_timeout() -> None:
    async def run() -> None:
        async def handler(socket) -> None:
            await asyncio.sleep(5)

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        handle = WebSocketClientHandle(
            url=f"ws://127.0.0.1:{port}",
            access_policy=_LOCAL_ACCESS_POLICY,
        )
        try:
            await asyncio.to_thread(handle.start, timeout_seconds=2)
            with pytest.raises(TimeoutError, match="receive_timeout"):
                await asyncio.to_thread(handle.receive, timeout_seconds=0.05)
        finally:
            await asyncio.to_thread(handle.close)
            server.close()
            await server.wait_closed()

    import asyncio

    asyncio.run(run())


def test_long_connection_clients_keep_explicit_proxy_configuration() -> None:
    fixture_policy = NetworkAccessPolicy(allowed_hostnames=frozenset({"example.test"}))
    sse = SSEClientHandle(
        url="https://example.test/events",
        proxy="http://proxy.example.test:8080",
        access_policy=fixture_policy,
    )
    websocket = WebSocketClientHandle(
        url="wss://example.test/events",
        proxy="socks5h://proxy.example.test:1080",
        access_policy=fixture_policy,
    )

    try:
        assert sse.proxy == "http://proxy.example.test:8080"
        assert websocket.proxy == "socks5h://proxy.example.test:1080"
    finally:
        sse.close()
        websocket.close()


def test_long_connection_clients_apply_default_network_access_policy() -> None:
    with pytest.raises(ValueError, match="network.access_denied"):
        SSEClientHandle(url="http://127.0.0.1:1/events")
    with pytest.raises(ValueError, match="network.access_denied"):
        WebSocketClientHandle(url="ws://127.0.0.1:1/events")
