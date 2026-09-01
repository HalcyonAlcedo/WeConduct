from __future__ import annotations

import asyncio
from concurrent.futures import Future
import json

import pytest

from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from weconduct.network_runtime.resources import ResponseBodyRef
from weconduct.network_runtime.long_connection import WebSocketClientHandle
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_network_graphql_subscription_node_is_registered() -> None:
    registry = RuntimeExecutorRegistry()

    assert "network.graphql_subscription" in registry._executors  # type: ignore[attr-defined]


def test_network_graphql_subscription_waits_for_ack_and_answers_ping() -> None:
    class FakeWebSocketHandle:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.received: list[str] = []
            self.closed = False
            self._frames = iter(
                [
                    '{"type":"ping","payload":{"nonce":"n-1"}}',
                    '{"type":"connection_ack"}',
                ]
            )

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            frame = next(self._frames)
            self.received.append(frame)
            return frame

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.messages: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def record_connection_message(self, **kwargs: object) -> None:
            self.messages.append(dict(kwargs))

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-handshake",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-handshake",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        output = registry.execute("network.graphql_subscription", node, context)
    finally:
        context.close()

    assert output["status"] == "succeeded", output
    assert [json.loads(item)["type"] for item in service.handle.sent] == [
        "connection_init",
        "pong",
        "subscribe",
    ]
    assert json.loads(service.handle.sent[1])["payload"] == {"nonce": "n-1"}
    assert [item["event_kind"] for item in service.messages] == [
        "graphql.connection_init",
        "graphql.ping",
        "graphql.pong",
        "graphql.connection_ack",
        "graphql.subscribe",
    ]


def test_network_graphql_subscription_reconnect_resends_handshake_and_subscription() -> None:
    class FakeConnection:
        connection_epoch = 2

        def __init__(self) -> None:
            self.sent: list[str] = []
            self._received = iter(['{"type":"connection_ack"}'])

        async def send(self, value: object) -> None:
            self.sent.append(str(value))

        async def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

    class FakeWebSocketHandle:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self.reconnect_callback = None

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return '{"type":"connection_ack"}'

        def set_reconnect_callback(self, callback) -> None:
            self.reconnect_callback = callback

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.messages: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def record_connection_message(self, **kwargs: object) -> None:
            self.messages.append(dict(kwargs))

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-reconnect",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-reconnect",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        output = registry.execute("network.graphql_subscription", node, context)
        assert output["status"] == "succeeded", output
        assert callable(service.handle.reconnect_callback)
        connection = FakeConnection()
        asyncio.run(service.handle.reconnect_callback(connection))
    finally:
        context.close()

    assert [json.loads(item)["type"] for item in connection.sent] == [
        "connection_init",
        "subscribe",
    ]
    assert [item["event_kind"] for item in service.messages][-3:] == [
        "graphql.connection_init",
        "graphql.connection_ack",
        "graphql.subscribe",
    ]


def test_network_graphql_subscription_node_sends_frames_and_parses_next_messages() -> None:
    class FakeWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self._received = iter(
                [
                    '{"type":"connection_ack"}',
                    '{"id":"subscription-1","type":"next","payload":{"data":{"tick":1}}}',
                ]
            )

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.messages: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def record_connection_message(self, **kwargs: object) -> None:
            self.messages.append(dict(kwargs))

        def release_connection(self, session_id: str, handle: object) -> None:
            del session_id, handle

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    node = {
        "node_id": "graphql-subscription-1",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-1",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )

    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        received = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-subscription-receive",
                "node_config": {
                    "action": "receive",
                    "connection_id": "subscription-1",
                },
            },
            context,
        )
    finally:
        context.close()

    assert connected["status"] == "succeeded", connected
    assert received["data"] == {"tick": 1}
    assert len(service.handle.sent) == 2
    assert '"type": "connection_init"' in service.handle.sent[0]
    assert '"type": "subscribe"' in service.handle.sent[1]
    assert [item["event_kind"] for item in service.messages] == [
        "graphql.connection_init",
        "graphql.connection_ack",
        "graphql.subscribe",
        "graphql.receive",
    ]


