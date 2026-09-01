from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from weconduct.application.sensitive_values.service import SensitiveValueService
import weconduct.network_runtime.service as network_service_module
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.service import NetworkRuntimeService
from weconduct.network_runtime.trace import NetworkTraceRecorder, TRACE_MESSAGE_BODY_THRESHOLD_BYTES


def test_network_runtime_service_records_completed_response_body(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                201,
                request=request,
                headers={"content-type": "application/json"},
                content=b'{"created":true}',
            )
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-session-1",
                method="POST",
                url="https://example.test/items",
                content='{"name":"item"}',
                node_id="node-1",
            ),
            NetworkContextSnapshot(context_id="context-1"),
        ).result(timeout=2)
    finally:
        service.close()

    assert result.status == "succeeded"
    traces = recorder.list_traces(debug_session_id="debug-session-1")
    assert len(traces) == 1
    assert traces[0]["status"] == "succeeded"
    assert traces[0]["protocol"] == "http"
    assert traces[0]["request_body"]["value"] == '{"name":"item"}'
    assert traces[0]["response_body"]["value"] == '{"created":true}'
    assert traces[0]["response_status"] == 201


def test_network_runtime_service_keeps_large_request_body_as_resource_reference(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    payload = b"request-body-" + b"x" * TRACE_MESSAGE_BODY_THRESHOLD_BYTES
    observed: dict[str, bytes] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["body"] = await request.aread()
        return httpx.Response(204, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-large-request",
                method="POST",
                url="https://example.test/items",
                content=payload,
                node_id="node-large-request",
            ),
            NetworkContextSnapshot(context_id="context-large-request"),
        ).result(timeout=2)
        trace_id = recorder.list_traces(debug_session_id="debug-large-request")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
        descriptor = detail["operation"]["request_body"]
        assert service.read_debug_body("debug-large-request", descriptor) == payload
    finally:
        service.close()

    assert result.status == "succeeded"
    assert observed["body"] == payload
    assert descriptor["resource_id"]
    assert descriptor["size_bytes"] == len(payload)
    assert "value" not in descriptor


def test_network_runtime_service_reads_registered_debug_body_descriptor(tmp_path) -> None:
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=b"debug-body")
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-body-session",
                method="GET",
                url="https://example.test/body",
            ),
            NetworkContextSnapshot(context_id="context-debug-body"),
        ).result(timeout=2)
        assert result.body_ref is not None
        descriptor = result.body_ref.to_debug_descriptor()

        assert service.read_debug_body("debug-body-session", descriptor) == b"debug-body"

        forged = {**descriptor, "resource_id": "body-not-registered"}
        with pytest.raises(RuntimeError, match="network.response_body_unavailable"):
            service.read_debug_body("debug-body-session", forged)
    finally:
        service.close()


def test_httpx_adapter_concurrent_trace_body_store_creation_does_not_leak_directories(
    tmp_path,
    monkeypatch,
) -> None:
    """同一会话并发捕获大消息时只能创建一个正文 store。"""
    import weconduct.network_runtime.http_adapter as http_adapter_module

    real_store = http_adapter_module.ResponseBodyStore
    construction_barrier = Barrier(2)

    def synchronized_store(*args, **kwargs):
        try:
            construction_barrier.wait(timeout=0.5)
        except Exception:
            # 修复后的串行创建只会到达一个构造器调用；超时后继续创建即可。
            pass
        return real_store(*args, **kwargs)

    monkeypatch.setattr(http_adapter_module, "ResponseBodyStore", synchronized_store)
    adapter = http_adapter_module.HttpxAdapter(
        transport=httpx.MockTransport(lambda request: httpx.Response(204, request=request)),
        response_root_directory=tmp_path,
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    adapter.capture_trace_message_body,
                    "trace-store-race",
                    "x" * (300 * 1024),
                )
                for _ in range(2)
            ]
            references = [future.result(timeout=3) for future in futures]

        assert all(reference is not None for reference in references)
        assert len(adapter._stores) == 1
        assert len(list(tmp_path.iterdir())) == 1
    finally:
        adapter.close()

    assert list(tmp_path.iterdir()) == []


