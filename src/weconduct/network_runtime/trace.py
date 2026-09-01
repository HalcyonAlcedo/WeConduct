from __future__ import annotations

from base64 import b64encode
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from threading import RLock
from time import monotonic
from typing import Any
from uuid import uuid4

from .resources import ResponseBodyRef


# 长连接消息默认完整保留；超过该阈值后转为会话临时正文资源，避免
# Debug 快照和进程内 Trace 因单条洪峰消息膨胀。
TRACE_MESSAGE_BODY_THRESHOLD_BYTES = 256 * 1024


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _header_value(headers: Mapping[str, Any] | None, name: str) -> str | None:
    if headers is None:
        return None
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered and value is not None:
            return str(value)
    return None


def _is_textual_content_type(headers: Mapping[str, Any] | None) -> bool:
    content_type = _header_value(headers, "content-type")
    if not content_type:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return (
        media_type.startswith("text/")
        or media_type in {"application/json", "application/xml", "application/graphql"}
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return {"encoding": "base64", "value": b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, memoryview):
        return {"encoding": "base64", "value": b64encode(value.tobytes()).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, set):
        return [_json_safe_value(item) for item in sorted(value, key=repr)]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _body_payload(value: Any, headers: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, ResponseBodyRef):
        return value.to_debug_descriptor()
    if isinstance(value, bytes):
        if _is_textual_content_type(headers):
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                return {
                    "encoding": "text",
                    "value": text,
                    "text": text,
                }
        return {
            "encoding": "base64",
            "value": b64encode(value).decode("ascii"),
            "text": None,
        }
    if isinstance(value, bytearray):
        return _body_payload(bytes(value), headers)
    if isinstance(value, memoryview):
        return _body_payload(value.tobytes(), headers)
    if isinstance(value, str):
        return {
            "encoding": "text",
            "value": value,
            "text": value,
        }
    return {
        "encoding": "json",
        "value": _json_safe_value(value),
        "text": None,
    }


def body_payload_from_bytes(
    value: bytes,
    headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """将按需读取的正文转换为与 Trace 记录一致的 Debug 载荷。"""
    payload = _body_payload(value, headers)
    if payload is None:  # pragma: no cover - bytes 输入永远不会返回 None
        raise ValueError("network body payload is empty")
    return payload


def serialize_trace_message_payload(value: Any) -> tuple[bytes, str | None]:
    """把长连接消息编码为可落盘正文，并返回推断的媒体类型。"""
    if isinstance(value, bytes):
        return value, "application/octet-stream"
    if isinstance(value, bytearray):
        return bytes(value), "application/octet-stream"
    if isinstance(value, memoryview):
        return value.tobytes(), "application/octet-stream"
    if isinstance(value, str):
        return value.encode("utf-8"), "text/plain; charset=utf-8"
    return (
        json.dumps(
            _json_safe_value(value),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        "application/json",
    )


def _body_size_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, bytearray):
        return len(value)
    if isinstance(value, memoryview):
        return value.nbytes
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    payload = _body_payload(value)
    if payload is None:
        return None
    text = payload.get("value")
    if isinstance(text, str):
        return len(text.encode("utf-8"))
    return len(str(text).encode("utf-8"))


def _record_copy(value: Any) -> Any:
    return deepcopy(value)


@dataclass
class _TraceState:
    trace_id: str
    debug_session_id: str
    runtime_session_id: str
    node_id: str | None
    operation_id: str | None
    started_at: str
    started_monotonic: float
    ended_at: str | None = None
    duration_ms: float | None = None
    status: str = "running"
    error_code: str | None = None
    debug_event_index: int | None = None
    operation: dict[str, Any] = field(default_factory=dict)
    connections: dict[str, dict[str, Any]] = field(default_factory=dict)
    connection_order: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


class NetworkTraceRecorder:
    def __init__(self) -> None:
        self._lock = RLock()
        self._traces: dict[str, _TraceState] = {}
        self._sequence_id = 0

    def start_operation(
        self,
        *,
        trace_id: str | None,
        debug_session_id: str,
        runtime_session_id: str,
        node_id: str | None,
        operation_id: str,
        method: str,
        url: str,
        protocol: str | None = None,
        request_headers: Mapping[str, Any] | None = None,
        request_query: Mapping[str, Any] | None = None,
        request_body: Any = None,
        proxy: Any = None,
        tls: Any = None,
        redirects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
        retry_attempt: int = 0,
        connection_id: str | None = None,
        connection_epoch: int | None = None,
        debug_event_index: int | None = None,
    ) -> dict[str, Any]:
        normalized_trace_id = trace_id or f"trace-{uuid4().hex}"
        started_at = _utc_now_iso()
        payload = {
            "trace_id": normalized_trace_id,
            "debug_session_id": debug_session_id,
            "runtime_session_id": runtime_session_id,
            "node_id": node_id,
            "operation_id": operation_id,
            "started_at": started_at,
            "ended_at": None,
            "duration_ms": None,
            "status": "running",
            "error_code": None,
            "connection_id": connection_id,
            "connection_epoch": connection_epoch,
            "debug_event_index": debug_event_index,
            "method": method,
            "url": url,
            "protocol": protocol,
            "request_headers": _json_safe_value(request_headers or {}),
            "request_query": _json_safe_value(request_query or {}),
            "request_body": _body_payload(request_body, request_headers),
            "response_status": None,
            "response_headers": None,
            "response_body": None,
            "retry_attempt": retry_attempt,
            "proxy": _json_safe_value(proxy) if proxy is not None else None,
            "tls": _json_safe_value(tls) if tls is not None else None,
            "final_url": None,
            "redirects": _json_safe_value(list(redirects or ()))
            if redirects is not None
            else [],
        }
        with self._lock:
            self._traces[normalized_trace_id] = _TraceState(
                trace_id=normalized_trace_id,
                debug_session_id=debug_session_id,
                runtime_session_id=runtime_session_id,
                node_id=node_id,
                operation_id=operation_id,
                started_at=started_at,
                started_monotonic=monotonic(),
                debug_event_index=debug_event_index,
                operation=payload,
            )
        return _record_copy(payload)

    def complete_operation(
        self,
        *,
        trace_id: str,
        status: str,
        response_status: int | None = None,
        response_headers: Mapping[str, Any] | None = None,
        request_body: Any = None,
        response_body: Any = None,
        error_code: str | None = None,
        debug_event_index: int | None = None,
        final_url: str | None = None,
        redirects: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
        retry_attempt: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_trace(trace_id)
            state.ended_at = _utc_now_iso()
            state.duration_ms = round((monotonic() - state.started_monotonic) * 1000, 3)
            state.status = status
            state.error_code = error_code
            if debug_event_index is not None:
                state.debug_event_index = debug_event_index
            state.operation.update(
                {
                    "ended_at": state.ended_at,
                    "duration_ms": state.duration_ms,
                    "status": status,
                    "error_code": error_code,
                    "response_status": response_status,
                    "response_headers": _json_safe_value(response_headers or {})
                    if response_headers is not None
                    else None,
                    "request_body": (
                        _body_payload(request_body, state.operation.get("request_headers"))
                        if request_body is not None
                        else state.operation.get("request_body")
                    ),
                    "response_body": _body_payload(response_body, response_headers),
                    "debug_event_index": state.debug_event_index,
                }
            )
            if final_url is not None:
                state.operation["final_url"] = final_url
            if redirects is not None:
                state.operation["redirects"] = _json_safe_value(list(redirects))
            if retry_attempt is not None:
                state.operation["retry_attempt"] = retry_attempt
            return _record_copy(state.operation)

    def update_connection(
        self,
        *,
        trace_id: str,
        debug_session_id: str,
        runtime_session_id: str,
        node_id: str | None,
        operation_id: str | None,
        connection_id: str,
        connection_epoch: int | None = None,
        protocol: str | None = None,
        subprotocol: str | None = None,
        connection_state: str | None = None,
        message_count: int | None = None,
        last_event_id: str | None = None,
        reconnect_count: int | None = None,
        reconnect_reason: str | None = None,
        queue_depth: int | None = None,
        dropped_count: int | None = None,
        drop_events: list[Mapping[str, Any]] | None = None,
        activation_queue_depth: int | None = None,
        activation_dropped_count: int | None = None,
        activation_drop_events: list[Mapping[str, Any]] | None = None,
        backpressure_policy: str | None = None,
        close_reason: str | None = None,
        debug_event_index: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_trace(trace_id)
            previous = state.connections.get(connection_id, {})
            record = {
                "trace_id": trace_id,
                "debug_session_id": debug_session_id,
                "runtime_session_id": runtime_session_id,
                "node_id": node_id if node_id is not None else state.node_id,
                "operation_id": (
                    operation_id if operation_id is not None else state.operation_id
                ),
                "connection_id": connection_id,
            }
            optional_values = {
                "connection_epoch": connection_epoch,
                "protocol": protocol,
                "subprotocol": subprotocol,
                "connection_state": connection_state,
                "message_count": message_count,
                "last_event_id": last_event_id,
                "reconnect_count": reconnect_count,
                "reconnect_reason": reconnect_reason,
                "queue_depth": queue_depth,
                "dropped_count": dropped_count,
                "drop_events": drop_events,
                "activation_queue_depth": activation_queue_depth,
                "activation_dropped_count": activation_dropped_count,
                "activation_drop_events": activation_drop_events,
                "backpressure_policy": backpressure_policy,
                "close_reason": close_reason,
                "debug_event_index": debug_event_index,
            }
            list_fields = {"drop_events", "activation_drop_events"}
            for field_name, value in optional_values.items():
                if value is None:
                    if field_name in previous:
                        record[field_name] = _record_copy(previous[field_name])
                    elif field_name in list_fields:
                        record[field_name] = []
                    else:
                        record[field_name] = None
                elif field_name in list_fields:
                    record[field_name] = _record_copy(value)
                else:
                    record[field_name] = value
            state.debug_session_id = debug_session_id
            state.runtime_session_id = runtime_session_id
            state.node_id = record["node_id"]
            state.operation_id = record["operation_id"]
            state.connections[connection_id] = record
            if connection_id not in state.connection_order:
                state.connection_order.append(connection_id)
        return _record_copy(record)

    def append_message(
        self,
        *,
        trace_id: str,
        debug_session_id: str,
        runtime_session_id: str,
        node_id: str | None,
        operation_id: str | None,
        connection_id: str | None,
        event_kind: str,
        payload: Any,
        sequence_id: int | None = None,
        connection_epoch: int | None = None,
        debug_event_index: int | None = None,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if sequence_id is None:
                self._sequence_id += 1
                resolved_sequence_id = self._sequence_id
            else:
                if isinstance(sequence_id, int) and not isinstance(sequence_id, bool):
                    self._sequence_id = max(self._sequence_id, sequence_id)
                resolved_sequence_id = sequence_id
            payload_value = (
                payload.to_debug_descriptor()
                if isinstance(payload, ResponseBodyRef)
                else _json_safe_value(payload)
            )
            record = {
                "trace_id": trace_id,
                "debug_session_id": debug_session_id,
                "runtime_session_id": runtime_session_id,
                "node_id": node_id,
                "operation_id": operation_id,
                "connection_id": connection_id,
                "event_kind": event_kind,
                "recorded_at": _utc_now_iso(),
                "payload": payload_value,
                "size_bytes": (
                    size_bytes
                    if size_bytes is not None
                    else payload.size_bytes
                    if isinstance(payload, ResponseBodyRef)
                    else _body_size_bytes(payload)
                ),
                "sequence_id": resolved_sequence_id,
                "connection_epoch": connection_epoch,
                "debug_event_index": debug_event_index,
            }
            state = self._require_trace(trace_id)
            state.debug_session_id = debug_session_id
            state.runtime_session_id = runtime_session_id
            state.node_id = node_id
            state.operation_id = operation_id
            state.messages.append(record)
            return _record_copy(record)

    def list_traces(
        self,
        *,
        debug_session_id: str | None = None,
        runtime_session_id: str | None = None,
        protocol: str | None = None,
        status: str | None = None,
        node_id: str | None = None,
        operation_id: str | None = None,
        connection_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items: list[dict[str, Any]] = []
            for state in self._traces.values():
                if trace_id is not None and state.trace_id != trace_id:
                    continue
                if debug_session_id is not None and state.debug_session_id != debug_session_id:
                    continue
                if runtime_session_id is not None and state.runtime_session_id != runtime_session_id:
                    continue
                if node_id is not None and state.node_id != node_id:
                    continue
                if operation_id is not None and state.operation_id != operation_id:
                    continue
                if self._match_operation(state.operation, protocol, status):
                    items.append(_record_copy(state.operation))
                for connection in state.connection_order:
                    record = state.connections[connection]
                    if self._match_connection(record, protocol, status, connection_id):
                        items.append(_record_copy(record))
                for message in state.messages:
                    if connection_id is not None and message.get("connection_id") != connection_id:
                        continue
                    if status is not None:
                        continue
                    if protocol is not None:
                        continue
                    items.append(_record_copy(message))
            return items

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._require_trace(trace_id)
            return {
                "trace_id": state.trace_id,
                "debug_session_id": state.debug_session_id,
                "runtime_session_id": state.runtime_session_id,
                "node_id": state.node_id,
                "operation_id": state.operation_id,
                "started_at": state.started_at,
                "ended_at": state.ended_at,
                "duration_ms": state.duration_ms,
                "status": state.status,
                "error_code": state.error_code,
                "debug_event_index": state.debug_event_index,
                "operation": _record_copy(state.operation),
                "connections": [_record_copy(state.connections[key]) for key in state.connection_order],
                "messages": [_record_copy(message) for message in state.messages],
            }

    def summary(
        self,
        *,
        debug_session_id: str | None = None,
        runtime_session_id: str | None = None,
        protocol: str | None = None,
        status: str | None = None,
        node_id: str | None = None,
        operation_id: str | None = None,
        connection_id: str | None = None,
    ) -> dict[str, Any]:
        items = self.list_traces(
            debug_session_id=debug_session_id,
            runtime_session_id=runtime_session_id,
            protocol=protocol,
            status=status,
            node_id=node_id,
            operation_id=operation_id,
            connection_id=connection_id,
        )
        operations = [item for item in items if "method" in item]
        connections = [
            item
            for item in items
            if "connection_id" in item and "connection_state" in item
        ]
        recent_errors = [
            {
                "trace_id": item["trace_id"],
                "operation_id": item["operation_id"],
                "status": item.get("status"),
                "error_code": item.get("error_code"),
                "ended_at": item.get("ended_at"),
            }
            for item in operations
            if item.get("status") in {"failed", "cancelled"} or item.get("error_code")
        ]
        queue_events: list[dict[str, Any]] = []
        for connection in connections:
            raw_events = connection.get("drop_events")
            for event_list in (
                raw_events,
                connection.get("activation_drop_events"),
            ):
                if not isinstance(event_list, list):
                    continue
                for raw_event in event_list:
                    if not isinstance(raw_event, Mapping):
                        continue
                    event = dict(raw_event)
                    event.setdefault("trace_id", connection.get("trace_id"))
                    queue_events.append(event)
        return {
            "total_operations": len(operations),
            "successful_operations": sum(1 for item in operations if item.get("status") == "succeeded"),
            "failed_operations": sum(1 for item in operations if item.get("status") == "failed"),
            "cancelled_operations": sum(1 for item in operations if item.get("status") == "cancelled"),
            "active_connections": sum(
                1
                for item in connections
                if str(item.get("connection_state") or "").lower() not in {"closed", "failed", "disconnected"}
            ),
            "queue_depth": sum(int(item.get("queue_depth") or 0) for item in connections),
            "reconnect_count": sum(int(item.get("reconnect_count") or 0) for item in connections),
            "dropped_count": sum(int(item.get("dropped_count") or 0) for item in connections),
            "activation_queue_depth": sum(
                int(item.get("activation_queue_depth") or 0) for item in connections
            ),
            "activation_dropped_count": sum(
                int(item.get("activation_dropped_count") or 0) for item in connections
            ),
            "queue_events": queue_events[-20:],
            "recent_errors": recent_errors[-5:],
        }

    def _require_trace(self, trace_id: str) -> _TraceState:
        state = self._traces.get(trace_id)
        if state is None:
            raise KeyError(f"unknown trace_id: {trace_id}")
        return state

    def _match_operation(
        self,
        record: dict[str, Any],
        protocol: str | None,
        status: str | None,
    ) -> bool:
        if protocol is not None and record.get("protocol") != protocol:
            return False
        if status is None:
            return True
        return record.get("status") == status

    def _match_connection(
        self,
        record: dict[str, Any],
        protocol: str | None,
        status: str | None,
        connection_id: str | None,
    ) -> bool:
        if connection_id is not None and record.get("connection_id") != connection_id:
            return False
        if protocol is not None and record.get("protocol") != protocol:
            return False
        if status is None:
            return True
        return record.get("connection_state") == status
