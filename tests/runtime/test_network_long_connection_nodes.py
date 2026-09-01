from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from threading import Event, Thread

import asyncio
import json
import websockets

from weconduct.network_runtime.models import NetworkContextSnapshot
from weconduct.network_runtime.service import NetworkRuntimeService
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


class _StubSseHandle:
    def close(self) -> None:
        return


class _StubNetworkRuntimeService:
    def __init__(self) -> None:
        self.snapshots = []
        self.connect_calls = []

    def connect_sse(self, **kwargs):
        self.snapshots.append(kwargs["snapshot"])
        self.connect_calls.append(kwargs)
        return _StubSseHandle(), {"status_code": 200, "headers": {}, "url": kwargs["url"]}


def test_network_message_trace_is_optional_for_injected_service() -> None:
    class ServiceWithoutTrace:
        pass

    registry = RuntimeExecutorRegistry()

    # 轻量网络服务桩未实现调试 Trace 扩展时，兼容辅助方法不应抛出异常。
    registry._record_network_connection_message(  # type: ignore[attr-defined]
        ServiceWithoutTrace(),
        session_id="debug-session",
        handle=object(),
        connection_id="connection",
        event_kind="sse.message",
        payload={"data": "hello"},
    )


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
        registry = RuntimeExecutorRegistry(runtime_settings={"allow_local_network_access": True})
        try:
            connected = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-connect",
                    "node_kind": "network.sse_connect",
                "node_config": {
                    "url": url,
                    "connection_id": "stream",
                    "timeout_seconds": None,
                },
                },
                context,
            )
            assert connected["status"] == "succeeded"
            assert connected["connection_id"] == "stream"
            assert isinstance(connected["queue"]["depth"], int)
            assert connected["queue"]["dropped_count"] == 0

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
            runtime_service = context.flow_runtime["network_runtime_service"]
            assert runtime_service._long_connections == {}
        finally:
            context.close()


def test_network_sse_connect_node_exposes_next_event_activation() -> None:
    with _sse_server() as url:
        context = RuntimeContext()
        registry = RuntimeExecutorRegistry(runtime_settings={"allow_local_network_access": True})
        try:
            connected = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-connect-activation",
                    "node_kind": "network.sse_connect",
                    "node_config": {
                        "url": url,
                        "connection_id": "stream-activation",
                        "timeout_seconds": None,
                    },
                },
                context,
            )
            assert connected["status"] == "succeeded"

            activated = registry.execute(
                "network.sse_connect",
                {
                    "node_id": "sse-next-event",
                    "node_kind": "network.sse_connect",
                    "node_config": {
                        "action": "next_event",
                        "connection_id": "stream-activation",
                        "timeout_seconds": 2,
                    },
                },
                context,
            )
            assert activated["status"] == "succeeded"
            assert activated["event_kind"] == "sse.message"
            assert activated["sequence_id"] == 1
            assert activated["event"]["event_id"] == "node-event"
        finally:
            context.close()


