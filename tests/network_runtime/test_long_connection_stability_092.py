from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import time

import pytest

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.long_connection import (
    SSEClientHandle,
    WebSocketClientHandle,
    WebSocketConnection,
    WebSocketConnectionError,
)


def test_websocket_connection_drops_oldest_under_long_burst() -> None:
    async def scenario() -> None:
        class Socket:
            def __init__(self) -> None:
                self.frames = iter([f"frame-{index}" for index in range(1, 33)])
                self.closed = False

            async def recv(self) -> object:
                try:
                    return next(self.frames)
                except StopIteration as exc:
                    raise RuntimeError("socket drained") from exc

            async def close(self) -> None:
                self.closed = True

        connection = WebSocketConnection(
            Socket(),
            max_queue_size=4,
            backpressure_policy="drop_oldest",
            connection_id="ws-burst",
        )
        await connection.start_receiver()
        await connection.wait_closed()

        assert connection.dropped_count == 28
        assert connection.queue_depth == 4
        assert connection.queue_status["connection_state"] == "disconnected"
        assert connection.activation_queue.dropped_count == 27

        await connection.close()
        assert connection.queue_status["closed"] is True

    asyncio.run(scenario())


def test_websocket_client_handle_recovers_across_reconnect_and_cleans_thread(monkeypatch) -> None:
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, frames: list[object]) -> None:
            self.frames = iter(frames)
            self.closed = False

        async def send(self, value: object) -> None:
            return

        async def recv(self) -> object:
            try:
                value = next(self.frames)
            except StopIteration as exc:
                while not self.closed:
                    await asyncio.sleep(0.01)
                raise ConnectionError("socket closed") from exc
            if isinstance(value, BaseException):
                raise value
            return value

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    sockets = iter(
        [
            Socket(["first", "second", ConnectionError("dropped")]),
            Socket(["third", "fourth", ConnectionError("reconnect exhausted")]),
        ]
    )

    async def connect(*args, **kwargs):
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = WebSocketClientHandle(
        url="ws://127.0.0.1/events",
        access_policy=NetworkAccessPolicy(allow_loopback=True),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.05,
        reconnect_max_delay_seconds=0.05,
    )
    try:
        handle.start(timeout_seconds=2)

        observed = []
        for _ in range(4):
            observed.append(handle.receive(timeout_seconds=2))
            activation = handle.wait_next_activation(timeout_seconds=2)
            observed.append(activation["payload"]["message"]["payload"])

        assert observed == [
            "first",
            "first",
            "second",
            "second",
            "third",
            "third",
            "fourth",
            "fourth",
        ]
        assert handle.queue_status["connection_epoch"] == 2
        assert handle.queue_status["reconnect_count"] == 1
        assert handle.queue_status["connection_state"] == "failed"
        assert handle.queue_status["reconnect_reason"] == "network.websocket_reconnect_failed"
    finally:
        handle.close()

    assert handle._loop._thread.is_alive() is False  # noqa: SLF001


def test_sse_client_handle_recovers_across_multiple_stream_bursts() -> None:
    @contextmanager
    def server_context():
        state = {"requests": [], "next_event_id": 1}

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                first_event_id = state["next_event_id"]
                state["requests"].append(self.headers.get("Last-Event-ID"))
                payload_lines = []
                for event_id in range(first_event_id, first_event_id + 10):
                    payload_lines.append(f"id: event-{event_id}")
                    payload_lines.append(f"data: payload-{event_id}")
                    payload_lines.append("")
                state["next_event_id"] += 10
                body = ("\n".join(payload_lines) + "\n").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/events", state
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    with server_context() as (url, state):
        handle = SSEClientHandle(
            url=url,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
            max_reconnect_attempts=2,
            reconnect_delay_seconds=0,
            reconnect_max_delay_seconds=0,
        )
        try:
            handle.start(timeout_seconds=2)
            event_ids = [
                handle.receive(timeout_seconds=2)["event_id"]
                for _ in range(30)
            ]
            assert event_ids == [f"event-{index}" for index in range(1, 31)]
            assert state["requests"] == [None, "event-10", "event-20"]
            assert handle.queue_status["connection_epoch"] == 3
            assert handle.queue_status["reconnect_count"] == 2
            assert handle.queue_status["reconnect_reason"] == "network.sse_stream_closed"
            assert handle.last_event_id == "event-30"
        finally:
            handle.close()


def test_websocket_client_handle_preserves_failed_terminal_state_after_reconnect_exhaustion(
    monkeypatch,
) -> None:
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self) -> None:
            self.closed = False

        async def recv(self) -> object:
            raise RuntimeError("peer closed with token=secret")

        async def send(self, value: object) -> None:
            return

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    async def connect(*args, **kwargs):
        return Socket()

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=0,
    )
    try:
        handle.start(timeout_seconds=2)
        deadline = time.monotonic() + 1
        while handle.queue_status["connection_state"] != "failed":
            if time.monotonic() >= deadline:
                raise AssertionError("connection never entered failed state")
            time.sleep(0.01)
        assert handle.queue_status["reconnect_reason"] == "network.websocket_reconnect_failed"
    finally:
        handle.close()


