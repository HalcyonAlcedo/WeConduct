from __future__ import annotations

from weconduct.network_runtime.resources import ResponseBodyStore
from weconduct.network_runtime.trace import (
    TRACE_MESSAGE_BODY_THRESHOLD_BYTES,
    NetworkTraceRecorder,
)


def test_network_trace_recorder_records_queries_and_summary() -> None:
    recorder = NetworkTraceRecorder()

    operation = recorder.start_operation(
        trace_id="trace-1",
        debug_session_id="debug-session-1",
        runtime_session_id="runtime-session-1",
        node_id="node-1",
        operation_id="operation-1",
        method="POST",
        url="https://example.test/api",
        request_headers={"Content-Type": "application/json"},
        request_query={"q": "alpha"},
        request_body='{"hello":"world"}',
        retry_attempt=1,
    )
    recorder.update_connection(
        trace_id="trace-1",
        debug_session_id="debug-session-1",
        runtime_session_id="runtime-session-1",
        node_id="node-1",
        operation_id="operation-1",
        connection_id="connection-1",
        connection_epoch=2,
        protocol="sse",
        subprotocol="text/event-stream",
        connection_state="connected",
        message_count=0,
        last_event_id="event-0",
        reconnect_count=1,
        queue_depth=3,
        dropped_count=0,
        drop_events=[
            {
                "event_kind": "network.queue_message_dropped",
                "policy": "drop_oldest",
                "dropped_count": 0,
                "first_sequence_id": 0,
                "last_sequence_id": 0,
                "connection_id": "connection-1",
                "connection_epoch": 2,
            }
        ],
        backpressure_policy="drop-oldest",
    )
    recorder.append_message(
        trace_id="trace-1",
        debug_session_id="debug-session-1",
        runtime_session_id="runtime-session-1",
        node_id="node-1",
        operation_id="operation-1",
        connection_id="connection-1",
        connection_epoch=2,
        event_kind="message",
        payload={"event": "ping"},
        sequence_id=7,
        debug_event_index=11,
    )
    recorder.complete_operation(
        trace_id="trace-1",
        status="succeeded",
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"ok":true}',
    )

    detail = recorder.get_trace("trace-1")
    assert detail["trace_id"] == "trace-1"
    assert detail["operation"]["method"] == "POST"
    assert detail["operation"]["request_body"]["value"] == '{"hello":"world"}'
    assert detail["operation"]["response_body"]["value"] == '{"ok":true}'
    assert detail["connections"][0]["queue_depth"] == 3
    assert detail["messages"][0]["payload"]["event"] == "ping"

    session_items = recorder.list_traces(debug_session_id="debug-session-1")
    assert [item["trace_id"] for item in session_items] == ["trace-1", "trace-1", "trace-1"]

    summary = recorder.summary(debug_session_id="debug-session-1")
    assert summary["total_operations"] == 1
    assert summary["successful_operations"] == 1
    assert summary["failed_operations"] == 0
    assert summary["cancelled_operations"] == 0
    assert summary["active_connections"] == 1
    assert summary["queue_depth"] == 3
    assert summary["reconnect_count"] == 1
    assert summary["dropped_count"] == 0
    assert summary["queue_events"][0]["connection_id"] == "connection-1"
    assert summary["recent_errors"] == []


def test_network_trace_recorder_filters_and_preserves_binary_bodies() -> None:
    recorder = NetworkTraceRecorder()

    recorder.start_operation(
        trace_id="trace-2",
        debug_session_id="debug-session-2",
        runtime_session_id="runtime-session-2",
        node_id="node-2",
        operation_id="operation-2",
        method="GET",
        url="https://example.test/download",
        request_body=b"\x00\x01\x02",
    )
    recorder.complete_operation(
        trace_id="trace-2",
        status="failed",
        error_code="network.timeout",
    )

    items = recorder.list_traces(operation_id="operation-2", status="failed", node_id="node-2")
    assert len(items) == 1
    assert items[0]["request_body"]["encoding"] == "base64"


def test_network_trace_recorder_falls_back_to_base64_for_invalid_text_bytes() -> None:
    recorder = NetworkTraceRecorder()

    operation = recorder.start_operation(
        trace_id="trace-invalid-text",
        debug_session_id="debug-session-invalid-text",
        runtime_session_id="runtime-session-invalid-text",
        node_id="node-invalid-text",
        operation_id="operation-invalid-text",
        method="GET",
        url="https://example.test/invalid",
        request_headers={"content-type": "text/plain"},
        request_body=b"\xff\xfe",
    )

    assert operation["request_body"]["encoding"] == "base64"