def test_network_runtime_service_assigns_debug_event_index_to_http_trace(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=b"ok")
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
        debug_event_index_supplier=lambda: 41,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-index-http",
                method="GET",
                url="https://example.test/items",
                node_id="node-index-http",
            ),
            NetworkContextSnapshot(context_id="context-index-http"),
        ).result(timeout=2)
        trace = recorder.get_trace(
            recorder.list_traces(debug_session_id="debug-index-http")[0]["trace_id"]
        )
    finally:
        service.close()

    assert result.status == "succeeded"
    assert trace["debug_event_index"] == 41
    assert trace["operation"]["debug_event_index"] == 41


def test_network_runtime_service_debug_trace_resolves_sensitive_headers(tmp_path) -> None:
    sensitive_values = SensitiveValueService()
    authorization = sensitive_values.create(
        "Bearer trace-secret",
        scope_id="debug-sensitive-trace",
        source="runtime_input",
    )
    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=b"ok")
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=sensitive_values,
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-sensitive-trace",
                method="GET",
                url="https://example.test/items",
                headers={"Authorization": authorization},
            ),
            NetworkContextSnapshot(context_id="context-sensitive-trace"),
        ).result(timeout=2)
        trace = recorder.get_trace(
            recorder.list_traces(debug_session_id="debug-sensitive-trace")[0]["trace_id"]
        )
    finally:
        service.close()

    assert result.status == "succeeded"
    assert trace["operation"]["request_headers"]["Authorization"] == "Bearer trace-secret"


def test_network_runtime_service_debug_trace_resolves_long_connection_sensitive_fields(tmp_path) -> None:
    sensitive_values = SensitiveValueService()
    scope_id = "debug-long-sensitive-trace"
    header_ref = sensitive_values.create(
        "Bearer long-connection-secret",
        scope_id=scope_id,
        source="runtime_input",
    )
    query_ref = sensitive_values.create(
        "query-secret",
        scope_id=scope_id,
        source="runtime_input",
    )
    proxy_user_ref = sensitive_values.create(
        "proxy-user",
        scope_id=scope_id,
        source="runtime_input",
    )
    tls_label_ref = sensitive_values.create(
        "tls-private-label",
        scope_id=scope_id,
        source="runtime_input",
    )
    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        sensitive_values=sensitive_values,
        trace_recorder=recorder,
    )
    try:
        trace_id = service._start_connection_trace(  # noqa: SLF001
            operation=NetworkOperation(
                operation_id="network.sse_connect",
                session_id=scope_id,
                method="GET",
                url="https://example.test/events",
                node_id="node-long-sensitive-trace",
            ),
            snapshot=NetworkContextSnapshot(
                context_id="context-long-sensitive-trace",
                proxy={
                    "mode": "manual",
                    "url": "http://proxy.example.test:8080",
                    "username": proxy_user_ref,
                },
                tls={"verify": "system", "debug_label": tls_label_ref},
            ),
            protocol="sse",
            connection_id="stream-long-sensitive-trace",
            request_headers={"Authorization": header_ref},
            request_query={"token": query_ref},
        )
        assert trace_id is not None
        trace = recorder.get_trace(trace_id)
    finally:
        service.close()

    operation = trace["operation"]
    assert operation["request_headers"]["Authorization"] == "Bearer long-connection-secret"
    assert operation["request_query"]["token"] == "query-secret"
    assert operation["proxy"]["username"] == "proxy-user"
    assert operation["tls"]["debug_label"] == "tls-private-label"


def test_network_runtime_service_records_failed_request(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ConnectError("connection failed", request=request))
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-session-2",
                method="GET",
                url="https://example.test/items",
                node_id="node-2",
            ),
            NetworkContextSnapshot(context_id="context-2"),
        ).result(timeout=2)
    finally:
        service.close()

    assert result.status == "failed"
    traces = recorder.list_traces(debug_session_id="debug-session-2")
    assert len(traces) == 1
    assert traces[0]["status"] == "failed"
    assert traces[0]["error_code"] == "network.connection_failed"