def test_websocket_client_handle_exposes_reconnecting_state_during_delay(monkeypatch) -> None:
    """WebSocket 在下一次连接建立前必须公开 reconnecting 状态。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)
            self.closed = False

        async def recv(self) -> object:
            try:
                value = next(self.values)
            except StopIteration:
                while not self.closed:
                    await asyncio.sleep(0.01)
                raise ConnectionError("socket closed")
            if isinstance(value, BaseException):
                raise value
            return value

        async def send(self, value: object) -> None:
            return

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    sockets = iter([Socket(["first", ConnectionError("dropped")]), Socket(["second"])])

    async def connect(*args, **kwargs):
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.25,
        reconnect_max_delay_seconds=0.25,
    )
    try:
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2) == "first"
        deadline = time.monotonic() + 1
        while handle.queue_status["connection_state"] != "reconnecting":
            if time.monotonic() >= deadline:
                raise AssertionError("WebSocket connection never entered reconnecting state")
            time.sleep(0.01)
    finally:
        handle.close()


def test_sse_client_handle_preserves_failed_terminal_state_after_stream_error(monkeypatch) -> None:
    async def fail_once(self, reconnecting: bool) -> None:
        self._ready.set()
        raise RuntimeError("stream failed with token=secret")

    monkeypatch.setattr(SSEClientHandle, "_run_once", fail_once)
    handle = SSEClientHandle(
        url="https://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=0,
    )
    try:
        with pytest.raises(RuntimeError, match="stream failed"):
            handle.start(timeout_seconds=2)
        assert handle.connection.queue_status["connection_state"] == "failed"
        assert handle.connection.queue_status["reconnect_reason"] == "network.sse_reconnect_failed"
    finally:
        handle.close()


def test_sse_client_handle_exposes_reconnecting_state_between_streams(monkeypatch) -> None:
    second_stream_ready = Event()
    release_second_stream = Event()
    attempts = 0

    async def run_once(self, reconnecting: bool) -> None:
        nonlocal attempts
        attempts += 1
        self.connection.mark_connected()
        self._ready.set()
        await self.connection.feed(
            {
                "id": f"event-{attempts}",
                "data": f"payload-{attempts}",
            }
        )
        if reconnecting:
            second_stream_ready.set()
            await asyncio.to_thread(release_second_stream.wait)

    monkeypatch.setattr(SSEClientHandle, "_run_once", run_once)
    handle = SSEClientHandle(
        url="https://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.1,
        reconnect_max_delay_seconds=0.1,
    )
    try:
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2)["data"] == "payload-1"
        deadline = time.monotonic() + 1
        while handle.queue_status["connection_state"] != "reconnecting":
            if time.monotonic() >= deadline:
                raise AssertionError("SSE connection never entered reconnecting state")
            time.sleep(0.01)
        while not second_stream_ready.is_set():
            if time.monotonic() >= deadline:
                raise AssertionError("SSE reconnect attempt never started")
            time.sleep(0.01)
        assert handle.queue_status["connection_state"] == "connected"
        release_second_stream.set()
    finally:
        handle.close()


def test_websocket_client_handle_short_soak_reconnects_and_releases_all_threads(monkeypatch) -> None:
    """连续多个重连 epoch 不能丢消息、阻塞激活队列或遗留客户端线程。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    epoch_count = 8
    messages_per_epoch = 64
    created_sockets: list["Socket"] = []

    class Socket:
        def __init__(self, epoch: int) -> None:
            self.epoch = epoch
            self.values = iter(
                [
                    f"epoch-{epoch}-message-{index}"
                    for index in range(messages_per_epoch)
                ]
            )
            self.closed = False

        async def recv(self) -> object:
            try:
                value = next(self.values)
            except StopIteration as exc:
                raise ConnectionError(f"epoch-{self.epoch}-closed") from exc
            await asyncio.sleep(0)
            return value

        async def send(self, value: object) -> None:
            return

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    async def connect(*args, **kwargs):
        epoch = len(created_sockets) + 1
        if epoch > epoch_count:
            raise AssertionError(f"unexpected reconnect epoch: {epoch}")
        socket = Socket(epoch)
        created_sockets.append(socket)
        return socket

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/soak",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        connection_id="short-soak",
        max_queue_size=epoch_count * messages_per_epoch,
        max_reconnect_attempts=epoch_count - 1,
        reconnect_delay_seconds=0,
        reconnect_max_delay_seconds=0,
    )
    expected = [
        f"epoch-{epoch}-message-{index}"
        for epoch in range(1, epoch_count + 1)
        for index in range(messages_per_epoch)
    ]
    observed: list[str] = []
    try:
        handle.start(timeout_seconds=2)
        for _ in expected:
            observed.append(handle.receive(timeout_seconds=2))
            activation = handle.wait_next_activation(timeout_seconds=2)
            assert activation["payload"]["message"]["payload"] == observed[-1]
        assert observed == expected
        assert handle.queue_status["connection_epoch"] == epoch_count
        assert handle.queue_status["reconnect_count"] == epoch_count - 1
    finally:
        handle.close()

    assert handle._loop._thread.is_alive() is False  # noqa: SLF001
    assert all(socket.closed for socket in created_sockets)
