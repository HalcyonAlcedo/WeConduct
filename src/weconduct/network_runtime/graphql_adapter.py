from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping
from urllib.parse import urlsplit

from graphql import DocumentNode, GraphQLError, get_operation_ast, parse

from .models import NetworkOperation


class GraphQLAdapterError(ValueError):
    """Stable GraphQL request/response contract error."""


@dataclass(frozen=True)
class GraphQLResult:
    data: object | None
    errors: tuple[Mapping[str, object], ...]
    extensions: Mapping[str, object]


class GraphQLProtocolAdapter:
    def build_operation(
        self,
        *,
        endpoint: str,
        query: str,
        session_id: str,
        operation_name: str | None = None,
        variables: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> NetworkOperation:
        self._validate_endpoint(endpoint)
        if not isinstance(query, str) or not query.strip():
            raise GraphQLAdapterError("graphql.query_required")
        try:
            document = parse(query)
        except GraphQLError as exc:
            raise GraphQLAdapterError("graphql.query_invalid") from exc
        operation_ast = get_operation_ast(document, operation_name)
        if operation_ast is None:
            if operation_name is None and self._operation_count(document) > 1:
                raise GraphQLAdapterError("graphql.operation_name is required")
            raise GraphQLAdapterError("graphql.operation was not found")
        if operation_ast.operation.value == "subscription":
            raise GraphQLAdapterError("graphql.subscription_requires_websocket")
        payload = {
            "query": query,
            "variables": dict(variables or {}),
            "operationName": operation_name,
        }
        request_headers = {str(key): str(value) for key, value in (headers or {}).items()}
        request_headers.setdefault("Content-Type", "application/json")
        return NetworkOperation(
            operation_id=f"graphql-{session_id}",
            session_id=session_id,
            method="POST",
            url=endpoint,
            headers=request_headers,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    def parse_response(self, response: Mapping[str, object]) -> GraphQLResult:
        if not isinstance(response, Mapping):
            raise GraphQLAdapterError("graphql.response_invalid")
        errors = response.get("errors", ())
        if errors is None:
            errors = ()
        if not isinstance(errors, (list, tuple)) or not all(isinstance(item, Mapping) for item in errors):
            raise GraphQLAdapterError("graphql.errors_invalid")
        extensions = response.get("extensions", {})
        if not isinstance(extensions, Mapping):
            raise GraphQLAdapterError("graphql.extensions_invalid")
        return GraphQLResult(
            data=response.get("data"),
            errors=tuple(dict(item) for item in errors),
            extensions=dict(extensions),
        )

    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise GraphQLAdapterError("graphql.endpoint_invalid")

    @staticmethod
    def _operation_count(document: DocumentNode) -> int:
        return sum(1 for definition in document.definitions if definition.kind == "operation_definition")
