from __future__ import annotations

import pytest

from weconduct.application.operations import (
    HostOperationService,
    OperationCaller,
    OperationRegistry,
)


_CALLER = OperationCaller(
    caller_id="external:debug-network-contract",
    permissions=frozenset({"operation.invoke"}),
)


class _DebugNetworkService:
    def get_debug_session_network_summary(self, *, session_id: str, history: bool = False) -> dict:
        assert session_id == "debug-1"
        assert history is True
        return {
            "session_id": session_id,
            "source": "history_store",
            "summary": {
                "total_operations": 1,
                "successful_operations": 0,
                "failed_operations": 1,
                "cancelled_operations": 0,
                "active_connections": 1,
                "queue_depth": 4,
                "reconnect_count": 2,
                "dropped_count": 1,
                "recent_errors": [
                    {
                        "trace_id": "trace-1",
                        "operation_id": "network.http_request",
                        "status": "failed",
                        "error_code": "network.timeout",
                        "ended_at": "2026-08-29T12:00:00Z",
                        "request_body": {"value": "must-not-leak"},
                    }
                ],
            },
        }

    def get_debug_session_network(
        self,
        *,
        session_id: str,
        history: bool = False,
        protocol: str | None = None,
        status: str | None = None,
        node_id: str | None = None,
        operation_id: str | None = None,
        connection_id: str | None = None,
        include_body: bool = False,
    ) -> dict:
        assert session_id == "debug-1"
        assert history is False
        assert protocol == "websocket"
        assert status == "failed"
        assert node_id == "node-http"
        assert operation_id == "network.http_request"
        assert connection_id == "connection-1"
        assert include_body is False
        return {
            "session_id": session_id,
            "source": "active_session",
            "summary": {
                "total_operations": 1,
                "successful_operations": 0,
                "failed_operations": 1,
                "cancelled_operations": 0,
                "active_connections": 1,
                "queue_depth": 4,
                "reconnect_count": 2,
                "dropped_count": 1,
                "recent_errors": [
                    {
                        "trace_id": "trace-1",
                        "operation_id": "network.http_request",
                        "status": "failed",
                        "error_code": "network.timeout",
                        "ended_at": "2026-08-29T12:00:00Z",
                    }
                ],
            },
            "traces": [
                {
                    "trace_id": "trace-1",
                    "debug_session_id": session_id,
                    "runtime_session_id": session_id,
                    "node_id": "node-http",
                    "operation_id": "network.http_request",
                    "method": "POST",
                    "url": "https://example.test/api",
                    "started_at": "2026-08-29T11:59:58Z",
                    "ended_at": "2026-08-29T12:00:00Z",
                    "duration_ms": 1200.5,
                    "status": "failed",
                    "error_code": "network.timeout",
                    "response_status": 504,
                    "request_headers": {
                        "Authorization": "Bearer secret-token",
                        "Cookie": "sid=secret",
                        "content-type": "application/json",
                    },
                    "response_headers": {
                        "Set-Cookie": "sid=secret",
                        "content-type": "application/json",
                    },
                    "request_body": {"encoding": "text", "value": "{\"secret\":true}"},
                    "response_body": {"encoding": "text", "value": "{\"error\":\"timeout\"}"},
                    "connections": [
                        {
                            "connection_id": "connection-1",
                            "connection_state": "open",
                            "queue_depth": 4,
                            "reconnect_count": 2,
                            "dropped_count": 1,
                            "message_count": 3,
                            "last_event_id": "evt-9",
                            "protocol": "websocket",
                        }
                    ],
                "messages": [
                    {
                        "event_kind": "message.received",
                        "protocol": "websocket",
                        "connection_id": "connection-1",
                        "payload": {"token": "must-not-leak"},
                    }
                ],
            },
            {
                # get_debug_session_network() 返回的是扁平记录；消息可能
                # 带有从父连接继承的 protocol，但不能被当成连接摘要。
                "trace_id": "trace-1",
                "event_kind": "message.received",
                "protocol": "websocket",
                "connection_id": "connection-1",
                "sequence_id": 8,
                "debug_event_index": 12,
            },
        ],
    }

    def get_debug_session_network_trace(
        self,
        *,
        session_id: str,
        trace_id: str,
        history: bool = False,
    ) -> dict:
        assert session_id == "debug-1"
        assert trace_id == "trace-1"
        assert history is True
        return {
            "session_id": session_id,
            "source": "history_store",
            "trace": {
                "trace_id": trace_id,
                "status": "failed",
                "request_body": {"encoding": "text", "value": "must-not-leak"},
                "messages": [{"payload": "must-not-leak"}],
                "operation": {
                    "method": "GET",
                    "url": "https://example.test/history",
                    "status": "failed",
                    "error_code": "network.timeout",
                    "duration_ms": 3500,
                    "request_headers": {"Cookie": "sid=secret"},
                    "response_headers": {"Set-Cookie": "sid=secret"},
                    "request_body": {"encoding": "text", "value": "must-not-leak"},
                    "response_body": {"encoding": "text", "value": "must-not-leak"},
                    "response_status": 504,
                },
                "connections": [
                    {
                        "connection_id": "connection-2",
                        "protocol": "sse",
                        "connection_state": "failed",
                        "queue_depth": 0,
                        "reconnect_count": 1,
                        "dropped_count": 0,
                        "message_count": 0,
                        "last_event_id": None,
                    }
                ],
            },
        }