def test_network_trace_recorder_keeps_textual_bytes_and_filters_protocol_status() -> None:
    recorder = NetworkTraceRecorder()

    recorder.start_operation(
        trace_id="trace-3",
        debug_session_id="debug-session-3",
        runtime_session_id="runtime-session-3",
        node_id="node-3",
        operation_id="operation-3",
        method="POST",
        url="https://example.test/events",
        protocol="sse",
        request_headers={"content-type": "application/json; charset=utf-8"},
        request_body=b'{"hello":"world"}',
    )
    recorder.update_connection(
        trace_id="trace-3",
        debug_session_id="debug-session-3",
        runtime_session_id="runtime-session-3",
        node_id="node-3",
        operation_id="operation-3",
        connection_id="connection-3",
        protocol="websocket",
        connection_state="connected",
    )
    recorder.complete_operation(
        trace_id="trace-3",
        status="succeeded",
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"ok":true}',
    )

    detail = recorder.get_trace("trace-3")
    assert detail["operation"]["request_body"]["encoding"] == "text"
    assert detail["operation"]["request_body"]["value"] == '{"hello":"world"}'
    assert detail["operation"]["response_body"]["encoding"] == "text"
    assert detail["operation"]["response_body"]["value"] == '{"ok":true}'
    assert detail["operation"]["protocol"] == "sse"

    assert [item["trace_id"] for item in recorder.list_traces(protocol="sse")] == [
        "trace-3",
    ]

    assert [item["trace_id"] for item in recorder.list_traces(protocol="websocket")] == [
        "trace-3",
    ]
    assert [item["trace_id"] for item in recorder.list_traces(status="succeeded")] == [
        "trace-3",
    ]
    assert recorder.list_traces(protocol="sse", status="failed") == []


def test_network_trace_recorder_keeps_transport_redirect_and_retry_metadata() -> None:
    recorder = NetworkTraceRecorder()

    recorder.start_operation(
        trace_id="trace-transport",
        debug_session_id="debug-transport",
        runtime_session_id="runtime-transport",
        node_id="node-http",
        operation_id="network.http_request",
        method="GET",
        url="https://example.test/start",
        proxy={"mode": "http", "url": "http://proxy.test:8080"},
        tls={"verify": "system", "certificate_pins": ["sha256/test"]},
    )
    recorder.complete_operation(
        trace_id="trace-transport",
        status="succeeded",
        response_status=200,
        final_url="https://example.test/final",
        redirects=[
            {
                "status_code": 302,
                "from_url": "https://example.test/start",
                "to_url": "https://example.test/final",
            }
        ],
        retry_attempt=2,
    )

    operation = recorder.get_trace("trace-transport")["operation"]
    assert operation["proxy"] == {"mode": "http", "url": "http://proxy.test:8080"}
    assert operation["tls"] == {"verify": "system", "certificate_pins": ["sha256/test"]}
    assert operation["final_url"] == "https://example.test/final"
    assert operation["redirects"][0]["status_code"] == 302
    assert operation["retry_attempt"] == 2


def test_network_trace_recorder_continues_after_explicit_sequence_id() -> None:
    recorder = NetworkTraceRecorder()
    recorder.start_operation(
        trace_id="trace-sequence-continuity",
        debug_session_id="debug-sequence-continuity",
        runtime_session_id="runtime-sequence-continuity",
        node_id="node-stream",
        operation_id="network.websocket_connect",
        method="GET",
        url="wss://example.test/events",
        protocol="websocket",
    )

    explicit = recorder.append_message(
        trace_id="trace-sequence-continuity",
        debug_session_id="debug-sequence-continuity",
        runtime_session_id="runtime-sequence-continuity",
        node_id="node-stream",
        operation_id="network.websocket_connect",
        connection_id="connection-sequence",
        event_kind="websocket.message",
        payload="explicit",
        sequence_id=17,
    )
    implicit = recorder.append_message(
        trace_id="trace-sequence-continuity",
        debug_session_id="debug-sequence-continuity",
        runtime_session_id="runtime-sequence-continuity",
        node_id="node-stream",
        operation_id="network.websocket_connect",
        connection_id="connection-sequence",
        event_kind="websocket.message",
        payload="implicit",
    )

    assert explicit["sequence_id"] == 17
    assert implicit["sequence_id"] == 18