def test_network_runtime_service_trace_keeps_transport_metadata_and_final_retry_attempt(
    tmp_path,
) -> None:
    recorder = NetworkTraceRecorder()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request, content=b"ok")

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.http_request",
                session_id="debug-transport-metadata",
                method="GET",
                url="https://example.test/items",
                node_id="node-http",
            ),
            NetworkContextSnapshot(
                context_id="context-transport-metadata",
                proxy={"mode": "direct"},
                tls={"verify": "system", "certificate_pins": []},
                retry_policy={
                    "max_attempts": 2,
                    "retry_status_codes": [503],
                    "initial_delay_seconds": 0,
                    "jitter_ratio": 0,
                },
            ),
        ).result(timeout=2)
        trace_id = recorder.list_traces(debug_session_id="debug-transport-metadata")[0]["trace_id"]
        trace = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert result.status == "succeeded"
    assert result.retry_attempt == 2
    assert trace["operation"]["proxy"] == {"mode": "direct"}
    assert trace["operation"]["tls"] == {
        "verify": "system",
        "certificate_pins": [],
    }
    assert trace["operation"]["retry_attempt"] == 2


def test_network_runtime_service_records_sse_connection_messages_and_close(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.closed = False

        def start(self, *, timeout_seconds=None):
            return {
                "status_code": 200,
                "headers": {"content-type": "text/event-stream"},
                "url": self.url,
            }

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, metadata = service.connect_sse(
            session_id="debug-sse",
            snapshot=NetworkContextSnapshot(context_id="context-sse"),
            url="https://example.test/events",
            node_id="node-sse",
            connection_id="stream",
        )
        assert metadata["status_code"] == 200
        service.record_connection_message(
            session_id="debug-sse",
            handle=handle,
            connection_id="stream",
            event_kind="message",
            payload={"data": "hello"},
        )
        service.release_connection("debug-sse", handle)
    finally:
        service.close()

    detail = recorder.get_trace(recorder.list_traces(debug_session_id="debug-sse")[0]["trace_id"])
    assert detail["operation"]["protocol"] == "sse"
    assert detail["operation"]["node_id"] == "node-sse"
    assert detail["messages"][0]["payload"] == {"data": "hello"}
    assert detail["messages"][0]["node_id"] == "node-sse"
    assert detail["connections"][0]["connection_id"] == "stream"
    assert detail["connections"][0]["node_id"] == "node-sse"
    assert detail["connections"][0]["connection_state"] == "closed"


def test_network_runtime_service_inherits_debug_event_index_for_connection_messages(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.closed = False

        def start(self, *, timeout_seconds=None):
            return {
                "status_code": 200,
                "headers": {"content-type": "text/event-stream"},
                "url": self.url,
            }

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
        debug_event_index_supplier=lambda: 7,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-index-sse",
            snapshot=NetworkContextSnapshot(context_id="context-index-sse"),
            url="https://example.test/events",
            node_id="node-index-sse",
            connection_id="stream-index-sse",
        )
        service.record_connection_message(
            session_id="debug-index-sse",
            handle=handle,
            connection_id="stream-index-sse",
            event_kind="sse.message",
            payload={"data": "hello"},
        )
        trace = recorder.get_trace(
            recorder.list_traces(debug_session_id="debug-index-sse")[0]["trace_id"]
        )
    finally:
        service.close()

    assert trace["debug_event_index"] == 7
    assert trace["operation"]["debug_event_index"] == 7
    assert trace["connections"][0]["debug_event_index"] == 7
    assert trace["messages"][0]["debug_event_index"] == 7


def test_network_runtime_service_records_graphql_subscription_as_own_protocol(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeWebSocketHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.closed = False
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
            }

        def start(self, *, timeout_seconds=None):
            return {"status": "connected", "url": self.url}

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(network_service_module, "WebSocketClientHandle", FakeWebSocketHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_websocket(
            session_id="debug-graphql",
            snapshot=NetworkContextSnapshot(context_id="context-graphql"),
            url="wss://example.test/graphql",
            node_id="node-graphql",
            connection_id="subscription-1",
            subprotocols=["graphql-transport-ws"],
            trace_operation_id="network.graphql_subscription",
            trace_protocol="graphql_subscription",
        )
        service.release_connection("debug-graphql", handle)
    finally:
        service.close()

    detail = recorder.get_trace(recorder.list_traces(debug_session_id="debug-graphql")[0]["trace_id"])
    assert detail["operation"]["operation_id"] == "network.graphql_subscription"
    assert detail["operation"]["protocol"] == "graphql_subscription"
    assert detail["connections"][0]["operation_id"] == "network.graphql_subscription"
    assert detail["connections"][0]["protocol"] == "graphql_subscription"


def test_network_runtime_service_writes_queue_status_to_connection_trace(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeWebSocketHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.closed = False
            self.queue_status = {
                "depth": 3,
                "dropped_count": 2,
                "drop_events": [
                    {
                        "event_kind": "network.queue_message_dropped",
                        "policy": "drop_oldest",
                        "dropped_count": 2,
                        "first_sequence_id": 5,
                        "last_sequence_id": 6,
                        "connection_id": "socket-1",
                        "connection_epoch": 3,
                    }
                ],
                "backpressure_policy": "drop_oldest",
                "connection_epoch": 3,
            }

        def start(self, *, timeout_seconds=None):
            return {"status": "connected", "url": self.url}

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(network_service_module, "WebSocketClientHandle", FakeWebSocketHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_websocket(
            session_id="debug-queue",
            snapshot=NetworkContextSnapshot(context_id="context-queue"),
            url="wss://example.test/events",
            node_id="node-queue",
            connection_id="socket-1",
        )
        service.record_connection_message(
            session_id="debug-queue",
            handle=handle,
            connection_id="socket-1",
            event_kind="websocket.message",
            payload="frame",
            sequence_id=7,
            connection_epoch=3,
        )
        service.release_connection("debug-queue", handle)
    finally:
        service.close()

    detail = recorder.get_trace(recorder.list_traces(debug_session_id="debug-queue")[0]["trace_id"])
    connection = detail["connections"][0]
    assert connection["queue_depth"] == 3
    assert connection["dropped_count"] == 2
    assert connection["backpressure_policy"] == "drop_oldest"
    assert connection["connection_epoch"] == 3
    assert connection["reconnect_count"] == 2
    assert connection["drop_events"][0]["first_sequence_id"] == 5
    assert connection["drop_events"][0]["last_sequence_id"] == 6
    assert detail["messages"][0]["sequence_id"] == 7
    assert detail["messages"][0]["connection_epoch"] == 3


def test_network_runtime_service_writes_reconnect_reason_to_connection_trace(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeWebSocketHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "backpressure_policy": "fail_stream",
                "connection_epoch": 2,
                "reconnect_count": 1,
                "reconnect_reason": "network.websocket_peer_closed",
            }

        def start(self, *, timeout_seconds=None):
            return {"status": "connected", "url": self.url}

        def close(self) -> None:
            return

    monkeypatch.setattr(network_service_module, "WebSocketClientHandle", FakeWebSocketHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_websocket(
            session_id="debug-reconnect-reason",
            snapshot=NetworkContextSnapshot(context_id="context-reconnect-reason"),
            url="wss://example.test/events",
            node_id="node-reconnect-reason",
            connection_id="socket-reconnect-reason",
        )
        service.refresh_connection_traces(session_id="debug-reconnect-reason")
        trace_id = recorder.list_traces(debug_session_id="debug-reconnect-reason")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
        service.release_connection("debug-reconnect-reason", handle)
    finally:
        service.close()

    assert detail["connections"][0]["reconnect_reason"] == "network.websocket_peer_closed"


def test_network_runtime_service_preserves_failed_connection_terminal_state(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeWebSocketHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "failed",
                "reconnect_reason": "network.websocket_reconnect_failed",
            }

        def start(self, *, timeout_seconds=None):
            return {"status": "connected", "url": self.url}

        def close(self) -> None:
            return

    monkeypatch.setattr(network_service_module, "WebSocketClientHandle", FakeWebSocketHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_websocket(
            session_id="debug-failed-connection",
            snapshot=NetworkContextSnapshot(context_id="context-failed-connection"),
            url="wss://example.test/events",
            node_id="node-failed-connection",
            connection_id="socket-failed-connection",
        )
        service.refresh_connection_traces(session_id="debug-failed-connection")
        trace_id = recorder.list_traces(debug_session_id="debug-failed-connection")[0]["trace_id"]
        service.release_connection("debug-failed-connection", handle)
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    connection = detail["connections"][0]
    assert connection["connection_state"] == "failed"
    assert connection["reconnect_reason"] == "network.websocket_reconnect_failed"


def test_network_runtime_service_refreshes_trace_after_automatic_reconnect(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "connected",
            }
            self.last_event_id = "event-1"

        def start(self, *, timeout_seconds=None):
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.queue_status = {
                **self.queue_status,
                "closed": True,
                "connection_state": "closed",
            }

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-refresh",
            snapshot=NetworkContextSnapshot(context_id="context-refresh"),
            url="https://example.test/events",
            node_id="node-refresh",
            connection_id="stream-refresh",
        )
        handle.queue_status = {
            **handle.queue_status,
            "connection_epoch": 2,
            "reconnect_count": 1,
            "connection_state": "connected",
        }
        service.refresh_connection_traces(session_id="debug-refresh")
        trace_id = recorder.list_traces(debug_session_id="debug-refresh")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    connection = detail["connections"][0]
    assert connection["connection_epoch"] == 2
    assert connection["reconnect_count"] == 1
    assert connection["connection_state"] == "connected"


def test_network_runtime_service_records_automatic_activation_before_node_receive(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        activation_sink = None

        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.activation_sink = kwargs["activation_sink"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "drop_events": [],
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "connected",
            }

        def start(self, *, timeout_seconds=None):
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.queue_status = {**self.queue_status, "connection_state": "closed"}

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-auto-message",
            snapshot=NetworkContextSnapshot(context_id="context-auto-message"),
            url="https://example.test/events",
            node_id="node-auto-message",
            connection_id="stream-auto-message",
        )
        handle.activation_sink(
            {
                "sequence_id": 4,
                "connection_id": "stream-auto-message",
                "connection_epoch": 1,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {
                        "sequence_id": 4,
                        "connection_id": "stream-auto-message",
                        "connection_epoch": 1,
                        "payload": {
                            "event_id": "event-auto",
                            "event_type": "message",
                            "data": "automatic",
                        },
                    },
                },
            }
        )
        trace_id = recorder.list_traces(debug_session_id="debug-auto-message")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["event_kind"] == "sse.message"
    assert detail["messages"][0]["payload"]["data"] == "automatic"
    assert detail["messages"][0]["sequence_id"] == 4


def test_network_runtime_service_records_session_activation_queue_metrics(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.activation_sink = kwargs["activation_sink"]
            self.queue_status = {
                "depth": 1,
                "dropped_count": 0,
                "drop_events": [],
                "backpressure_policy": "drop_newest",
                "connection_epoch": 1,
                "connection_state": "connected",
            }

        def start(self, *, timeout_seconds=None):
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.queue_status = {**self.queue_status, "connection_state": "closed"}

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-session-queue-metrics",
            snapshot=NetworkContextSnapshot(context_id="context-queue-metrics"),
            url="https://example.test/events",
            node_id="node-queue-metrics",
            connection_id="stream-queue-metrics",
            max_queue_size=1,
            backpressure_policy="drop_newest",
        )
        handle.activation_sink(
            {
                "sequence_id": 1,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {"sequence_id": 1, "payload": {"data": "first"}},
                },
            }
        )
        handle.activation_sink(
            {
                "sequence_id": 2,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {"sequence_id": 2, "payload": {"data": "second"}},
                },
            }
        )
        trace_id = recorder.list_traces(debug_session_id="debug-session-queue-metrics")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    connection = detail["connections"][0]
    assert connection["activation_queue_depth"] == 1
    assert connection["activation_dropped_count"] == 1
    assert connection["activation_drop_events"][0]["event_kind"] == "network.queue_message_dropped"


def test_network_runtime_service_records_zero_activation_depth_after_connection_release(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.connection_id = kwargs["connection_id"]
            self.activation_sink = kwargs["activation_sink"]
            self.closed = False
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "drop_events": [],
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "connected",
            }

        def start(self, *, timeout_seconds=None):
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.closed = True
            self.queue_status = {**self.queue_status, "connection_state": "closed"}

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-release-activation",
            snapshot=NetworkContextSnapshot(context_id="context-release-activation"),
            url="https://example.test/events",
            connection_id="stream-release-activation",
        )
        handle.activation_sink(
            {
                "sequence_id": 1,
                "connection_id": "stream-release-activation",
                "connection_epoch": 1,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {"sequence_id": 1, "payload": {"data": "one"}},
                },
            }
        )
        handle.activation_sink(
            {
                "sequence_id": 2,
                "connection_id": "stream-release-activation",
                "connection_epoch": 1,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {"sequence_id": 2, "payload": {"data": "two"}},
                },
            }
        )
        trace_id = recorder.list_traces(debug_session_id="debug-release-activation")[0]["trace_id"]
        service.release_connection("debug-release-activation", handle)
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    connection = detail["connections"][0]
    assert connection["connection_state"] == "closed"
    assert connection["close_reason"] == "released"
    assert connection["activation_queue_depth"] == 0