def test_network_graphql_subscription_node_consumes_activation_queue() -> None:
    class FakeWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self._received = iter(['{"type":"connection_ack"}'])

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def wait_next_activation(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
            del timeout_seconds
            raw_frame = '{"id":"subscription-activation","type":"next","payload":{"data":{"tick":2}}}'
            return {
                "payload": {
                    "event_kind": "websocket.message",
                    "message": {
                        "sequence_id": 4,
                        "connection_epoch": 2,
                        "payload": raw_frame,
                    },
                },
            }

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.messages: list[dict[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def record_connection_message(self, **kwargs: object) -> None:
            self.messages.append(dict(kwargs))

        def wait_connection_activation(self, **kwargs: object) -> dict[str, object]:
            return self.handle.wait_next_activation(timeout_seconds=kwargs.get("timeout_seconds"))

        def release_connection(self, session_id: str, handle: object) -> None:
            del session_id, handle

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-subscription-activation",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-activation",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        activated = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-subscription-activation-next",
                "node_config": {
                    "action": "next_event",
                    "connection_id": "subscription-activation",
                },
            },
            context,
        )
    finally:
        context.close()

    assert connected["status"] == "succeeded", connected
    assert activated["status"] == "succeeded", activated
    assert activated["event_type"] == "next"
    assert activated["data"] == {"tick": 2}
    assert activated["sequence_id"] == 4
    assert activated["connection_epoch"] == 2
    assert service.messages[-1]["event_kind"] == "graphql.next_event"


def test_network_graphql_subscription_next_event_skips_control_frames() -> None:
    class FakeWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self._received = iter(['{"type":"connection_ack"}'])
            self._activations = iter(
                [
                    {
                        "payload": {
                            "event_kind": "websocket.message",
                            "message": {
                                "sequence_id": 1,
                                "connection_epoch": 1,
                                "payload": '{"type":"connection_ack"}',
                            },
                        }
                    },
                    {
                        "payload": {
                            "event_kind": "websocket.message",
                            "message": {
                                "sequence_id": 2,
                                "connection_epoch": 1,
                                "payload": (
                                    '{"id":"subscription-control-filter",'
                                    '"type":"next","payload":{"data":{"tick":3}}}'
                                ),
                            },
                        }
                    },
                ]
            )

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def wait_next_activation(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
            del timeout_seconds
            return next(self._activations)

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def wait_connection_activation(self, **kwargs: object) -> dict[str, object]:
            return self.handle.wait_next_activation(timeout_seconds=kwargs.get("timeout_seconds"))

        def release_connection(self, session_id: str, handle: object) -> None:
            del session_id, handle

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-subscription-control-filter",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-control-filter",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        next_event = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-subscription-control-filter-next",
                "node_config": {
                    "action": "next_event",
                    "connection_id": "subscription-control-filter",
                },
            },
            context,
        )
    finally:
        context.close()

    assert connected["status"] == "succeeded", connected
    assert next_event["status"] == "succeeded", next_event
    assert next_event["event_type"] == "next"
    assert next_event["sequence_id"] == 2
    assert next_event["data"] == {"tick": 3}