def test_debug_network_summary_operation_uses_read_only_contract() -> None:
    service = HostOperationService(service=_DebugNetworkService())

    result = service.invoke(
        "debug.network.summary",
        {"session_id": "debug-1", "history": True},
        caller=_CALLER,
    )

    assert result == {
        "session_id": "debug-1",
        "source": "history_store",
        "summary": {
            "total_operations": 1,
            "successful_operations": 0,
            "failed_operations": 1,
            "cancelled_operations": 0,
            "active_connections": 1,
            "queue_depth": 4,
            "reconnect_count": 2,
            "dropped_count": 1,
            "recent_errors": [
                {
                    "trace_id": "trace-1",
                    "operation_id": "network.http_request",
                    "status": "failed",
                    "error_code": "network.timeout",
                    "ended_at": "2026-08-29T12:00:00Z",
                }
            ],
        },
    }


def test_debug_network_list_operation_filters_and_removes_sensitive_fields() -> None:
    service = HostOperationService(service=_DebugNetworkService())

    result = service.invoke(
        "debug.network.list",
        {
            "session_id": "debug-1",
            "protocol": "websocket",
            "status": "failed",
            "node_id": "node-http",
            "operation_id": "network.http_request",
            "connection_id": "connection-1",
        },
        caller=_CALLER,
    )

    assert result == {
        "session_id": "debug-1",
        "source": "active_session",
        "summary": {
            "total_operations": 1,
            "successful_operations": 0,
            "failed_operations": 1,
            "cancelled_operations": 0,
            "active_connections": 1,
            "queue_depth": 4,
            "reconnect_count": 2,
            "dropped_count": 1,
            "recent_errors": [
                {
                    "trace_id": "trace-1",
                    "operation_id": "network.http_request",
                    "status": "failed",
                    "error_code": "network.timeout",
                    "ended_at": "2026-08-29T12:00:00Z",
                }
            ],
        },
        "traces": [
            {
                "trace_id": "trace-1",
                "node_id": "node-http",
                "operation_id": "network.http_request",
                "method": "POST",
                "url": "https://example.test/api",
                "started_at": "2026-08-29T11:59:58Z",
                "ended_at": "2026-08-29T12:00:00Z",
                "duration_ms": 1200.5,
                "status": "failed",
                "error_code": "network.timeout",
                "response_status": 504,
                "connection_summary": {
                    "connection_count": 1,
                    "active_connection_count": 1,
                    "queue_depth": 4,
                    "reconnect_count": 2,
                    "dropped_count": 1,
                    "message_count": 3,
                    "last_event_id": "evt-9",
                    "protocols": ["websocket"],
                },
            }
        ],
    }


def test_debug_network_get_operation_returns_single_sanitized_trace_without_bodies() -> None:
    service = HostOperationService(service=_DebugNetworkService())

    result = service.invoke(
        "debug.network.get",
        {"session_id": "debug-1", "trace_id": "trace-1", "history": True},
        caller=_CALLER,
    )

    assert result == {
        "session_id": "debug-1",
        "source": "history_store",
        "trace": {
            "trace_id": "trace-1",
            "node_id": None,
            "operation_id": None,
            "method": "GET",
            "url": "https://example.test/history",
            "started_at": None,
            "ended_at": None,
            "duration_ms": 3500,
            "status": "failed",
            "error_code": "network.timeout",
            "response_status": 504,
            "connection_summary": {
                "connection_count": 1,
                "active_connection_count": 0,
                "queue_depth": 0,
                "reconnect_count": 1,
                "dropped_count": 0,
                "message_count": 0,
                "last_event_id": None,
                "protocols": ["sse"],
            },
        },
    }


def test_debug_network_external_url_masks_sensitive_query_values() -> None:
    class _UrlService:
        def get_debug_session_network_trace(
            self,
            *,
            session_id: str,
            trace_id: str,
            history: bool = False,
        ) -> dict:
            return {
                "session_id": session_id,
                "source": "history_store",
                "trace": {
                    "trace_id": trace_id,
                    "operation": {
                        "method": "GET",
                        "url": (
                            "https://example.test/items?access_token=query-secret"
                            "&page=2"
                        ),
                        "status": "succeeded",
                    },
                    "connections": [],
                },
            }

    service = HostOperationService(service=_UrlService())

    result = service.invoke(
        "debug.network.get",
        {"session_id": "debug-url", "trace_id": "trace-url", "history": True},
        caller=_CALLER,
    )

    url = result["trace"]["url"]
    assert "query-secret" not in url
    assert "access_token=%3Credacted%3E" in url
    assert "page=2" in url


def test_debug_network_operations_are_registered_as_stable_read_only_contracts() -> None:
    registry = OperationRegistry.build_stable_public()

    summary = registry.describe("debug.network.summary")
    listing = registry.describe("debug.network.list")
    detail = registry.describe("debug.network.get")

    assert summary.side_effect_level.value == "read"
    assert listing.side_effect_level.value == "read"
    assert detail.side_effect_level.value == "read"
    assert summary.input_model.model_json_schema()["properties"]["history"]["default"] is False
    assert "trace_id" in detail.input_model.model_json_schema()["properties"]
    assert set(listing.output_fields) == {"session_id", "source", "summary", "traces"}
    assert set(detail.output_fields) == {"session_id", "source", "trace"}


def test_debug_network_get_requires_trace_id() -> None:
    service = HostOperationService(service=_DebugNetworkService())

    with pytest.raises(Exception):
        service.invoke(
            "debug.network.get",
            {"session_id": "debug-1"},
            caller=_CALLER,
        )


def test_debug_network_query_schema_declares_supported_list_filters() -> None:
    listing = OperationRegistry.build_stable_public().describe("debug.network.list")
    properties = listing.input_model.model_json_schema()["properties"]

    assert {"event_kind", "from_time", "to_time", "page", "page_size"} <= set(properties)
    assert properties["page"]["anyOf"][0]["minimum"] == 1 or properties["page"].get("minimum") == 1
