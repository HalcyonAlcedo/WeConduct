from __future__ import annotations

import asyncio
import time

import pytest

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.long_connection import (
    SSEClientHandle,
    SSEConnection,
    WebSocketConnection,
    WebSocketConnectionError,
)


def test_sse_connection_feeds_bounded_queue_and_activation() -> None:
    async def scenario() -> None:
        connection = SSEConnection(
            max_queue_size=2,
            backpressure_policy="drop_oldest",
            connection_id="sse-1",
        )

        await connection.feed({"id": "event-1", "data": "one"})
        await connection.feed({"id": "event-2", "data": "two"})
        await connection.feed({"id": "event-3", "data": "three"})

        assert connection.queue_depth == 2
        assert connection.dropped_count == 1
        assert connection.queue_status["backpressure_policy"] == "drop_oldest"
        assert connection.queue_status["drop_events"] == [
            {
                "event_kind": "network.queue_message_dropped",
                "policy": "drop_oldest",
                "dropped_count": 1,
                "first_sequence_id": 1,
                "last_sequence_id": 1,
                "connection_id": "sse-1",
                "connection_epoch": 1,
            }
        ]

        activation = await connection.activation_queue.wait_next()
        assert activation["payload"]["event_kind"] == "sse.message"
        assert activation["payload"]["message"]["sequence_id"] == 1

        event = await connection.receive()
        assert event.event_id == "event-2"
        assert event.data == "two"

    asyncio.run(scenario())


def test_sse_connection_publishes_activation_to_session_sink() -> None:
    async def scenario() -> None:
        observed: list[dict[str, object]] = []
        connection = SSEConnection(
            connection_id="sse-sink",
            activation_sink=observed.append,
        )

        await connection.feed({"id": "event-1", "data": "one"})

        assert len(observed) == 1
        assert observed[0]["connection_id"] == "sse-sink"
        assert observed[0]["sequence_id"] == 1
        assert observed[0]["payload"]["event_kind"] == "sse.message"  # type: ignore[index]

    asyncio.run(scenario())


def test_websocket_connection_pump_feeds_queue_and_activation() -> None:
    async def scenario() -> None:
        class Socket:
            def __init__(self) -> None:
                self.values = iter(["first", "second"])
                self.closed = False

            async def recv(self) -> object:
                try:
                    return next(self.values)
                except StopIteration:
                    while not self.closed:
                        await asyncio.sleep(0.01)
                    raise RuntimeError("socket closed")

            async def close(self) -> None:
                self.closed = True

        connection = WebSocketConnection(
            Socket(),
            max_queue_size=2,
            backpressure_policy="fail_stream",
            connection_id="ws-1",
        )
        await connection.start_receiver()

        first = await connection.receive(timeout_seconds=1)
        second = await connection.receive(timeout_seconds=1)

        assert first == "first"
        assert second == "second"
        assert connection.queue_depth == 0
        assert connection.dropped_count == 0

        activation = await connection.activation_queue.wait_next(timeout_seconds=1)
        assert activation["payload"]["event_kind"] == "websocket.message"
        assert activation["payload"]["message"]["sequence_id"] == 1

        await connection.close()

    asyncio.run(scenario())


def test_websocket_connection_publishes_activation_to_session_sink() -> None:
    async def scenario() -> None:
        observed: list[dict[str, object]] = []

        class Socket:
            async def recv(self) -> object:
                return "frame"

            async def close(self) -> None:
                return None

        connection = WebSocketConnection(
            Socket(),
            connection_id="ws-sink",
            activation_sink=observed.append,
        )
        await connection.start_receiver()
        await asyncio.sleep(0)
        await connection.close()

        assert len(observed) >= 1
        assert observed[0]["connection_id"] == "ws-sink"
        assert observed[0]["payload"]["event_kind"] == "websocket.message"  # type: ignore[index]

    asyncio.run(scenario())


def test_websocket_receiver_error_closes_queues_and_wakes_blocked_receive() -> None:
    async def scenario() -> None:
        class Socket:
            async def recv(self) -> object:
                raise RuntimeError("fixture socket failed")

            async def close(self) -> None:
                return None

        connection = WebSocketConnection(Socket(), connection_id="ws-error")
        await connection.start_receiver()
        await connection.wait_closed()

        assert connection.receiver_error is not None
        with pytest.raises(WebSocketConnectionError, match="network.websocket_closed"):
            await connection.receive(timeout_seconds=0.1)

    asyncio.run(scenario())