def test_network_runtime_service_records_zero_activation_depth_after_session_cancel(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.connection_id = kwargs["connection_id"]
            self.activation_sink = kwargs["activation_sink"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "drop_events": [],
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "connected",
            }

        def start(self, *, timeout_seconds=None):
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.queue_status = {**self.queue_status, "connection_state": "closed"}

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        handle, _ = service.connect_sse(
            session_id="debug-cancel-activation",
            snapshot=NetworkContextSnapshot(context_id="context-cancel-activation"),
            url="https://example.test/events",
            connection_id="stream-cancel-activation",
        )
        handle.activation_sink(
            {
                "sequence_id": 1,
                "connection_id": "stream-cancel-activation",
                "connection_epoch": 1,
                "payload": {
                    "event_kind": "sse.message",
                    "message": {"sequence_id": 1, "payload": {"data": "one"}},
                },
            }
        )
        trace_id = recorder.list_traces(debug_session_id="debug-cancel-activation")[0]["trace_id"]
        service.cancel_session("debug-cancel-activation")
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    connection = detail["connections"][0]
    assert connection["connection_state"] == "closed"
    assert connection["close_reason"] == "session_cancelled"
    assert connection["activation_queue_depth"] == 0


def test_network_runtime_service_flushes_activation_arriving_during_connect(
    tmp_path,
    monkeypatch,
) -> None:
    recorder = NetworkTraceRecorder()

    class FakeSseHandle:
        def __init__(self, **kwargs) -> None:
            self.url = kwargs["url"]
            self.activation_sink = kwargs["activation_sink"]
            self.queue_status = {
                "depth": 0,
                "dropped_count": 0,
                "drop_events": [],
                "backpressure_policy": "fail_stream",
                "connection_epoch": 1,
                "connection_state": "connected",
            }

        def start(self, *, timeout_seconds=None):
            self.activation_sink(
                {
                    "sequence_id": 9,
                    "payload": {
                        "event_kind": "sse.message",
                        "message": {
                            "sequence_id": 9,
                            "connection_epoch": 1,
                            "payload": {"data": "arrived-during-connect"},
                        },
                    },
                }
            )
            return {"status_code": 200, "headers": {}, "url": self.url}

        def close(self) -> None:
            self.queue_status = {**self.queue_status, "connection_state": "closed"}

    monkeypatch.setattr(network_service_module, "SSEClientHandle", FakeSseHandle)
    service = NetworkRuntimeService(
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        service.connect_sse(
            session_id="debug-connect-race",
            snapshot=NetworkContextSnapshot(context_id="context-connect-race"),
            url="https://example.test/events",
            node_id="node-connect-race",
            connection_id="stream-connect-race",
        )
        trace_id = recorder.list_traces(debug_session_id="debug-connect-race")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert detail["messages"][0]["payload"]["data"] == "arrived-during-connect"


def test_network_runtime_service_keeps_large_response_body_as_resource_reference(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    payload = b"x" * (4 * 1024 * 1024 + 1)
    service = NetworkRuntimeService(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/octet-stream"},
                content=payload,
            )
        ),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.download",
                session_id="debug-large-response",
                method="GET",
                url="https://example.test/large.bin",
                node_id="node-large-response",
            ),
            NetworkContextSnapshot(context_id="context-large-response"),
        ).result(timeout=2)
        trace_id = recorder.list_traces(debug_session_id="debug-large-response")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert result.status == "succeeded"
    assert detail["operation"]["response_body"]["resource_id"]
    assert detail["operation"]["response_body"]["available"] is True
    assert "value" not in detail["operation"]["response_body"]
    assert detail["operation"]["response_body"]["size_bytes"] == len(payload)


