from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest
from httpx_sse import aconnect_sse

from weconduct.network_runtime.long_connection import SSEConnection, SSEConnectionClosed


@contextmanager
def _sse_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(
                b"id: event-local\n"
                b"event: update\n"
                b"data: first\n"
                b"data: second\n"
                b"retry: 2500\n\n"
            )
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


def test_sse_connection_queues_events_and_tracks_last_event_id() -> None:
    async def run() -> None:
        connection = SSEConnection(max_queue_size=2)
        await connection.feed(
            {"id": "event-1", "event": "message", "data": "{\"ok\":true}", "retry": 1500}
        )

        event = await connection.receive()

        assert event.event_id == "event-1"
        assert event.event_type == "message"
        assert event.data == '{"ok":true}'
        assert event.retry_ms == 1500
        assert connection.last_event_id == "event-1"
        assert connection.build_reconnect_headers() == {"Last-Event-ID": "event-1"}

    asyncio.run(run())


def test_sse_connection_close_wakes_receive() -> None:
    async def run() -> None:
        connection = SSEConnection()
        waiter = asyncio.create_task(connection.receive())
        await asyncio.sleep(0)
        await connection.close()

        with pytest.raises(SSEConnectionClosed):
            await waiter

    asyncio.run(run())


def test_sse_connection_keeps_queued_events_available_after_stream_closes() -> None:
    async def run() -> None:
        connection = SSEConnection()
        await connection.feed({"id": "queued-event", "data": "queued-payload"})
        await connection.close()

        event = await connection.receive()

        assert event.event_id == "queued-event"
        assert event.data == "queued-payload"
        with pytest.raises(SSEConnectionClosed, match="network.sse_closed"):
            await connection.receive()

    asyncio.run(run())


def test_sse_connection_consumes_real_httpx_sse_stream() -> None:
    async def run() -> None:
        with _sse_server() as url:
            connection = SSEConnection()
            async with httpx.AsyncClient(timeout=2) as client:
                async with aconnect_sse(client, "GET", url) as source:
                    async for parsed_event in source.aiter_sse():
                        await connection.feed(parsed_event)
                        break
                    event = await connection.receive()

            assert event.event_id == "event-local"
            assert event.event_type == "update"
            assert event.data == "first\nsecond"
            assert event.retry_ms == 2500

    asyncio.run(run())