def test_network_sse_connect_node_uses_network_runtime_service_snapshot() -> None:
    service = _StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"network_platform_defaults": {"timeout_seconds": 12}},
        network_runtime_service=service,
    ).execute(
        "network.sse_connect",
        {
            "node_id": "sse-service-connect",
            "node_kind": "network.sse_connect",
            "node_config": {
                "url": "https://example.test/events",
                "connection_id": "stream",
                "timeout_seconds": None,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert len(service.snapshots) == 1
    assert service.snapshots[0].context_id is not None
    assert service.snapshots[0].timeout_seconds == 12
    assert service.connect_calls[0]["timeout_seconds"] == 12


def test_network_sse_connect_node_forwards_queue_backpressure_configuration() -> None:
    service = _StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"network_platform_defaults": {"timeout_seconds": 12}},
        network_runtime_service=service,
    ).execute(
        "network.sse_connect",
        {
            "node_id": "sse-queue-config",
            "node_kind": "network.sse_connect",
            "node_config": {
                "url": "https://example.test/events",
                "connection_id": "stream",
                "max_queue_size": 7,
                "backpressure_policy": "drop_oldest",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.connect_calls[0]["max_queue_size"] == 7
    assert service.connect_calls[0]["backpressure_policy"] == "drop_oldest"


def test_network_runtime_service_forwards_sse_reconnect_configuration(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class RecordingHandle:
        def __init__(self, **kwargs: object) -> None:
            recorded.update(kwargs)

        def start(self, *, timeout_seconds: float) -> dict[str, object]:
            return {"status_code": 200, "headers": {}, "url": recorded["url"]}

        def close(self) -> None:
            return

    monkeypatch.setattr("weconduct.network_runtime.service.SSEClientHandle", RecordingHandle)

    service = NetworkRuntimeService(response_root_directory=Path.cwd() / "tmp-test-response")
    service.connect_sse(
        session_id="session",
        snapshot=NetworkContextSnapshot(context_id="ctx"),
        url="https://example.test/events",
        connection_id="stream",
        max_reconnect_attempts=3,
        reconnect_delay_seconds=1.25,
        reconnect_max_delay_seconds=9.5,
    )

    assert recorded["max_reconnect_attempts"] == 3
    assert recorded["reconnect_delay_seconds"] == 1.25
    assert recorded["reconnect_max_delay_seconds"] == 9.5


def test_network_sse_connect_node_forwards_reconnect_configuration() -> None:
    service = _StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"network_platform_defaults": {"timeout_seconds": 12}},
        network_runtime_service=service,
    ).execute(
        "network.sse_connect",
        {
            "node_id": "sse-reconnect-config",
            "node_kind": "network.sse_connect",
            "node_config": {
                "url": "https://example.test/events",
                "connection_id": "stream",
                "max_reconnect_attempts": 4,
                "reconnect_delay_seconds": 1.5,
                "reconnect_max_delay_seconds": 12.0,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.connect_calls[0]["max_reconnect_attempts"] == 4
    assert service.connect_calls[0]["reconnect_delay_seconds"] == 1.5
    assert service.connect_calls[0]["reconnect_max_delay_seconds"] == 12.0


def test_network_websocket_connect_node_forwards_queue_backpressure_configuration() -> None:
    class RecordingService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object) -> tuple[object, dict[str, object]]:
            self.calls.append(kwargs)
            return _StubSseHandle(), {"status": "connected", "url": kwargs["url"]}

    service = RecordingService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    ).execute(
        "network.websocket_connect",
        {
            "node_id": "websocket-queue-config",
            "node_kind": "network.websocket_connect",
            "node_config": {
                    # 该用例验证节点到注入服务的参数转发；使用已明确允许的环回地址，
                    # 避免把真实 DNS 解析引入测试，也不绕过生产网络访问策略。
                    "url": "wss://127.0.0.1/events",
                "connection_id": "socket",
                "max_queue_size": 9,
                "backpressure_policy": "drop_newest",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.calls[0]["max_queue_size"] == 9
    assert service.calls[0]["backpressure_policy"] == "drop_newest"


def test_network_runtime_service_forwards_websocket_reconnect_configuration(
    monkeypatch,
) -> None:
    recorded: dict[str, object] = {}

    class RecordingHandle:
        def __init__(self, **kwargs: object) -> None:
            recorded.update(kwargs)

        def start(self, *, timeout_seconds: float) -> dict[str, object]:
            return {"status": "connected", "url": recorded["url"]}

        def close(self) -> None:
            return

    monkeypatch.setattr("weconduct.network_runtime.service.WebSocketClientHandle", RecordingHandle)

    service = NetworkRuntimeService(response_root_directory=Path.cwd() / "tmp-test-response")
    service.connect_websocket(
        session_id="session",
        snapshot=NetworkContextSnapshot(context_id="ctx"),
        url="wss://example.test/events",
        connection_id="socket",
        max_reconnect_attempts=2,
        reconnect_delay_seconds=0.75,
        reconnect_max_delay_seconds=8.0,
    )

    assert recorded["max_reconnect_attempts"] == 2
    assert recorded["reconnect_delay_seconds"] == 0.75
    assert recorded["reconnect_max_delay_seconds"] == 8.0


def test_network_websocket_connect_node_forwards_reconnect_configuration() -> None:
    class RecordingService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object) -> tuple[object, dict[str, object]]:
            self.calls.append(kwargs)
            return _StubSseHandle(), {"status": "connected", "url": kwargs["url"]}

    service = RecordingService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    ).execute(
        "network.websocket_connect",
        {
            "node_id": "websocket-reconnect-config",
            "node_kind": "network.websocket_connect",
            "node_config": {
                "url": "wss://127.0.0.1/events",
                "connection_id": "socket",
                "max_reconnect_attempts": 2,
                "reconnect_delay_seconds": 0.5,
                "reconnect_max_delay_seconds": 6.0,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.calls[0]["max_reconnect_attempts"] == 2
    assert service.calls[0]["reconnect_delay_seconds"] == 0.5
    assert service.calls[0]["reconnect_max_delay_seconds"] == 6.0


def test_network_sse_connect_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.sse_connect",
        {
            "node_id": "sse-invalid-url",
            "node_kind": "network.sse_connect",
            "node_config": {"connection_id": "stream"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.sse_url_required"
    assert output["request_id"]
    assert output["network_error"] == {
        "error_code": "network.sse_url_required",
        "message": "SSE url is required",
        "details": {"action": "connect"},
        "request_id": output["request_id"],
        "node_id": "sse-invalid-url",
        "network_context_id": None,
        "retry_attempt": 1,
    }


def test_network_sse_connect_rejects_invalid_reconnect_attempts() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.sse_connect",
        {
            "node_id": "sse-invalid-reconnect-attempts",
            "node_kind": "network.sse_connect",
            "node_config": {
                "url": "https://example.test/events",
                "connection_id": "stream",
                "max_reconnect_attempts": -1,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.sse_connect_failed"
    assert output["message"] == "network.sse_reconnect_attempts_invalid"


def test_network_websocket_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.websocket_connect",
        {
            "node_id": "websocket-invalid-url",
            "node_kind": "network.websocket_connect",
            "node_config": {"connection_id": "socket"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.websocket_url_required"
    assert output["network_error"]["request_id"] == output["request_id"]
    assert output["network_error"]["node_id"] == "websocket-invalid-url"
    assert output["network_error"]["details"] == {"action": "connect"}


def test_network_websocket_connect_rejects_invalid_reconnect_delay_range() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.websocket_connect",
        {
            "node_id": "websocket-invalid-reconnect-delay",
            "node_kind": "network.websocket_connect",
            "node_config": {
                "url": "wss://example.test/events",
                "connection_id": "socket",
                "reconnect_delay_seconds": 3,
                "reconnect_max_delay_seconds": 2,
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.websocket_connect_failed"
    assert output["message"] == "network.websocket_reconnect_max_delay_invalid"


def test_websocket_node_checks_access_policy_before_calling_network_service() -> None:
    class RecordingService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object) -> tuple[object, dict[str, object]]:
            self.calls.append(kwargs)
            return object(), {"status": "connected"}

    service = RecordingService()
    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(  # type: ignore[arg-type]
        "network.websocket_connect",
        {
            "node_id": "ws-loopback-denied",
            "node_kind": "network.websocket_connect",
            "node_config": {
                "url": "ws://127.0.0.1:8080",
                "connection_id": "socket",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.websocket_connect_failed"
    assert service.calls == []


def test_network_websocket_connect_node_supports_send_receive_ping_and_close() -> None:
    server = _WebSocketServer()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(runtime_settings={"allow_local_network_access": True})
    try:
        url = f"ws://127.0.0.1:{server.port}"
        connected = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-connect",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "url": url,
                    "connection_id": "socket",
                    "timeout_seconds": None,
                },
            },
            context,
        )
        assert connected["status"] == "succeeded"
        assert connected["queue"]["depth"] == 0
        assert connected["queue"]["dropped_count"] == 0

        sent = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-send",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "action": "send",
                    "connection_id": "socket",
                    "message": "hello",
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
        activated = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-next-event",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "action": "next_event",
                    "connection_id": "socket",
                    "timeout_seconds": 2,
                },
            },
            context,
        )
        assert activated["status"] == "succeeded"
        assert activated["event_kind"] == "websocket.message"
        assert activated["sequence_id"] == 1
        assert activated["message"] == "ack:hello"
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
        runtime_service = context.flow_runtime["network_runtime_service"]
        assert runtime_service._long_connections == {}
    finally:
        context.close()
        server.close()


def test_network_websocket_connect_node_serializes_structured_messages() -> None:
    server = _WebSocketServer()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(runtime_settings={"allow_local_network_access": True})
    message = {"type": "ping", "request_id": "structured-1", "values": [1, True]}
    try:
        url = f"ws://127.0.0.1:{server.port}"
        connected = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-structured-connect",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "url": url,
                    "connection_id": "structured-socket",
                    "timeout_seconds": None,
                },
            },
            context,
        )
        assert connected["status"] == "succeeded"

        sent = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-structured-send",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "action": "send",
                    "connection_id": "structured-socket",
                    "message": message,
                },
            },
            context,
        )
        assert sent["status"] == "succeeded", sent

        received = registry.execute(
            "network.websocket_connect",
            {
                "node_id": "ws-structured-receive",
                "node_kind": "network.websocket_connect",
                "node_config": {
                    "action": "receive",
                    "connection_id": "structured-socket",
                },
            },
            context,
        )
        assert json.loads(str(received["message"])[len("ack:") :]) == message
    finally:
        context.close()
        server.close()