def test_client_handles_expose_queue_state_without_breaking_pull_api() -> None:
    async def scenario() -> None:
        connection = SSEConnection(max_queue_size=1, connection_id="sse-2")
        await connection.feed({"id": "event-1", "data": "payload"})
        event = await connection.receive(timeout_seconds=1)
        assert event.data == "payload"
        assert connection.last_event_id == "event-1"

    asyncio.run(scenario())


def test_sse_connection_epoch_reports_reconnect_count() -> None:
    async def scenario() -> None:
        connection = SSEConnection(connection_id="sse-reconnect")
        assert connection.queue_status["connection_epoch"] == 1
        assert connection.queue_status["reconnect_count"] == 0

        await connection.advance_epoch()

        assert connection.queue_status["connection_epoch"] == 2
        assert connection.queue_status["reconnect_count"] == 1

    asyncio.run(scenario())


def test_sse_client_handle_reconnects_with_last_event_id() -> None:
    from contextlib import contextmanager
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Lock, Thread

    @contextmanager
    def server_context():
        state = {"count": 0, "last_event_ids": []}
        state_lock = Lock()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                with state_lock:
                    state["count"] += 1
                    count = state["count"]
                    state["last_event_ids"].append(self.headers.get("Last-Event-ID"))
                event_id = "event-one" if count == 1 else "event-two"
                payload = f"id: {event_id}\ndata: payload-{count}\n\n".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
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
            max_reconnect_attempts=1,
            reconnect_delay_seconds=0,
        )
        try:
            handle.start(timeout_seconds=2)
            assert handle.receive(timeout_seconds=2)["event_id"] == "event-one"
            assert handle.receive(timeout_seconds=2)["event_id"] == "event-two"
            assert state["last_event_ids"][:2] == [None, "event-one"]
            assert handle.queue_status["connection_epoch"] == 2
            assert handle.queue_status["reconnect_count"] == 1
            assert handle.queue_status["reconnect_reason"] == "network.sse_stream_closed"
        finally:
            handle.close()


def test_sse_client_preserves_url_query_when_params_are_empty() -> None:
    from contextlib import contextmanager
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Lock, Thread
    from urllib.parse import parse_qs, urlsplit

    @contextmanager
    def server_context():
        state = {"queries": []}
        state_lock = Lock()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                query = parse_qs(urlsplit(self.path).query)
                with state_lock:
                    state["queries"].append(query.get("count", [None])[0])
                count = int(query.get("count", ["3"])[0] or 3)
                payload = "".join(
                    f"id: event-{index}\ndata: payload-{index}\n\n"
                    for index in range(1, count + 1)
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
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
            url=f"{url}?count=1",
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        try:
            handle.start(timeout_seconds=2)
            assert state["queries"] == ["1"]
            assert handle.receive(timeout_seconds=2)["event_id"] == "event-1"
        finally:
            handle.close()


def test_sse_client_uses_server_retry_delay_seconds_without_double_conversion() -> None:
    handle = SSEClientHandle(
        url="http://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        reconnect_max_delay_seconds=30,
    )
    try:
        asyncio.run(handle.connection.feed({"retry": 31_000, "data": "payload"}))
        assert handle._next_reconnect_delay(1) == 30
    finally:
        handle.close()


def test_websocket_client_receive_waits_for_delayed_reconnect(monkeypatch) -> None:
    """重连窗口内的连续 receive 不应把临时断开误报为终态关闭。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)

        async def send(self, value: object) -> None:
            return

        async def recv(self) -> object:
            try:
                value = next(self.values)
            except StopIteration as exc:
                raise ConnectionError("socket dropped") from exc
            if isinstance(value, BaseException):
                raise value
            return value

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            return

    sockets = iter([Socket(["first", ConnectionError("dropped")]), Socket(["second"])])
    connect_count = 0

    async def connect(*args, **kwargs):
        nonlocal connect_count
        connect_count += 1
        if connect_count > 1:
            await asyncio.sleep(0.05)
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0,
    )
    try:
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2) == "first"
        assert handle.receive(timeout_seconds=2) == "second"
    finally:
        handle.close()


def test_websocket_receive_does_not_spin_on_closed_queue_during_reconnect(monkeypatch) -> None:
    """重连等待期间应挂起等待状态变化，而不是反复读取已关闭队列。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)
            self.closed = False

        async def send(self, value: object) -> None:
            return

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

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    sockets = iter(
        [
            Socket(["first", ConnectionError("dropped")]),
            Socket(["second"]),
        ]
    )

    async def connect(*args, **kwargs):
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.5,
    )
    try:
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2) == "first"
        connection = handle.connection
        assert connection is not None
        receive_calls = 0
        original_receive = connection.receive

        async def counted_receive(*, timeout_seconds=None):
            nonlocal receive_calls
            receive_calls += 1
            return await original_receive(timeout_seconds=timeout_seconds)

        connection.receive = counted_receive  # type: ignore[method-assign]
        with pytest.raises(TimeoutError, match="network.websocket_receive_timeout"):
            handle.receive(timeout_seconds=0.05)
        assert receive_calls <= 3
    finally:
        handle.close()


