from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping
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


@dataclass(frozen=True)
class GraphQLSubscriptionRequest:
    endpoint: str
    query: str
    session_id: str
    operation_name: str | None
    variables: Mapping[str, object]
    headers: Mapping[str, str]
    subprotocol: str = "graphql-transport-ws"


@dataclass(frozen=True)
class GraphQLSubscriptionFrame:
    type: str
    request_id: str | None = None
    payload: object | None = None


class GraphQLSubscriptionProtocol:
    """graphql-transport-ws frame builder/parser without transport ownership."""

    SUPPORTED_TYPES = frozenset(
        {
            "connection_init",
            "connection_ack",
            "ping",
            "pong",
            "subscribe",
            "start",
            "next",
            "data",
            "error",
            "complete",
            "stop",
        }
    )

    @staticmethod
    def connection_init(payload: Mapping[str, object] | None = None) -> dict[str, object]:
        frame: dict[str, object] = {"type": "connection_init"}
        if payload:
            frame["payload"] = dict(payload)
        return frame

    @staticmethod
    def ping(payload: object | None = None) -> dict[str, object]:
        frame: dict[str, object] = {"type": "ping"}
        if payload is not None:
            frame["payload"] = payload
        return frame

    @staticmethod
    def pong(payload: object | None = None) -> dict[str, object]:
        frame: dict[str, object] = {"type": "pong"}
        if payload is not None:
            frame["payload"] = payload
        return frame

    @staticmethod
    def complete(*, request_id: str) -> dict[str, object]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise GraphQLAdapterError("graphql.subscription_id_required")
        return {"id": request_id, "type": "complete"}

    @staticmethod
    def stop(*, request_id: str) -> dict[str, object]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise GraphQLAdapterError("graphql.subscription_id_required")
        return {"id": request_id, "type": "stop"}

    @staticmethod
    def subscribe(*, request_id: str, request: GraphQLSubscriptionRequest) -> dict[str, object]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise GraphQLAdapterError("graphql.subscription_id_required")
        payload: dict[str, object] = {
            "query": request.query,
            "variables": dict(request.variables),
            "operationName": request.operation_name,
        }
        frame_type = "start" if request.subprotocol == "graphql-ws" else "subscribe"
        return {"id": request_id, "type": frame_type, "payload": payload}

    @classmethod
    def parse(cls, message: str | bytes | Mapping[str, object]) -> GraphQLSubscriptionFrame:
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise GraphQLAdapterError("graphql.subscription_frame_invalid") from exc
        if isinstance(message, str):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError as exc:
                raise GraphQLAdapterError("graphql.subscription_frame_invalid") from exc
        else:
            payload = dict(message) if isinstance(message, Mapping) else None
        if not isinstance(payload, Mapping):
            raise GraphQLAdapterError("graphql.subscription_frame_invalid")
        frame_type = payload.get("type")
        if not isinstance(frame_type, str) or frame_type not in cls.SUPPORTED_TYPES:
            raise GraphQLAdapterError("graphql.subscription_frame_type_invalid")
        request_id = payload.get("id")
        if request_id is not None and not isinstance(request_id, str):
            raise GraphQLAdapterError("graphql.subscription_frame_id_invalid")
        frame_payload = payload.get("payload")
        if frame_type in {"next", "data", "error"} and frame_payload is None:
            raise GraphQLAdapterError("graphql.subscription_frame_payload_required")
        if frame_type in {"next", "data"} and not isinstance(frame_payload, Mapping):
            raise GraphQLAdapterError("graphql.subscription_next_payload_invalid")
        if frame_type == "error" and not isinstance(frame_payload, (list, tuple, Mapping)):
            raise GraphQLAdapterError("graphql.subscription_error_payload_invalid")
        return GraphQLSubscriptionFrame(
            type=frame_type,
            request_id=request_id,
            payload=frame_payload,
        )


class GraphQLProtocolAdapter:
    def build_operation(
        self,
        *,
        endpoint: str,
        query: str,
        session_id: str,
        operation_name: str | None = None,
        variables: Mapping[str, object] | None = None,
        extensions: Mapping[str, object] | None = None,
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
            "extensions": dict(extensions or {}),
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

    def build_subscription(
        self,
        *,
        endpoint: str,
        query: str,
        session_id: str,
        operation_name: str | None = None,
        variables: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        subprotocol: str = "graphql-transport-ws",
    ) -> GraphQLSubscriptionRequest:
        self._validate_subscription_endpoint(endpoint)
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
        if operation_ast.operation.value != "subscription":
            raise GraphQLAdapterError("graphql.subscription_required")
        normalized_protocol = subprotocol.strip().lower() if isinstance(subprotocol, str) else ""
        if normalized_protocol not in {"graphql-transport-ws", "graphql-ws"}:
            raise GraphQLAdapterError("graphql.subscription_protocol_invalid")
        websocket_endpoint = endpoint.strip()
        if websocket_endpoint.startswith("https://"):
            websocket_endpoint = "wss://" + websocket_endpoint[len("https://") :]
        elif websocket_endpoint.startswith("http://"):
            websocket_endpoint = "ws://" + websocket_endpoint[len("http://") :]
        request_headers = {str(key): str(value) for key, value in (headers or {}).items()}
        return GraphQLSubscriptionRequest(
            endpoint=websocket_endpoint,
            query=query,
            session_id=session_id,
            operation_name=operation_name,
            variables=dict(variables or {}),
            headers=request_headers,
            subprotocol=normalized_protocol,
        )

    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            return
        if not parsed.scheme and not parsed.netloc and endpoint.strip():
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise GraphQLAdapterError("graphql.endpoint_invalid")

    @staticmethod
    def _validate_subscription_endpoint(endpoint: str) -> None:
        """允许 HTTP(S) 自动转换，也允许调用方直接提供 WS(S) 地址。"""
        parsed = urlsplit(endpoint)
        if parsed.scheme in {"http", "https", "ws", "wss"} and parsed.hostname:
            return
        if not parsed.scheme and not parsed.netloc and endpoint.strip():
            return
        raise GraphQLAdapterError("graphql.endpoint_invalid")

    @staticmethod
    def _operation_count(document: DocumentNode) -> int:
        return sum(1 for definition in document.definitions if definition.kind == "operation_definition")
