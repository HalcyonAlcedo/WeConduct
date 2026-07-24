from __future__ import annotations

import pytest

from weconduct.network_runtime.graphql_adapter import GraphQLAdapterError, GraphQLProtocolAdapter


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