def test_network_trace_recorder_preserves_connection_metrics_when_update_omits_them() -> None:
    recorder = NetworkTraceRecorder()
    recorder.start_operation(
        trace_id="trace-connection-merge",
        debug_session_id="debug-connection-merge",
        runtime_session_id="runtime-connection-merge",
        node_id="node-stream",
        operation_id="network.websocket_connect",
        method="GET",
        url="wss://example.test/events",
        protocol="websocket",
    )
    recorder.update_connection(
        trace_id="trace-connection-merge",
        debug_session_id="debug-connection-merge",
        runtime_session_id="runtime-connection-merge",
        node_id="node-stream",
        operation_id="network.websocket_connect",
        connection_id="connection-merge",
        connection_epoch=2,
        protocol="websocket",
        subprotocol="graphql-transport-ws",
        connection_state="connected",
        message_count=4,
        last_event_id="event-4",
        reconnect_count=1,
        reconnect_reason="network.websocket_closed",
        queue_depth=3,
        dropped_count=2,
        drop_events=[{"event_kind": "network.queue_message_dropped"}],
        activation_queue_depth=5,
        activation_dropped_count=1,
        activation_drop_events=[{"event_kind": "network.activation_dropped"}],
        backpressure_policy="drop_oldest",
    )

    updated = recorder.update_connection(
        trace_id="trace-connection-merge",
        debug_session_id="debug-connection-merge",
        runtime_session_id="runtime-connection-merge",
        node_id=None,
        operation_id=None,
        connection_id="connection-merge",
        connection_state="closed",
        close_reason="released",
    )

    assert updated["node_id"] == "node-stream"
    assert updated["operation_id"] == "network.websocket_connect"
    assert updated["connection_epoch"] == 2
    assert updated["subprotocol"] == "graphql-transport-ws"
    assert updated["message_count"] == 4
    assert updated["last_event_id"] == "event-4"
    assert updated["reconnect_count"] == 1
    assert updated["reconnect_reason"] == "network.websocket_closed"
    assert updated["queue_depth"] == 3
    assert updated["dropped_count"] == 2
    assert updated["drop_events"] == [{"event_kind": "network.queue_message_dropped"}]
    assert updated["activation_queue_depth"] == 5
    assert updated["activation_dropped_count"] == 1
    assert updated["activation_drop_events"] == [{"event_kind": "network.activation_dropped"}]
    assert updated["backpressure_policy"] == "drop_oldest"
    assert updated["connection_state"] == "closed"
    assert updated["close_reason"] == "released"


def test_network_trace_recorder_keeps_body_ref_for_large_connection_message(tmp_path) -> None:
    store = ResponseBodyStore(session_id="debug-message", root_directory=tmp_path)
    capture = store.open_capture(content_type="application/json", force_file=True)
    capture.write(b'{"large":true}')
    body_ref = capture.finish()

    recorder = NetworkTraceRecorder()
    recorder.start_operation(
        trace_id="trace-large-message",
        debug_session_id="debug-message",
        runtime_session_id="debug-message",
        node_id="node-stream",
        operation_id="network.sse_connect",
        method="GET",
        url="https://example.test/events",
        protocol="sse",
    )
    recorder.append_message(
        trace_id="trace-large-message",
        debug_session_id="debug-message",
        runtime_session_id="debug-message",
        node_id="node-stream",
        operation_id="network.sse_connect",
        connection_id="connection-1",
        event_kind="sse.message",
        payload=body_ref,
    )

    payload = recorder.get_trace("trace-large-message")["messages"][0]["payload"]
    assert payload["resource_kind"] == "session_temp"
    assert payload["resource_id"] == body_ref.resource_id
    assert payload["storage_kind"] == "file"
    store.close()


def test_httpx_adapter_captures_large_connection_message_as_temp_body(tmp_path) -> None:
    import httpx

    from weconduct.network_runtime.http_adapter import HttpxAdapter

    adapter = HttpxAdapter(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        response_root_directory=tmp_path,
    )
    payload = b"x" * (TRACE_MESSAGE_BODY_THRESHOLD_BYTES + 1)

    body_ref = adapter.capture_trace_message_body(
        "debug-message",
        payload,
        content_type="application/octet-stream",
    )

    assert body_ref is not None
    assert body_ref.storage_kind == "file"
    assert body_ref.read_bytes() == payload
    adapter.close_session("debug-message")
