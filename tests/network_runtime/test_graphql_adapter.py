from __future__ import annotations

import pytest

from weconduct.network_runtime.graphql_adapter import (
    GraphQLAdapterError,
    GraphQLProtocolAdapter,
    GraphQLSubscriptionProtocol,
)


def test_graphql_adapter_selects_named_operation_and_builds_http_operation() -> None:
    adapter = GraphQLProtocolAdapter()

    operation = adapter.build_operation(
        endpoint="https://example.test/graphql",
        query="query One($id: ID!) { item(id: $id) { id } } query Two { health }",
        operation_name="One",
        variables={"id": "7"},
        session_id="session-1",
    )

    assert operation.method == "POST"
    assert operation.url == "https://example.test/graphql"
    assert operation.headers["Content-Type"] == "application/json"
    assert b'"operationName": "One"' in operation.content  # type: ignore[operator]


def test_graphql_adapter_rejects_missing_or_unknown_operation_name() -> None:
    adapter = GraphQLProtocolAdapter()
    query = "query One { health } query Two { status }"

    with pytest.raises(GraphQLAdapterError, match="operation_name is required"):
        adapter.build_operation(endpoint="https://example.test/graphql", query=query, session_id="s")
    with pytest.raises(GraphQLAdapterError, match="operation was not found"):
        adapter.build_operation(
            endpoint="https://example.test/graphql",
            query=query,
            operation_name="Missing",
            session_id="s",
        )


def test_graphql_adapter_parses_data_errors_and_extensions() -> None:
    result = GraphQLProtocolAdapter().parse_response(
        {"data": {"health": True}, "errors": [{"message": "partial"}], "extensions": {"trace": "x"}}
    )

    assert result.data == {"health": True}
    assert result.errors == ({"message": "partial"},)
    assert result.extensions == {"trace": "x"}


def test_graphql_subscription_builds_transport_ws_frames() -> None:
    adapter = GraphQLProtocolAdapter()

    request = adapter.build_subscription(
        endpoint="https://example.test/graphql",
        query="subscription Watch { updates { id } }",
        operation_name="Watch",
        variables={"limit": 1},
        session_id="session-1",
    )

    assert request.endpoint == "wss://example.test/graphql"
    assert request.subprotocol == "graphql-transport-ws"
    assert GraphQLSubscriptionProtocol.connection_init() == {
        "type": "connection_init"
    }
    assert GraphQLSubscriptionProtocol.subscribe(
        request_id="sub-1",
        request=request,
    )["type"] == "subscribe"


def test_graphql_subscription_accepts_direct_websocket_endpoint() -> None:
    request = GraphQLProtocolAdapter().build_subscription(
        endpoint="ws://127.0.0.1:3456/api/network/graphql-ws",
        query="subscription Watch { updates { id } }",
        session_id="session-1",
    )

    assert request.endpoint == "ws://127.0.0.1:3456/api/network/graphql-ws"


def test_graphql_subscription_parses_next_error_and_complete_frames() -> None:
    protocol = GraphQLSubscriptionProtocol()

    next_frame = protocol.parse(
        '{"id":"sub-1","type":"next","payload":{"data":{"updates":[]}}}'
    )
    error_frame = protocol.parse(
        '{"id":"sub-1","type":"error","payload":[{"message":"bad"}]}'
    )
    complete_frame = protocol.parse('{"id":"sub-1","type":"complete"}')

    assert next_frame.type == "next"
    assert next_frame.payload == {"data": {"updates": []}}
    assert error_frame.type == "error"
    assert complete_frame.type == "complete"


def test_graphql_subscription_builds_unsubscribe_frames_for_both_protocols() -> None:
    assert GraphQLSubscriptionProtocol.complete(request_id="sub-1") == {
        "id": "sub-1",
        "type": "complete",
    }
    assert GraphQLSubscriptionProtocol.stop(request_id="sub-1") == {
        "id": "sub-1",
        "type": "stop",
    }