def test_network_runtime_service_records_upload_file_body_as_resource_reference(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    upload_path = Path(tmp_path) / "upload.bin"
    payload = b"file-upload-payload"
    upload_path.write_bytes(payload)
    observed: dict[str, bytes] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["body"] = await request.aread()
        return httpx.Response(204, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.upload",
                session_id="debug-upload-file",
                method="POST",
                url="https://example.test/upload",
                upload_file_path=upload_path,
                upload_allowed_roots=(Path(tmp_path),),
                node_id="node-upload-file",
            ),
            NetworkContextSnapshot(context_id="context-upload-file"),
        ).result(timeout=2)
        trace_id = recorder.list_traces(debug_session_id="debug-upload-file")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert result.status == "succeeded"
    assert observed["body"] == payload
    assert detail["operation"]["request_body"]["resource_id"]
    assert detail["operation"]["request_body"]["size_bytes"] == len(payload)
    assert detail["operation"]["request_body"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert "value" not in detail["operation"]["request_body"]


def test_network_runtime_service_records_upload_stream_body_as_resource_reference(tmp_path) -> None:
    recorder = NetworkTraceRecorder()
    payload = b"stream-upload-payload"
    observed: dict[str, bytes] = {}

    async def upload_stream():
        yield payload[:6]
        yield payload[6:]

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["body"] = await request.aread()
        return httpx.Response(204, request=request)

    service = NetworkRuntimeService(
        transport=httpx.MockTransport(handler),
        response_root_directory=tmp_path,
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
        trace_recorder=recorder,
    )
    try:
        result = service.submit(
            NetworkOperation(
                operation_id="network.upload",
                session_id="debug-upload-stream",
                method="POST",
                url="https://example.test/upload-stream",
                upload_stream=upload_stream(),
                node_id="node-upload-stream",
            ),
            NetworkContextSnapshot(context_id="context-upload-stream"),
        ).result(timeout=2)
        trace_id = recorder.list_traces(debug_session_id="debug-upload-stream")[0]["trace_id"]
        detail = recorder.get_trace(trace_id)
    finally:
        service.close()

    assert result.status == "succeeded"
    assert observed["body"] == payload
    assert detail["operation"]["request_body"]["resource_id"]
    assert detail["operation"]["request_body"]["size_bytes"] == len(payload)
    assert detail["operation"]["request_body"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert "value" not in detail["operation"]["request_body"]
