from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import json

import websockets

from weconduct.network_runtime.long_connection import SSEClientHandle, WebSocketClientHandle
from weconduct.network_runtime.long_connection import SSEConnection
from weconduct.network_runtime.access_policy import NetworkAccessPolicy


_LOCAL_ACCESS_POLICY = NetworkAccessPolicy(allow_loopback=True)


@contextmanager
def _blocking_sse_server():
    keep_open = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"id: one\ndata: first\n\n")
            self.wfile.flush()
            keep_open.wait(timeout=5)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/events"
    finally:
        keep_open.set()
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


def test_sse_client_close_is_idempotent_and_stops_owned_loop() -> None:
    with _blocking_sse_server() as url:
        handle = SSEClientHandle(url=url, access_policy=_LOCAL_ACCESS_POLICY)
        handle.start()
        assert handle.receive(timeout_seconds=1)["event_id"] == "one"
        handle.close()
        handle.close()

        assert handle._loop._thread.is_alive() is False  # type: ignore[attr-defined]


def test_sse_connection_close_wakes_waiters_even_when_event_queue_is_full() -> None:
    async def run() -> None:
        connection = SSEConnection(max_queue_size=1)
        await connection.feed({"id": "queued", "data": "value"})
        await asyncio.wait_for(connection.close(), timeout=0.2)

    asyncio.run(run())


def test_websocket_client_close_is_idempotent_and_stops_owned_loop() -> None:
    ready = Event()
    stop = Event()
    server_info: dict[str, object] = {}

    async def handler(socket) -> None:
        await socket.recv()
        await socket.send(json.dumps({"ok": True}))
        while not stop.is_set():
            await asyncio.sleep(0.01)

    def server_thread() -> None:
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)

        async def run_server() -> None:
            server = await websockets.serve(handler, "127.0.0.1", 0)
            server_info["server"] = server
            server_info["port"] = server.sockets[0].getsockname()[1]
            ready.set()
            while not stop.is_set():
                await asyncio.sleep(0.01)
            server.close()
            await server.wait_closed()

        try:
            loop.run_until_complete(run_server())
        finally:
            loop.close()

    thread = Thread(target=server_thread, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    handle = WebSocketClientHandle(
        url=f"ws://127.0.0.1:{server_info['port']}",
        access_policy=_LOCAL_ACCESS_POLICY,
    )
    try:
        handle.start()
        handle.send("ping")
        assert json.loads(handle.receive(timeout_seconds=1)) == {"ok": True}
    finally:
        handle.close()
        handle.close()
        stop.set()
        thread.join(timeout=2)

    assert handle._loop._thread.is_alive() is False  # type: ignore[attr-defined]