@pytest.mark.parametrize(
    ("action", "raw_frame", "expected_event_type", "expected_output"),
    [
        (
            "next_event",
            '{"type":"complete"}',
            "complete",
            {"completed": True},
        ),
        (
            "receive",
            '{"type":"complete"}',
            "complete",
            {"completed": True},
        ),
        (
            "next_event",
            '{"type":"stop"}',
            "stop",
            {"completed": True},
        ),
        (
            "receive",
            '{"type":"stop"}',
            "stop",
            {"completed": True},
        ),
        (
            "next_event",
            '{"type":"error","payload":[{"message":"boom"}]}',
            "error",
            {"errors": [{"message": "boom"}]},
        ),
        (
            "receive",
            '{"type":"error","payload":[{"message":"boom"}]}',
            "error",
            {"errors": [{"message": "boom"}]},
        ),
    ],
)
def test_network_graphql_subscription_terminal_frames_release_connection(
    action: str,
    raw_frame: str,
    expected_event_type: str,
    expected_output: dict[str, object],
) -> None:
    class FakeWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self._received = iter(
                ['{"type":"connection_ack"}'] + ([raw_frame] if action == "receive" else [])
            )
            self._activations = iter(
                [
                    {
                        "payload": {
                            "event_kind": "websocket.message",
                            "message": {
                                "sequence_id": 2,
                                "connection_epoch": 1,
                                "payload": raw_frame,
                            },
                        }
                    }
                ]
            )

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def wait_next_activation(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
            del timeout_seconds
            return next(self._activations)

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.released: list[tuple[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def wait_connection_activation(self, **kwargs: object) -> dict[str, object]:
            return self.handle.wait_next_activation(timeout_seconds=kwargs.get("timeout_seconds"))

        def release_connection(self, session_id: str, handle: object) -> None:
            self.released.append((session_id, handle))

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": f"graphql-subscription-terminal-{action}",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": f"subscription-terminal-{action}",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        terminal = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": f"graphql-subscription-terminal-{action}-{action}",
                "node_config": {
                    "action": action,
                    "connection_id": f"subscription-terminal-{action}",
                },
            },
            context,
        )
        connections = context.flow_runtime.get("network_connections", {})
        assert connected["status"] == "succeeded", connected
        assert terminal["status"] == "succeeded", terminal
        assert terminal["event_type"] == expected_event_type
        for key, value in expected_output.items():
            assert terminal[key] == value
        assert connections.get(("graphql", f"subscription-terminal-{action}")) is None
        assert service.handle.closed is True
        assert service.released == [(context.execution_session_context.session_id, service.handle)]
    finally:
        context.close()


def test_network_graphql_subscription_unsubscribe_sends_complete_and_releases_connection() -> None:
    class FakeWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed = False
            self._received = iter(['{"type":"connection_ack"}'])

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def close(self) -> None:
            self.closed = True

    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.handle = FakeWebSocketHandle()
            self.released: list[tuple[str, object]] = []

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def release_connection(self, session_id: str, handle: object) -> None:
            self.released.append((session_id, handle))

    service = StubNetworkRuntimeService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-subscription-unsubscribe",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-unsubscribe",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        closed = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-subscription-unsubscribe-action",
                "node_config": {
                    "action": "unsubscribe",
                    "connection_id": "subscription-unsubscribe",
                },
            },
            context,
        )
    finally:
        context.close()

    assert connected["status"] == "succeeded", connected
    assert closed["status"] == "succeeded", closed
    assert closed["action"] == "unsubscribe"
    assert json.loads(service.handle.sent[-1]) == {
        "id": "subscription-unsubscribe",
        "type": "complete",
    }
    assert service.handle.closed is True
    assert service.released == [(context.execution_session_context.session_id, service.handle)] if context.execution_session_context else service.released


def test_network_graphql_subscription_cleanup_removes_connection_when_release_or_close_fails() -> None:
    class FailingCloseWebSocketHandle(WebSocketClientHandle):
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.close_calls = 0
            self._received = iter(['{"type":"connection_ack"}'])

        def send(self, value: object) -> None:
            self.sent.append(str(value))

        def receive(self, *, timeout_seconds: float | None = None) -> object:
            del timeout_seconds
            return next(self._received)

        def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("close failed")

    class FailingCleanupService:
        def __init__(self) -> None:
            self.handle = FailingCloseWebSocketHandle()
            self.release_calls = 0

        def connect_websocket(self, **kwargs: object):
            return self.handle, {"status": "connected", "url": kwargs["url"]}

        def release_connection(self, session_id: str, handle: object) -> None:
            del session_id, handle
            self.release_calls += 1
            raise RuntimeError("release failed")

    service = FailingCleanupService()
    context = RuntimeContext()
    registry = RuntimeExecutorRegistry(
        runtime_settings={"allow_local_network_access": True},
        network_runtime_service=service,
    )
    node = {
        "node_id": "graphql-subscription-cleanup-failure",
        "node_kind": "network.graphql_subscription",
        "node_config": {
            "action": "connect",
            "connection_id": "subscription-cleanup-failure",
            "endpoint": "http://127.0.0.1:12345/graphql",
            "query": "subscription Tick { tick }",
        },
    }
    try:
        connected = registry.execute("network.graphql_subscription", node, context)
        terminal = registry.execute(
            "network.graphql_subscription",
            {
                **node,
                "node_id": "graphql-subscription-cleanup-failure-action",
                "node_config": {
                    "action": "unsubscribe",
                    "connection_id": "subscription-cleanup-failure",
                },
            },
            context,
        )
        connections = context.flow_runtime.get("network_connections", {})
        assert connected["status"] == "succeeded", connected
        assert terminal["status"] == "succeeded", terminal
        assert connections.get(("graphql", "subscription-cleanup-failure")) is None
        assert service.release_calls == 1
        assert service.handle.close_calls == 1
    finally:
        context.close()


