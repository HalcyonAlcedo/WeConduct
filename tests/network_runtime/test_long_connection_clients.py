from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import websockets

from weconduct.network_runtime.long_connection import (
    SSEClientHandle,
    WebSocketClientHandle,
)


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
        handle = SSEClientHandle(url=url)
        metadata = handle.start(timeout_seconds=2)
        try:
            assert metadata["status_code"] == 200
            event = handle.receive(timeout_seconds=2)
            assert event["event_id"] == "event-client"
            assert event["event_type"] == "update"
            assert event["data"] == "payload"
        finally:
            handle.close()


def test_websocket_client_handle_supports_pull_operations_and_close() -> None:
    async def run() -> None:
        async def handler(socket) -> None:
            value = await socket.recv()
            await socket.send(f"ack:{value}")
            await asyncio.sleep(5)

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        handle = WebSocketClientHandle(url=f"ws://127.0.0.1:{port}")
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


def test_long_connection_client_rejects_receive_after_close() -> None:
    handle = SSEClientHandle(url="http://127.0.0.1:1/events")
    handle.close()

    with pytest.raises(RuntimeError, match="closed"):
        handle.receive(timeout_seconds=0.1)


def test_websocket_client_receive_honors_operation_timeout() -> None:
    async def run() -> None:
        async def handler(socket) -> None:
            await asyncio.sleep(5)

        server = await websockets.serve(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        handle = WebSocketClientHandle(url=f"ws://127.0.0.1:{port}")
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
    sse = SSEClientHandle(url="https://example.test/events", proxy="http://proxy.example.test:8080")
    websocket = WebSocketClientHandle(
        url="wss://example.test/events",
        proxy="socks5h://proxy.example.test:1080",
    )

    try:
        assert sse.proxy == "http://proxy.example.test:8080"
        assert websocket.proxy == "socks5h://proxy.example.test:1080"
    finally:
        sse.close()
        websocket.close()
