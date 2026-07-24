from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Event, Thread

import asyncio
import websockets

from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


@contextmanager
def _sse_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"id: node-event\nevent: update\ndata: node-payload\n\n")
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


class _WebSocketServer:
    def __init__(self) -> None:
        self._ready: Queue[int] = Queue(maxsize=1)
        self._stop = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        self.port = self._ready.get(timeout=2)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        async def main() -> None:
            async def handler(socket) -> None:
                async for value in socket:
                    await socket.send(f"ack:{value}")

            server = await websockets.serve(handler, "127.0.0.1", 0)
            self._ready.put(server.sockets[0].getsockname()[1])
            while not self._stop.is_set():
                await asyncio.sleep(0.01)
            server.close()
            await server.wait_closed()

        asyncio.run(main())


def test_network_sse_connect_node_supports_connect_receive_and_close() -> None:
    with _sse_server() as url:
        context = RuntimeContext()
        registry = RuntimeExecutorRegistry()
        try:
            connected = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-connect",
                    "node_kind": "network.sse_connect",
                    "node_config": {"url": url, "connection_id": "stream"},
                },
                context,
            )
            assert connected["status"] == "succeeded"
            assert connected["connection_id"] == "stream"

            received = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-receive",
                    "node_kind": "network.sse_connect",
                    "node_config": {
                        "action": "receive",
                        "connection_id": "stream",
                        "timeout_seconds": 2,
                    },
                },
                context,
            )
            assert received["status"] == "succeeded"
            assert received["event_id"] == "node-event"
            assert received["data"] == "node-payload"

            closed = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-close",
                    "node_kind": "network.sse_connect",
                    "node_config": {"action": "close", "connection_id": "stream"},
                },
                context,
            )
            assert closed["status"] == "succeeded"
        finally:
            context.close()


def test_network_websocket_connect_node_supports_send_receive_ping_and_close() -> None:
    server = _WebSocketServer()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry()
    try:
        url = f"ws://127.0.0.1:{server.port}"
        connected = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-connect",
                "node_kind": "network.websocket_connect",
                "node_config": {"url": url, "connection_id": "socket"},
            },
            context,
        )
        assert connected["status"] == "succeeded"

        sent = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-send",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "action": "send",
                    "connection_id": "socket",
                    "value": "hello",
                },
            },
            context,
        )
        assert sent["status"] == "succeeded"
        received = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-receive",
                "node_kind": "network.websocket_connect",
                "node_config": {"action": "receive", "connection_id": "socket"},
            },
            context,
        )
        assert received["message"] == "ack:hello"
        assert registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-ping",
                "node_kind": "network.websocket_connect",
                "node_config": {"action": "ping", "connection_id": "socket"},
            },
            context,
        )["status"] == "succeeded"
        assert registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-close",
                "node_kind": "network.websocket_connect",
                "node_config": {"action": "close", "connection_id": "socket"},
            },
            context,
        )["status"] == "succeeded"
    finally:
        context.close()
        server.close()