def test_network_graphql_request_returns_data_errors_and_extensions() -> None:
    class StubNetworkRuntimeService:
        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            future: Future[NetworkResult] = Future()
            payload = json.dumps(
                {"data": {"health": True}, "errors": [{"message": "partial"}], "extensions": {"trace": "x"}}
            ).encode("utf-8")
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    node = {
        "node_id": "graphql-1",
        "node_kind": "network.graphql_request",
        "node_config": {
            "endpoint": "https://example.test/graphql",
            "query": "query Health { health }",
            "variables": {},
        },
    }

    output = RuntimeExecutorRegistry(network_runtime_service=StubNetworkRuntimeService()).execute(
        "network.graphql_request", node, RuntimeContext()
    )

    assert output["status"] == "succeeded"
    assert output["data"] == {"health": True}
    assert output["errors"] == [{"message": "partial"}]
    assert output["extensions"] == {"trace": "x"}


def test_network_graphql_request_forwards_request_extensions() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            del snapshot
            self.operation = operation
            payload = b'{"data":{"health":true}}'
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(network_runtime_service=service).execute(
        "network.graphql_request",
        {
            "node_id": "graphql-extensions",
            "node_kind": "network.graphql_request",
            "node_config": {
                "endpoint": "https://example.test/graphql",
                "query": "query Health { health }",
                "extensions": {"persistedQuery": {"version": 1}},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.operation is not None
    assert json.loads(service.operation.content or b"{}") ["extensions"] == {
        "persistedQuery": {"version": 1}
    }


def test_network_graphql_request_does_not_use_removed_subscription_not_supported_path() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "subscription-node",
            "node_kind": "network.graphql_request",
            "node_config": {
                "endpoint": "https://example.test/graphql",
                "query": "subscription Watch { updates { id } }",
                "operation_name": "Watch",
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.graphql_subscription_requires_websocket"
    assert "0.9.0" not in output.get("message", "")


def test_network_graphql_request_resolves_relative_endpoint_from_platform_default() -> None:
    class StubNetworkRuntimeService:
        def __init__(self) -> None:
            self.operation: NetworkOperation | None = None

        def submit(
            self,
            operation: NetworkOperation,
            snapshot: NetworkContextSnapshot,
        ) -> Future[NetworkResult]:
            del snapshot
            self.operation = operation
            payload = b'{"data":{"health":true}}'
            future: Future[NetworkResult] = Future()
            future.set_result(
                NetworkResult(
                    status="succeeded",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    status_code=200,
                    body_ref=ResponseBodyRef(
                        session_id=operation.session_id,
                        storage_kind="memory",
                        size_bytes=len(payload),
                        content_type="application/json",
                        _payload=payload,
                    ),
                )
            )
            return future

    service = StubNetworkRuntimeService()
    output = RuntimeExecutorRegistry(
        runtime_settings={"network_platform_defaults": {"base_url": "https://example.test/api/"}},
        network_runtime_service=service,
    ).execute(
        "network.graphql_request",
        {
            "node_id": "graphql-relative-endpoint",
            "node_kind": "network.graphql_request",
            "node_config": {"endpoint": "health", "query": "query Health { health }"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert service.operation is not None
    assert service.operation.url == "https://example.test/api/health"


def test_network_graphql_subscription_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "graphql-subscription-invalid",
            "node_kind": "network.graphql_request",
            "node_config": {"action": "connect", "connection_id": "subscription-1"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] != "network.graphql_subscription_not_supported"
    assert "0.9.0" not in output.get("message", "")
    assert output["network_error"]["request_id"] == output["request_id"]
    assert output["network_error"]["node_id"] == "graphql-subscription-invalid"
    assert output["network_error"]["details"] == {"action": "connect"}


def test_network_graphql_request_validation_failure_exposes_structured_network_error() -> None:
    output = RuntimeExecutorRegistry().execute(
        "network.graphql_request",
        {
            "node_id": "graphql-request-invalid",
            "node_kind": "network.graphql_request",
            "node_config": {"query": "query Health { health }"},
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "network.graphql_endpoint_required"
    assert output["network_error"]["request_id"] == output["request_id"]
    assert output["network_error"]["node_id"] == "graphql-request-invalid"
    assert output["network_error"]["network_context_id"] is None