def test_websocket_client_handle_reconnects_and_preserves_activation_queue(monkeypatch) -> None:
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)
            self.closed = False

        async def send(self, value: object) -> None:
            return

        async def recv(self) -> object:
            try:
                value = next(self.values)
            except StopIteration as exc:
                raise ConnectionError("socket dropped") from exc
            if isinstance(value, BaseException):
                raise value
            return value

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
        reconnect_delay_seconds=0,
    )
    try:
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2) == "first"
        assert handle.receive(timeout_seconds=2) == "second"
        assert handle.queue_status["connection_epoch"] == 2
        assert handle.queue_status["reconnect_count"] == 1
        assert handle.queue_status["reconnect_reason"] == "network.websocket_reconnect_failed"
    finally:
        handle.close()


def test_websocket_client_handle_wait_next_activation_waits_through_reconnect(monkeypatch) -> None:
    """重连期间 activation 队列被关闭后，等待中的消费者应在恢复后继续取到新事件。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)
            self.closed = False

        async def send(self, value: object) -> None:
            return

        async def recv(self) -> object:
            try:
                value = next(self.values)
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
            Socket(['{"kind":"first"}', ConnectionError("dropped")]),
            Socket(['{"kind":"second"}']),
        ]
    )

    async def connect(*args, **kwargs):
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0.2,
    )
    try:
        handle.start(timeout_seconds=2)
        first = handle.wait_next_activation(timeout_seconds=2)
        assert first["payload"]["message"]["payload"] == '{"kind":"first"}'
        deadline = time.monotonic() + 1
        while handle.queue_status["connection_state"] != "reconnecting":
            if time.monotonic() >= deadline:
                raise AssertionError("connection never entered reconnect state")
            time.sleep(0.01)
        second = handle.wait_next_activation(timeout_seconds=2)
        assert second["payload"]["message"]["payload"] == '{"kind":"second"}'
    finally:
        handle.close()


def test_websocket_client_handle_invokes_reconnect_callback_after_socket_replacement(monkeypatch) -> None:
    """传输层替换 socket 后应给协议层机会重新完成握手。"""
    import weconduct.network_runtime.long_connection as long_connection_module

    class Socket:
        def __init__(self, values: list[object]) -> None:
            self.values = iter(values)
            self.closed = False

        async def send(self, value: object) -> None:
            return

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

        async def ping(self, value: bytes | None = None) -> None:
            return

        async def close(self) -> None:
            self.closed = True

    sockets = iter([Socket(["first", ConnectionError("dropped")]), Socket(["second"])])
    callback_epochs: list[int] = []

    async def connect(*args, **kwargs):
        return next(sockets)

    monkeypatch.setattr(long_connection_module.websockets, "connect", connect)
    handle = long_connection_module.WebSocketClientHandle(
        url="ws://example.test/events",
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        max_reconnect_attempts=1,
        reconnect_delay_seconds=0,
    )

    async def on_reconnect(connection) -> None:
        callback_epochs.append(connection.connection_epoch)

    try:
        handle.set_reconnect_callback(on_reconnect)
        handle.start(timeout_seconds=2)
        assert handle.receive(timeout_seconds=2) == "first"
        assert handle.receive(timeout_seconds=2) == "second"
        assert callback_epochs == [2]
    finally:
        handle.close()
