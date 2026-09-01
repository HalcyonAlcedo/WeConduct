from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import random
from threading import Event, RLock, Thread
from time import monotonic, time
from typing import Callable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from .access_policy import NetworkAccessPolicy
from .authentication import apply_static_auth
from .errors import build_network_error
from .http_adapter import HttpxAdapter
from .long_connection import SSEClientHandle, WebSocketClientHandle
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .oauth import OAuthService, OAuthTokenState
from .proxy import ProxyResolver
from .resources import ResponseBodyRef
from .tls import TlsResolver, build_ssl_context
from .trace import NetworkTraceRecorder
from .queue import (
    QueueBackpressureError,
    QueueCancelledError,
    QueueClosedError,
    SequenceAllocator,
    SessionActivationQueue,
)


def _normalize_retry_policy(value: object) -> dict[str, object]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("retry_policy must be an object")

    def positive_int(name: str, default: int) -> int:
        raw = value.get(name, default)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ValueError(f"{name} must be an integer greater than zero")
        return raw

    def non_negative_number(name: str, default: float | None) -> float | None:
        raw = value.get(name, default)
        if raw is None:
            return None
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < 0:
            raise ValueError(f"{name} must be a non-negative number")
        return float(raw)

    status_codes_value = value.get("retry_status_codes", ())
    if not isinstance(status_codes_value, (list, tuple, set)) or any(
        not isinstance(status_code, int) or isinstance(status_code, bool)
        for status_code in status_codes_value
    ):
        raise ValueError("retry_status_codes must be a list of integer status codes")
    jitter_ratio = non_negative_number("jitter_ratio", 0.0)
    assert jitter_ratio is not None
    if jitter_ratio > 1:
        raise ValueError("jitter_ratio must not exceed 1")
    respect_retry_after = value.get("respect_retry_after", True)
    if not isinstance(respect_retry_after, bool):
        raise ValueError("respect_retry_after must be a boolean")
    allow_non_idempotent = value.get("allow_non_idempotent", False)
    if not isinstance(allow_non_idempotent, bool):
        raise ValueError("allow_non_idempotent must be a boolean")
    retry_transport_errors = value.get("retry_transport_errors", True)
    if not isinstance(retry_transport_errors, bool):
        raise ValueError("retry_transport_errors must be a boolean")
    initial_delay_seconds = non_negative_number("initial_delay_seconds", 0.25)
    max_delay_seconds = non_negative_number("max_delay_seconds", 30.0)
    max_total_seconds = non_negative_number("max_total_seconds", None)
    assert initial_delay_seconds is not None
    assert max_delay_seconds is not None
    if max_delay_seconds < initial_delay_seconds:
        raise ValueError("max_delay_seconds must be greater than or equal to initial_delay_seconds")
    return {
        "max_attempts": positive_int("max_attempts", 1),
        "retry_status_codes": frozenset(status_codes_value),
        "retry_transport_errors": retry_transport_errors,
        "initial_delay_seconds": initial_delay_seconds,
        "max_delay_seconds": max_delay_seconds,
        "max_total_seconds": max_total_seconds,
        "jitter_ratio": jitter_ratio,
        "respect_retry_after": respect_retry_after,
        "allow_non_idempotent": allow_non_idempotent,
    }


def _retry_is_allowed(
    operation: NetworkOperation,
    snapshot: NetworkContextSnapshot,
    policy: Mapping[str, object],
) -> bool:
    if policy["max_attempts"] == 1 or operation.upload_stream is not None:
        return False
    method = operation.method.upper()
    if method in {"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "TRACE"}:
        return True
    effective_headers = {str(name).lower() for name in (*snapshot.headers, *operation.headers)}
    return bool(policy["allow_non_idempotent"]) or "idempotency-key" in effective_headers


def _is_retryable_result(result: NetworkResult, policy: Mapping[str, object]) -> bool:
    if result.status != "succeeded":
        if result.transport_error in {"network.cancelled", "network.access_denied"}:
            return False
        return bool(policy["retry_transport_errors"])
    retry_status_codes = policy["retry_status_codes"]
    return isinstance(retry_status_codes, frozenset) and result.status_code in retry_status_codes


def _with_retry_attempt(
    result: NetworkResult,
    *,
    operation: NetworkOperation,
    snapshot: NetworkContextSnapshot,
    retry_attempt: int,
) -> NetworkResult:
    if result.status != "failed":
        return replace(result, retry_attempt=retry_attempt)
    error = result.error or build_network_error(
        result.transport_error or "network.transport_failed",
        operation=operation,
        snapshot=snapshot,
    )
    error = error.with_retry_attempt(retry_attempt)
    return replace(
        result,
        transport_error=error.error_code,
        error=error,
        retry_attempt=retry_attempt,
    )


def _retry_delay_seconds(
    result: NetworkResult,
    policy: Mapping[str, object],
    *,
    attempt_index: int,
) -> float:
    initial_delay = float(policy["initial_delay_seconds"])
    max_delay = float(policy["max_delay_seconds"])
    delay = min(max_delay, initial_delay * (2**attempt_index))
    if bool(policy["respect_retry_after"]):
        retry_after = _parse_retry_after(result.headers)
        if retry_after is not None:
            delay = min(max_delay, retry_after)
    jitter_ratio = float(policy["jitter_ratio"])
    if jitter_ratio:
        delay *= random.uniform(1 - jitter_ratio, 1 + jitter_ratio)
    return delay


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw_value = next(
        (
            value
            for name, value in headers.items()
            if isinstance(name, str) and name.lower() == "retry-after" and isinstance(value, str)
        ),
        None,
    )
    if raw_value is None:
        return None
    try:
        return max(0.0, float(raw_value.strip()))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())


def _metadata_status_code(metadata: Mapping[str, object]) -> int | None:
    value = metadata.get("status_code")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _metadata_headers(metadata: Mapping[str, object]) -> Mapping[str, object] | None:
    value = metadata.get("headers")
    return value if isinstance(value, Mapping) else None


def _connection_error_code(error: BaseException, fallback: str) -> str:
    value = getattr(error, "error_code", None)
    if isinstance(value, str) and value.strip():
        return value
    text = str(error).strip()
    return text if text.startswith("network.") else fallback


def _connection_security_audit_events(
    snapshot: NetworkContextSnapshot,
    url: str,
) -> tuple[str, ...]:
    """返回降级连接配置对应的审计事件，不包含地址或凭据。"""
    events: list[str] = []
    if urlsplit(url).scheme.lower() == "ws":
        events.append("network.websocket_plaintext")
    proxy = snapshot.proxy if isinstance(snapshot.proxy, Mapping) else {}
    mode = proxy.get("mode") if isinstance(proxy, Mapping) else None
    normalized_mode = mode.strip().lower() if isinstance(mode, str) else ""
    proxy_url = proxy.get("url") if isinstance(proxy, Mapping) else None
    proxy_scheme = urlsplit(proxy_url).scheme.lower() if isinstance(proxy_url, str) else ""
    if normalized_mode == "socks5h" or proxy_scheme == "socks5h":
        events.append("network.proxy_remote_dns")
    elif normalized_mode == "pac":
        events.append("network.proxy_pac")
    elif normalized_mode in {"wpad", "windows_system"}:
        events.append("network.proxy_auto_discovery")
    return tuple(events)


class NetworkRuntimeService:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
        sensitive_values: object | None = None,
        audit_event_sink: Callable[[str, dict[str, object]], None] | None = None,
        trace_recorder: NetworkTraceRecorder | None = None,
        debug_event_index_supplier: Callable[[], int | None] | None = None,
        allow_insecure_tls: bool = True,
    ) -> None:
        if not isinstance(allow_insecure_tls, bool):
            raise ValueError("network.allow_insecure_tls_invalid")
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._tls_resolver = TlsResolver(allow_insecure=allow_insecure_tls)
        self._adapter = HttpxAdapter(
            response_root_directory=response_root_directory,
            access_policy=self._access_policy,
            transport=transport,
            allow_insecure_tls=allow_insecure_tls,
        )
        self._client = self._adapter._client
        self._loop = asyncio.new_event_loop()
        self._ready = Event()
        self._closed = False
        self._lock = RLock()
        self._active_tasks: dict[str, set[asyncio.Task[NetworkResult]]] = {}
        self._long_connections: dict[str, set[object]] = {}
        self._sequence_allocators: dict[str, SequenceAllocator] = {}
        self._session_activation_queues: dict[str, SessionActivationQueue] = {}
        self._connection_activation_keys: dict[int, tuple[str, str]] = {}
        self._connection_trace_metadata: dict[int, dict[str, object]] = {}
        self._pending_activation_trace_records: dict[tuple[str, str], list[dict[str, object]]] = {}
        self._sensitive_values = sensitive_values
        self._audit_event_sink = audit_event_sink
        self._trace_recorder = trace_recorder
        self._debug_event_index_supplier = debug_event_index_supplier
        self._oauth_service = (
            OAuthService(
                sensitive_values=sensitive_values,  # type: ignore[arg-type]
                transport=transport,  # type: ignore[arg-type]
                access_policy=self._access_policy,
                allow_insecure_tls=allow_insecure_tls,
            )
            if sensitive_values is not None
            else None
        )
        self._oauth_tokens: dict[tuple[str, str | None], OAuthTokenState] = {}
        self._oauth_tokens_lock = RLock()
        self._thread = Thread(target=self._run_loop, daemon=True, name="weconduct-network")
        self._thread.start()
        self._ready.wait(timeout=1)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def submit(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> Future[NetworkResult]:
        with self._lock:
            if self._closed:
                raise RuntimeError("network runtime service is closed")
            future: Future[NetworkResult] = Future()
            trace_id: str | None = None
            if self._trace_recorder is not None:
                try:
                    trace_request_headers = self._resolve_debug_trace_value(
                        {**dict(snapshot.headers), **dict(operation.headers)}
                    )
                    trace_request_query = self._resolve_debug_trace_value(
                        {**dict(snapshot.query), **dict(operation.query)}
                    )
                    trace_request_body = self._resolve_debug_trace_value(operation.content)
                    captured_request_body = self._adapter.capture_trace_body(
                        operation.session_id,
                        trace_request_body,
                        content_type=self._header_value_for_trace(
                            {**dict(snapshot.headers), **dict(operation.headers)},
                            "content-type",
                        ),
                    )
                    trace = self._trace_recorder.start_operation(
                        trace_id=None,
                        debug_session_id=operation.session_id,
                        runtime_session_id=operation.session_id,
                        node_id=operation.node_id,
                        operation_id=operation.operation_id,
                        method=operation.method,
                        url=operation.url,
                        protocol="http",
                        request_headers=trace_request_headers,
                        request_query=trace_request_query,
                        request_body=(
                            captured_request_body
                            if captured_request_body is not None
                            else trace_request_body
                        ),
                        proxy=self._resolve_debug_trace_value(snapshot.proxy),
                        tls=self._resolve_debug_trace_value(snapshot.tls),
                        debug_event_index=self._current_debug_event_index(),
                    )
                    trace_id = trace.get("trace_id")
                except Exception:
                    # Tracing must never prevent the network operation itself.
                    trace_id = None
            self._loop.call_soon_threadsafe(
                self._schedule_operation,
                operation,
                snapshot,
                future,
                trace_id,
            )
        return future

    @staticmethod
    def _header_value_for_trace(headers: Mapping[str, object], name: str) -> str | None:
        lowered = name.lower()
        for key, value in headers.items():
            if str(key).lower() == lowered and value is not None:
                return str(value)
        return None

    @staticmethod
    def _normalize_debug_event_index(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    def _current_debug_event_index(self) -> int | None:
        supplier = self._debug_event_index_supplier
        if not callable(supplier):
            return None
        try:
            return self._normalize_debug_event_index(supplier())
        except Exception:
            # Debug 事件关联是观测旁路，供应器异常不能影响网络请求。
            return None

    def _resolve_debug_trace_value(self, value: object) -> object:
        """仅为 Debug Trace 解析敏感引用；失败时保留原值，不影响网络执行。"""
        if isinstance(value, Mapping):
            return {
                key: self._resolve_debug_trace_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_debug_trace_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._resolve_debug_trace_value(item) for item in value)
        try:
            resolved = self._resolve_sensitive_text(value)
        except Exception:
            return value
        return resolved

    def cancel_session(self, session_id: str) -> None:
        self._close_session_connections(session_id)
        self._clear_session_oauth(session_id)
        self._clear_session_sequence_allocator(session_id)
        with self._lock:
            if self._closed:
                return
            self._loop.call_soon_threadsafe(self._cancel_session_on_loop, session_id)

    def close(self) -> None:
        self._close_all_connections()
        with self._oauth_tokens_lock:
            self._oauth_tokens.clear()
        with self._lock:
            self._sequence_allocators.clear()
            activation_queues = tuple(self._session_activation_queues.values())
            self._session_activation_queues.clear()
            if self._closed:
                return
            self._closed = True
            shutdown = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        for activation_queue in activation_queues:
            activation_queue.close()
        shutdown.result(timeout=1)
        with self._lock:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)

    def connect_sse(
        self,
        *,
        session_id: str,
        snapshot: NetworkContextSnapshot,
        url: str,
        node_id: str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        connection_id: str | None = None,
        timeout_seconds: float = 30.0,
        max_queue_size: int = 100,
        backpressure_policy: str = "fail_stream",
        max_reconnect_attempts: int = 0,
        reconnect_delay_seconds: float = 0.5,
        reconnect_max_delay_seconds: float = 30.0,
    ) -> tuple[SSEClientHandle, dict[str, object]]:
        self._require_open()
        operation = NetworkOperation(
            operation_id="network.sse_connect",
            session_id=session_id,
            method="GET",
            url=url,
            node_id=node_id,
        )
        connection_key = self._connection_key("sse", connection_id)
        effective_snapshot = self._resolve_oauth_snapshot_sync(
            operation=operation,
            snapshot=snapshot,
            timeout_seconds=timeout_seconds,
        )
        proxy = self._resolve_proxy(effective_snapshot, url)
        resolved_tls = self._tls_resolver.resolve(
            effective_snapshot.tls if isinstance(effective_snapshot.tls, dict) else {}
        )
        self._emit_network_security_events(
            operation,
            effective_snapshot,
            (*resolved_tls.audit_events, *_connection_security_audit_events(effective_snapshot, url)),
        )
        trace_id = self._start_connection_trace(
            operation=operation,
            snapshot=effective_snapshot,
            protocol="sse",
            connection_id=connection_key,
            request_headers=headers,
            request_query=params,
        )
        handle = SSEClientHandle(
            url=url,
            headers=self._effective_headers(effective_snapshot, headers),
            params={**dict(effective_snapshot.query), **(params or {})},
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            max_queue_size=max_queue_size,
            backpressure_policy=backpressure_policy,
            access_policy=self._access_policy,
            ssl_context=build_ssl_context(resolved_tls),
            certificate_pins=resolved_tls.certificate_pins,
            sequence_allocator=self._get_sequence_allocator(session_id),
            connection_id=connection_key,
            max_reconnect_attempts=max_reconnect_attempts,
            reconnect_delay_seconds=reconnect_delay_seconds,
            reconnect_max_delay_seconds=reconnect_max_delay_seconds,
            activation_sink=self._build_activation_sink(
                session_id=session_id,
                connection_key=connection_key,
                backpressure_policy=backpressure_policy,
                maxsize=max_queue_size,
            ),
        )
        try:
            metadata = handle.start(timeout_seconds=timeout_seconds)
        except BaseException as exc:
            self._complete_connection_trace(
                trace_id=trace_id,
                status="failed",
                error_code=_connection_error_code(exc, "network.sse_connect_failed"),
            )
            handle.close()
            raise
        self._complete_connection_trace(
            trace_id=trace_id,
            status="succeeded",
            response_status=_metadata_status_code(metadata),
            response_headers=_metadata_headers(metadata),
        )
        self._register_connection_trace(
            session_id=session_id,
            handle=handle,
            trace_id=trace_id,
            operation=operation,
            protocol="sse",
            connection_id=connection_key,
        )
        self._register_connection_activation(session_id, handle, connection_key)
        self._register_long_connection(session_id, handle)
        return handle, metadata

    def connect_websocket(
        self,
        *,
        session_id: str,
        snapshot: NetworkContextSnapshot,
        url: str,
        node_id: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        subprotocols: list[str] | None = None,
        connection_id: str | None = None,
        max_queue_size: int = 100,
        backpressure_policy: str = "fail_stream",
        max_reconnect_attempts: int = 0,
        reconnect_delay_seconds: float = 0.5,
        reconnect_max_delay_seconds: float = 30.0,
        trace_operation_id: str | None = None,
        trace_protocol: str | None = None,
    ) -> tuple[WebSocketClientHandle, dict[str, object]]:
        self._require_open()
        resolved_trace_operation_id = (
            trace_operation_id.strip()
            if isinstance(trace_operation_id, str) and trace_operation_id.strip()
            else "network.websocket_connect"
        )
        resolved_trace_protocol = (
            trace_protocol.strip()
            if isinstance(trace_protocol, str) and trace_protocol.strip()
            else "websocket"
        )
        operation = NetworkOperation(
            operation_id=resolved_trace_operation_id,
            session_id=session_id,
            method="GET",
            url=url,
            node_id=node_id,
        )
        connection_key = self._connection_key(resolved_trace_protocol, connection_id)
        effective_snapshot = self._resolve_oauth_snapshot_sync(
            operation=operation,
            snapshot=snapshot,
            timeout_seconds=timeout_seconds,
        )
        proxy = self._resolve_proxy(effective_snapshot, url)
        resolved_tls = self._tls_resolver.resolve(
            effective_snapshot.tls if isinstance(effective_snapshot.tls, dict) else {}
        )
        self._emit_network_security_events(
            operation,
            effective_snapshot,
            (*resolved_tls.audit_events, *_connection_security_audit_events(effective_snapshot, url)),
        )
        trace_id = self._start_connection_trace(
            operation=operation,
            snapshot=effective_snapshot,
            protocol=resolved_trace_protocol,
            connection_id=connection_key,
            request_headers=headers,
        )
        handle = WebSocketClientHandle(
            url=url,
            headers=self._effective_headers(effective_snapshot, headers),
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            max_queue_size=max_queue_size,
            backpressure_policy=backpressure_policy,
            subprotocols=subprotocols,
            access_policy=self._access_policy,
            ssl_context=build_ssl_context(resolved_tls),
            certificate_pins=resolved_tls.certificate_pins,
            sequence_allocator=self._get_sequence_allocator(session_id),
            connection_id=connection_key,
            max_reconnect_attempts=max_reconnect_attempts,
            reconnect_delay_seconds=reconnect_delay_seconds,
            reconnect_max_delay_seconds=reconnect_max_delay_seconds,
            activation_sink=self._build_activation_sink(
                session_id=session_id,
                connection_key=connection_key,
                backpressure_policy=backpressure_policy,
                maxsize=max_queue_size,
            ),
        )
        try:
            metadata = handle.start(timeout_seconds=timeout_seconds)
        except BaseException as exc:
            self._complete_connection_trace(
                trace_id=trace_id,
                status="failed",
                error_code=_connection_error_code(exc, "network.websocket_connect_failed"),
            )
            handle.close()
            raise
        self._complete_connection_trace(
            trace_id=trace_id,
            status="succeeded",
            response_status=_metadata_status_code(metadata),
            response_headers=_metadata_headers(metadata),
        )
        self._register_connection_trace(
            session_id=session_id,
            handle=handle,
            trace_id=trace_id,
            operation=operation,
            protocol=resolved_trace_protocol,
            connection_id=connection_key,
            subprotocol=(subprotocols[0] if subprotocols else None),
        )
        self._register_connection_activation(session_id, handle, connection_key)
        self._register_long_connection(session_id, handle)
        return handle, metadata

    def release_connection(self, session_id: str, handle: object) -> None:
        activation_key = self._connection_activation_key(handle)
        if activation_key is not None:
            self._discard_connection_activation(*activation_key)
        self._record_connection_closed(session_id, handle, close_reason="released")
        with self._lock:
            connections = self._long_connections.get(session_id)
            if connections is None:
                return
            connections.discard(handle)
            if not connections:
                self._long_connections.pop(session_id, None)

    def record_connection_message(
        self,
        *,
        session_id: str,
        handle: object,
        connection_id: str | None,
        event_kind: str,
        payload: object,
        debug_event_index: int | None = None,
        sequence_id: int | None = None,
        connection_epoch: int | None = None,
    ) -> None:
        """记录长连接消息；记录失败不得影响网络节点结果。"""
        recorder = self._trace_recorder
        if recorder is None:
            return
        with self._lock:
            metadata = self._connection_trace_metadata.get(id(handle))
            if metadata is None or metadata.get("session_id") != session_id:
                return
        queue_metrics = self._connection_queue_metrics(handle)
        activation_metrics = self._session_activation_queue_metrics(session_id)
        self._record_connection_message_from_metadata(
            recorder=recorder,
            metadata=metadata,
            session_id=session_id,
            connection_id=connection_id,
            event_kind=event_kind,
            payload=payload,
            debug_event_index=debug_event_index,
            sequence_id=sequence_id,
            connection_epoch=connection_epoch,
            queue_metrics=queue_metrics,
            activation_metrics=activation_metrics,
        )

    def record_connection_activation(
        self,
        *,
        session_id: str,
        connection_id: str,
        activation: Mapping[str, object],
    ) -> None:
        """记录接收线程自动产生的激活消息，不依赖节点先调用 receive。"""
        recorder = self._trace_recorder
        if recorder is None or not isinstance(activation, Mapping):
            return
        with self._lock:
            metadata = next(
                (
                    item
                    for item in self._connection_trace_metadata.values()
                    if item.get("session_id") == session_id
                    and item.get("connection_id") == connection_id
                ),
                None,
            )
            if metadata is None:
                pending = self._pending_activation_trace_records.setdefault(
                    (session_id, connection_id),
                    [],
                )
                if len(pending) < 256:
                    pending.append(dict(activation))
                return
            handles = tuple(self._long_connections.get(session_id, ()))
            handle = next(
                (
                    candidate
                    for candidate in handles
                    if self._connection_trace_metadata.get(id(candidate)) is metadata
                ),
                None,
            )
        if metadata is None:
            return
        activation_payload = activation.get("payload")
        message = (
            activation_payload.get("message")
            if isinstance(activation_payload, Mapping)
            else None
        )
        if not isinstance(message, Mapping):
            return
        raw_payload = message.get("payload")
        event_kind = (
            activation_payload.get("event_kind")
            if isinstance(activation_payload, Mapping)
            else None
        )
        if not isinstance(event_kind, str) or not event_kind:
            event_kind = "network.message"
        normalized_payload = self._normalize_connection_message_payload(raw_payload)
        sequence_id = message.get("sequence_id")
        if not isinstance(sequence_id, int) or isinstance(sequence_id, bool):
            sequence_id = activation.get("sequence_id")
        if not isinstance(sequence_id, int) or isinstance(sequence_id, bool):
            sequence_id = None
        connection_epoch = message.get("connection_epoch")
        if not isinstance(connection_epoch, int) or isinstance(connection_epoch, bool):
            connection_epoch = activation.get("connection_epoch")
        if not isinstance(connection_epoch, int) or isinstance(connection_epoch, bool):
            connection_epoch = None
        self._record_connection_message_from_metadata(
            recorder=recorder,
            metadata=metadata,
            session_id=session_id,
            connection_id=connection_id,
            event_kind=event_kind,
            payload=normalized_payload,
            sequence_id=sequence_id,
            connection_epoch=connection_epoch,
            queue_metrics=self._connection_queue_metrics(handle) if handle is not None else {},
            activation_metrics=self._session_activation_queue_metrics(session_id),
        )

    @staticmethod
    def _normalize_connection_message_payload(payload: object) -> object:
        if all(hasattr(payload, name) for name in ("event_id", "event_type", "data", "retry_ms")):
            return {
                "event_id": getattr(payload, "event_id"),
                "event_type": getattr(payload, "event_type"),
                "data": getattr(payload, "data"),
                "retry_ms": getattr(payload, "retry_ms"),
            }
        return payload

    def _record_connection_message_from_metadata(
        self,
        *,
        recorder: NetworkTraceRecorder,
        metadata: dict[str, object],
        session_id: str,
        connection_id: str | None,
        event_kind: str,
        payload: object,
        debug_event_index: int | None = None,
        sequence_id: int | None = None,
        connection_epoch: int | None = None,
        queue_metrics: Mapping[str, object] | None = None,
        activation_metrics: Mapping[str, object] | None = None,
    ) -> None:
        queue_metrics = dict(queue_metrics or {})
        activation_metrics = dict(activation_metrics or {})
        resolved_debug_event_index = self._normalize_debug_event_index(debug_event_index)
        with self._lock:
            if queue_metrics:
                metadata.update(queue_metrics)
            if activation_metrics:
                metadata.update(activation_metrics)
            if resolved_debug_event_index is None:
                resolved_debug_event_index = self._normalize_debug_event_index(
                    metadata.get("debug_event_index")
                )
            if resolved_debug_event_index is None:
                resolved_debug_event_index = self._current_debug_event_index()
            if resolved_debug_event_index is not None:
                metadata["debug_event_index"] = resolved_debug_event_index
            if isinstance(sequence_id, int) and not isinstance(sequence_id, bool):
                recorded_sequences = metadata.setdefault("_recorded_sequence_ids", set())
                if not isinstance(recorded_sequences, set):
                    recorded_sequences = set()
                    metadata["_recorded_sequence_ids"] = recorded_sequences
                if sequence_id in recorded_sequences:
                    return
                recorded_sequences.add(sequence_id)
            message_count = int(metadata.get("message_count", 0)) + 1
            metadata["message_count"] = message_count
        trace_id = metadata.get("trace_id")
        if not isinstance(trace_id, str):
            return
        resolved_connection_id = connection_id or metadata.get("connection_id") or trace_id
        if not isinstance(resolved_connection_id, str):
            return
        resolved_connection_epoch = (
            connection_epoch
            if isinstance(connection_epoch, int)
            else queue_metrics.get("connection_epoch")
            if isinstance(queue_metrics.get("connection_epoch"), int)
            else metadata.get("connection_epoch")
            if isinstance(metadata.get("connection_epoch"), int)
            else None
        )
        resolved_reconnect_count = (
            queue_metrics.get("reconnect_count")
            if isinstance(queue_metrics.get("reconnect_count"), int)
            else metadata.get("reconnect_count")
            if isinstance(metadata.get("reconnect_count"), int)
            else None
        )
        resolved_reconnect_reason = (
            queue_metrics.get("reconnect_reason")
            if isinstance(queue_metrics.get("reconnect_reason"), str)
            else metadata.get("reconnect_reason")
            if isinstance(metadata.get("reconnect_reason"), str)
            else None
        )
        try:
            trace_payload = payload
            if not isinstance(payload, ResponseBodyRef):
                try:
                    captured = self._adapter.capture_trace_message_body(
                        session_id,
                        payload,
                    )
                except Exception:
                    captured = None
                if captured is not None:
                    trace_payload = captured
            recorder.append_message(
                trace_id=trace_id,
                debug_session_id=session_id,
                runtime_session_id=session_id,
                node_id=(
                    metadata.get("node_id")
                    if isinstance(metadata.get("node_id"), str)
                    else None
                ),
                operation_id=(
                    metadata.get("operation_id")
                    if isinstance(metadata.get("operation_id"), str)
                    else None
                ),
                connection_id=resolved_connection_id,
                event_kind=event_kind,
                payload=trace_payload,
                sequence_id=sequence_id,
                connection_epoch=resolved_connection_epoch,
                debug_event_index=resolved_debug_event_index,
            )
            recorder.update_connection(
                trace_id=trace_id,
                debug_session_id=session_id,
                runtime_session_id=session_id,
                node_id=(
                    metadata.get("node_id")
                    if isinstance(metadata.get("node_id"), str)
                    else None
                ),
                operation_id=(
                    metadata.get("operation_id")
                    if isinstance(metadata.get("operation_id"), str)
                    else None
                ),
                connection_id=resolved_connection_id,
                connection_epoch=resolved_connection_epoch,
                protocol=(
                    metadata.get("protocol")
                    if isinstance(metadata.get("protocol"), str)
                    else None
                ),
                subprotocol=(
                    metadata.get("subprotocol")
                    if isinstance(metadata.get("subprotocol"), str)
                    else None
                ),
                connection_state="connected",
                message_count=message_count,
                last_event_id=(
                    payload.get("event_id")
                    if isinstance(payload, Mapping)
                    and isinstance(payload.get("event_id"), str)
                    else None
                ),
                queue_depth=(
                    queue_metrics.get("queue_depth")
                    if isinstance(queue_metrics.get("queue_depth"), int)
                    else None
                ),
                dropped_count=(
                    queue_metrics.get("dropped_count")
                    if isinstance(queue_metrics.get("dropped_count"), int)
                    else None
                ),
                drop_events=(
                    queue_metrics.get("drop_events")
                    if isinstance(queue_metrics.get("drop_events"), list)
                    else None
                ),
                backpressure_policy=(
                    queue_metrics.get("backpressure_policy")
                    if isinstance(queue_metrics.get("backpressure_policy"), str)
                    else None
                ),
                activation_queue_depth=(
                    activation_metrics.get("activation_queue_depth")
                    if isinstance(activation_metrics.get("activation_queue_depth"), int)
                    else None
                ),
                activation_dropped_count=(
                    activation_metrics.get("activation_dropped_count")
                    if isinstance(activation_metrics.get("activation_dropped_count"), int)
                    else None
                ),
                activation_drop_events=(
                    activation_metrics.get("activation_drop_events")
                    if isinstance(activation_metrics.get("activation_drop_events"), list)
                    else None
                ),
                reconnect_count=resolved_reconnect_count,
                reconnect_reason=resolved_reconnect_reason,
                debug_event_index=resolved_debug_event_index,
            )
        except Exception:
            return

    def refresh_connection_traces(self, *, session_id: str) -> None:
        """将自动重连后的句柄状态同步到 Debug Trace。"""
        recorder = self._trace_recorder
        if recorder is None:
            return
        with self._lock:
            handles = tuple(self._long_connections.get(session_id, ()))
        for handle in handles:
            self._refresh_connection_trace(session_id=session_id, handle=handle)

    def _refresh_connection_trace(self, *, session_id: str, handle: object) -> None:
        recorder = self._trace_recorder
        if recorder is None:
            return
        with self._lock:
            metadata = self._connection_trace_metadata.get(id(handle))
            if metadata is None or metadata.get("session_id") != session_id:
                return
        queue_metrics = self._connection_queue_metrics(handle)
        activation_metrics = self._session_activation_queue_metrics(session_id)
        with self._lock:
            current_metadata = self._connection_trace_metadata.get(id(handle))
            if current_metadata is None:
                return
            current_metadata.update(queue_metrics)
            current_metadata.update(activation_metrics)
            metadata = dict(current_metadata)
        trace_id = metadata.get("trace_id")
        connection_id = metadata.get("connection_id")
        if not isinstance(trace_id, str) or not isinstance(connection_id, str):
            return
        connection_epoch = (
            queue_metrics.get("connection_epoch")
            if isinstance(queue_metrics.get("connection_epoch"), int)
            else metadata.get("connection_epoch")
            if isinstance(metadata.get("connection_epoch"), int)
            else None
        )
        reconnect_count = (
            queue_metrics.get("reconnect_count")
            if isinstance(queue_metrics.get("reconnect_count"), int)
            else metadata.get("reconnect_count")
            if isinstance(metadata.get("reconnect_count"), int)
            else None
        )
        reconnect_reason = (
            queue_metrics.get("reconnect_reason")
            if isinstance(queue_metrics.get("reconnect_reason"), str)
            else metadata.get("reconnect_reason")
            if isinstance(metadata.get("reconnect_reason"), str)
            else None
        )
        connection_state = queue_metrics.get("connection_state")
        if not isinstance(connection_state, str):
            connection_state = "connected"
        try:
            recorder.update_connection(
                trace_id=trace_id,
                debug_session_id=session_id,
                runtime_session_id=session_id,
                node_id=(metadata.get("node_id") if isinstance(metadata.get("node_id"), str) else None),
                operation_id=(
                    metadata.get("operation_id")
                    if isinstance(metadata.get("operation_id"), str)
                    else None
                ),
                connection_id=connection_id,
                connection_epoch=connection_epoch,
                protocol=(metadata.get("protocol") if isinstance(metadata.get("protocol"), str) else None),
                subprotocol=(
                    metadata.get("subprotocol")
                    if isinstance(metadata.get("subprotocol"), str)
                    else None
                ),
                connection_state=connection_state,
                message_count=int(metadata.get("message_count", 0)),
                last_event_id=(
                    queue_metrics.get("last_event_id")
                    if isinstance(queue_metrics.get("last_event_id"), str)
                    else None
                ),
                queue_depth=(
                    queue_metrics.get("queue_depth")
                    if isinstance(queue_metrics.get("queue_depth"), int)
                    else None
                ),
                dropped_count=(
                    queue_metrics.get("dropped_count")
                    if isinstance(queue_metrics.get("dropped_count"), int)
                    else None
                ),
                drop_events=(
                    queue_metrics.get("drop_events")
                    if isinstance(queue_metrics.get("drop_events"), list)
                    else None
                ),
                activation_queue_depth=(
                    activation_metrics.get("activation_queue_depth")
                    if isinstance(activation_metrics.get("activation_queue_depth"), int)
                    else None
                ),
                activation_dropped_count=(
                    activation_metrics.get("activation_dropped_count")
                    if isinstance(activation_metrics.get("activation_dropped_count"), int)
                    else None
                ),
                activation_drop_events=(
                    activation_metrics.get("activation_drop_events")
                    if isinstance(activation_metrics.get("activation_drop_events"), list)
                    else None
                ),
                backpressure_policy=(
                    queue_metrics.get("backpressure_policy")
                    if isinstance(queue_metrics.get("backpressure_policy"), str)
                    else None
                ),
                reconnect_count=reconnect_count,
                reconnect_reason=reconnect_reason,
                debug_event_index=(
                    metadata.get("debug_event_index")
                    if isinstance(metadata.get("debug_event_index"), int)
                    and not isinstance(metadata.get("debug_event_index"), bool)
                    else None
                ),
            )
        except Exception:
            return

    def describe_connection(
        self,
        *,
        session_id: str,
        handle: object,
    ) -> dict[str, object]:
        self._require_session_connection(session_id, handle)
        queue_status = getattr(handle, "queue_status", None)
        if not isinstance(queue_status, dict):
            raise ValueError("network.connection_queue_unavailable")
        return dict(queue_status)

    def wait_connection_activation(
        self,
        *,
        session_id: str,
        handle: object,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        self._require_session_connection(session_id, handle)
        activation_key = self._connection_activation_key(handle)
        if activation_key is not None and activation_key[0] == session_id:
            with self._lock:
                activation_queue = self._session_activation_queues.get(session_id)
            if activation_queue is not None:
                try:
                    return activation_queue.wait(
                        activation_key[1],
                        timeout_seconds=timeout_seconds,
                    )
                except (QueueBackpressureError, QueueCancelledError, QueueClosedError):
                    raise
        waiter = getattr(handle, "wait_next_activation", None)
        if not callable(waiter):
            raise ValueError("network.connection_activation_unavailable")
        activation = waiter(timeout_seconds=timeout_seconds)
        if not isinstance(activation, dict):
            raise ValueError("network.connection_activation_invalid")
        return activation

    @staticmethod
    def _connection_key(protocol: str, connection_id: str | None) -> str:
        if isinstance(connection_id, str) and connection_id.strip():
            return connection_id.strip()
        return f"{protocol}:{uuid4().hex}"

    def read_debug_body(self, session_id: str, descriptor: dict) -> bytes:
        """读取活动 Debug 会话中已登记的网络正文资源。"""
        return self._adapter.read_debug_body(session_id, descriptor)

    def capture_trace_body(
        self,
        session_id: str,
        payload: object,
        *,
        content_type: str | None = None,
    ) -> ResponseBodyRef | None:
        """将超大 Debug 正文写入活动会话的临时资源。"""
        return self._adapter.capture_trace_body(
            session_id,
            payload,
            content_type=content_type,
        )

    def _get_session_activation_queue(
        self,
        session_id: str,
        *,
        maxsize: int,
    ) -> SessionActivationQueue:
        with self._lock:
            queue = self._session_activation_queues.get(session_id)
            if queue is None:
                queue = SessionActivationQueue(maxsize=max(1, int(maxsize)))
                self._session_activation_queues[session_id] = queue
            return queue

    def _build_activation_sink(
        self,
        *,
        session_id: str,
        connection_key: str,
        backpressure_policy: str,
        maxsize: int,
    ) -> Callable[[dict[str, object]], None]:
        activation_queue = self._get_session_activation_queue(session_id, maxsize=maxsize)

        def publish(activation: dict[str, object]) -> None:
            activation_queue.publish(
                connection_key,
                activation,
                backpressure_policy=backpressure_policy,
            )
            # 接收线程产生激活时立即记录原始消息；节点随后调用
            # receive/next_event 只负责消费，不能决定 Trace 是否存在。
            self.record_connection_activation(
                session_id=session_id,
                connection_id=connection_key,
                activation=activation,
            )

        return publish

    def _register_connection_activation(
        self,
        session_id: str,
        handle: object,
        connection_key: str,
    ) -> None:
        with self._lock:
            self._connection_activation_keys[id(handle)] = (session_id, connection_key)

    def _connection_activation_key(self, handle: object) -> tuple[str, str] | None:
        with self._lock:
            return self._connection_activation_keys.get(id(handle))

    def _discard_connection_activation(self, session_id: str, connection_key: str) -> None:
        with self._lock:
            activation_queue = self._session_activation_queues.get(session_id)
            self._pending_activation_trace_records.pop((session_id, connection_key), None)
        if activation_queue is not None:
            activation_queue.discard(connection_key)

    def _schedule_operation(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
        result_future: Future[NetworkResult],
        trace_id: str | None = None,
    ) -> None:
        task = self._loop.create_task(self._execute_with_retry(operation, snapshot))
        active_tasks = self._active_tasks.setdefault(operation.session_id, set())
        active_tasks.add(task)

        def complete(completed_task: asyncio.Task[NetworkResult]) -> None:
            active_tasks.discard(completed_task)
            if not active_tasks:
                self._active_tasks.pop(operation.session_id, None)
            try:
                result = completed_task.result()
            except asyncio.CancelledError:
                error = build_network_error(
                    "network.cancelled",
                    operation=operation,
                    snapshot=snapshot,
                )
                result = NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error=error.error_code,
                    error=error,
                )
            except Exception as exc:
                error = build_network_error(
                    exc,
                    operation=operation,
                    snapshot=snapshot,
                )
                result = NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error=error.error_code,
                    error=error,
                )

            if trace_id is not None and self._trace_recorder is not None:
                request_body = self._adapter.pop_request_trace_body(operation.request_id)
                response_body = None
                if result.body_ref is not None:
                    try:
                        response_body = (
                            result.body_ref
                            if result.body_ref.storage_kind == "file"
                            else result.body_ref.read_bytes()
                        )
                    except BaseException:
                        response_body = result.body_ref
                try:
                    self._trace_recorder.complete_operation(
                        trace_id=trace_id,
                        status=(
                            "cancelled"
                            if result.transport_error == "network.cancelled"
                            else result.status
                        ),
                        response_status=result.status_code,
                        response_headers=result.headers,
                        request_body=request_body,
                        response_body=response_body,
                        error_code=result.transport_error,
                        final_url=result.final_url,
                        redirects=result.redirects,
                        retry_attempt=result.retry_attempt,
                    )
                except Exception:
                    # A trace sink is observational and must not break callers.
                    pass
            if result_future.done():
                return
            result_future.set_result(result)

        task.add_done_callback(complete)

    async def _execute_with_retry(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkResult:
        try:
            policy = _normalize_retry_policy(snapshot.retry_policy)
        except ValueError as exc:
            error = build_network_error(
                exc,
                operation=operation,
                snapshot=snapshot,
                error_code="network.retry_policy_invalid",
            )
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=error.error_code,
                error=error,
            )

        start_time = monotonic()
        can_retry = _retry_is_allowed(operation, snapshot, policy)
        resolved_tls = self._tls_resolver.resolve(
            snapshot.tls if isinstance(snapshot.tls, dict) else {}
        )
        self._emit_network_security_events(
            operation,
            snapshot,
            (*resolved_tls.audit_events, *_connection_security_audit_events(snapshot, operation.url)),
        )
        result: NetworkResult | None = None
        for attempt_index in range(policy["max_attempts"]):
            try:
                effective_snapshot = await self._resolve_oauth_snapshot(operation, snapshot)
            except ValueError as exc:
                error = build_network_error(
                    exc,
                    operation=operation,
                    snapshot=snapshot,
                    error_code="network.oauth_failed",
                    retry_attempt=attempt_index + 1,
                )
                return NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error=error.error_code,
                    error=error,
                )
            effective_operation = self._resolve_static_sensitive_operation(operation)
            result = _with_retry_attempt(
                await self._adapter.execute_async(effective_operation, effective_snapshot),
                operation=operation,
                snapshot=effective_snapshot,
                retry_attempt=attempt_index + 1,
            )
            if not can_retry or not _is_retryable_result(result, policy):
                return result
            if attempt_index + 1 >= policy["max_attempts"]:
                return result

            delay_seconds = _retry_delay_seconds(
                result,
                policy,
                attempt_index=attempt_index,
            )
            max_total_seconds = policy["max_total_seconds"]
            if (
                max_total_seconds is not None
                and monotonic() - start_time + delay_seconds >= max_total_seconds
            ):
                return result
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
        assert result is not None
        return result

    def _cancel_session_on_loop(self, session_id: str) -> None:
        for task in tuple(self._active_tasks.get(session_id, ())):
            task.cancel()
        self._adapter.close_session(session_id)

    async def _resolve_oauth_snapshot(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkContextSnapshot:
        oauth_snapshot = self._resolve_static_sensitive_snapshot(snapshot)
        auth = oauth_snapshot.auth
        if not isinstance(auth, Mapping):
            return oauth_snapshot
        auth_type = auth.get("type")
        if not isinstance(auth_type, str) or auth_type.strip().lower() != "oauth_client_credentials":
            return oauth_snapshot
        if self._oauth_service is None or self._sensitive_values is None:
            raise ValueError("network.oauth_sensitive_values_unavailable")
        key = (operation.session_id, snapshot.context_id)
        with self._oauth_tokens_lock:
            token_state = self._oauth_tokens.get(key)
        if token_state is None or (
            token_state.expires_at is not None and token_state.expires_at <= time() + 5
        ):
            token_url = auth.get("token_url")
            client_id = auth.get("client_id")
            client_secret = auth.get("client_secret")
            scope = auth.get("scope")
            if isinstance(token_url, str) and urlsplit(token_url).scheme.lower() == "http":
                self._emit_network_security_events(
                    operation,
                    snapshot,
                    ("network.oauth_plaintext",),
                )
            if token_state is not None and token_state.refresh_token is not None:
                token_state = await asyncio.to_thread(
                    self._oauth_service.refresh_access_token,
                    token_url=token_url,
                    refresh_token=token_state.refresh_token,
                    scope_id=operation.session_id,
                    client_id=client_id,
                    scope=scope,
                    snapshot=oauth_snapshot,
                )
            else:
                request = self._oauth_service.build_client_credentials_request(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    scope=scope,
                    scope_id=operation.session_id,
                )
                token_state = await asyncio.to_thread(
                    self._oauth_service.exchange_client_credentials,
                    request=request,
                    scope_id=operation.session_id,
                    snapshot=oauth_snapshot,
                )
            with self._oauth_tokens_lock:
                self._oauth_tokens[key] = token_state
        from weconduct.application.sensitive_values.models import SensitiveConsumer

        access_token = self._sensitive_values.resolve(
            token_state.access_token,
            consumer=SensitiveConsumer.NETWORK_RUNTIME,
        )
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("network.oauth_access_token_invalid")
        return self._resolve_static_sensitive_snapshot(
            replace(oauth_snapshot, auth={"type": "bearer", "token": access_token})
        )

    def _resolve_oauth_snapshot_sync(
        self,
        *,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
        timeout_seconds: float,
    ) -> NetworkContextSnapshot:
        future = asyncio.run_coroutine_threadsafe(
            self._resolve_oauth_snapshot(operation, snapshot),
            self._loop,
        )
        return future.result(timeout=timeout_seconds)

    def _clear_session_oauth(self, session_id: str) -> None:
        with self._oauth_tokens_lock:
            for key in tuple(self._oauth_tokens):
                if key[0] == session_id:
                    self._oauth_tokens.pop(key, None)

    def _get_sequence_allocator(self, session_id: str) -> SequenceAllocator:
        with self._lock:
            allocator = self._sequence_allocators.get(session_id)
            if allocator is None:
                allocator = SequenceAllocator()
                self._sequence_allocators[session_id] = allocator
            return allocator

    def _clear_session_sequence_allocator(self, session_id: str) -> None:
        with self._lock:
            self._sequence_allocators.pop(session_id, None)

    def _emit_network_security_events(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
        event_names: tuple[str, ...],
    ) -> None:
        if self._audit_event_sink is None:
            return
        for event_name in event_names:
            self._audit_event_sink(
                event_name,
                {
                    "event_kind": event_name,
                    "session_id": operation.session_id,
                    "operation_id": operation.operation_id,
                    "network_context_id": snapshot.context_id,
                },
            )

    def _resolve_static_sensitive_snapshot(
        self,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkContextSnapshot:
        auth = snapshot.auth
        if isinstance(auth, Mapping):
            normalized_auth = dict(auth)
            auth_type = normalized_auth.get("type")
            fields = (
                ("token",)
                if isinstance(auth_type, str) and auth_type.strip().lower() == "bearer"
                else ("username", "password")
                if isinstance(auth_type, str) and auth_type.strip().lower() == "basic"
                else ()
            )
            for field_name in fields:
                if field_name in normalized_auth:
                    normalized_auth[field_name] = self._resolve_sensitive_text(
                        normalized_auth[field_name]
                    )
            auth = normalized_auth

        headers = self._resolve_sensitive_mapping(snapshot.headers)
        cookies = self._resolve_sensitive_mapping(snapshot.cookies)

        proxy = snapshot.proxy
        if isinstance(proxy, Mapping):
            normalized_proxy = dict(proxy)
            username = self._resolve_sensitive_text(normalized_proxy.pop("username", None))
            password = self._resolve_sensitive_text(normalized_proxy.pop("password", None))
            if username is not None or password is not None:
                raw_url = normalized_proxy.get("url")
                if not isinstance(raw_url, str):
                    raise ValueError("network.proxy_credentials_invalid")
                normalized_proxy["url"] = _with_proxy_credentials(
                    raw_url,
                    username=username,
                    password=password,
                )
            proxy = normalized_proxy
        return replace(snapshot, auth=auth, headers=headers, cookies=cookies, proxy=proxy)

    def _resolve_static_sensitive_operation(
        self,
        operation: NetworkOperation,
    ) -> NetworkOperation:
        return replace(operation, headers=self._resolve_sensitive_mapping(operation.headers))

    def _resolve_sensitive_mapping(
        self,
        values: Mapping[str, object],
    ) -> dict[str, str]:
        return {
            str(name): resolved
            for name, value in values.items()
            if isinstance((resolved := self._resolve_sensitive_text(value)), str)
        }

    def _resolve_sensitive_text(self, value: object) -> str | None:
        from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef

        if value is None:
            return None
        if isinstance(value, SensitiveRef):
            if self._sensitive_values is None:
                raise ValueError("network.sensitive_values_unavailable")
            value = self._sensitive_values.resolve(
                value,
                consumer=SensitiveConsumer.NETWORK_RUNTIME,
            )
        if not isinstance(value, str):
            raise ValueError("network.sensitive_value_invalid")
        return value

    def _register_long_connection(self, session_id: str, handle: object) -> None:
        with self._lock:
            if self._closed:
                close = getattr(handle, "close", None)
                if callable(close):
                    close()
                raise RuntimeError("network runtime service is closed")
            self._long_connections.setdefault(session_id, set()).add(handle)

    def _start_connection_trace(
        self,
        *,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot | None = None,
        protocol: str,
        connection_id: str | None,
        request_headers: Mapping[str, object] | None = None,
        request_query: Mapping[str, object] | None = None,
    ) -> str | None:
        recorder = self._trace_recorder
        if recorder is None:
            return None
        try:
            trace = recorder.start_operation(
                trace_id=None,
                debug_session_id=operation.session_id,
                runtime_session_id=operation.session_id,
                node_id=operation.node_id,
                operation_id=operation.operation_id,
                method=operation.method,
                url=operation.url,
                protocol=protocol,
                request_headers=self._resolve_debug_trace_value(request_headers or {}),
                request_query=self._resolve_debug_trace_value(request_query or {}),
                connection_id=connection_id,
                proxy=(
                    self._resolve_debug_trace_value(snapshot.proxy)
                    if snapshot is not None
                    else None
                ),
                tls=(
                    self._resolve_debug_trace_value(snapshot.tls)
                    if snapshot is not None
                    else None
                ),
                debug_event_index=self._current_debug_event_index(),
            )
        except Exception:
            return None
        trace_id = trace.get("trace_id")
        return trace_id if isinstance(trace_id, str) else None

    def _complete_connection_trace(
        self,
        *,
        trace_id: str | None,
        status: str,
        response_status: int | None = None,
        response_headers: Mapping[str, object] | None = None,
        error_code: str | None = None,
    ) -> None:
        if trace_id is None or self._trace_recorder is None:
            return
        try:
            self._trace_recorder.complete_operation(
                trace_id=trace_id,
                status=status,
                response_status=response_status,
                response_headers=response_headers,
                error_code=error_code,
            )
        except Exception:
            return

    def _register_connection_trace(
        self,
        *,
        session_id: str,
        handle: object,
        trace_id: str | None,
        operation: NetworkOperation,
        protocol: str,
        connection_id: str | None,
        subprotocol: str | None = None,
    ) -> None:
        if trace_id is None or self._trace_recorder is None:
            return
        resolved_connection_id = connection_id or trace_id
        debug_event_index = None
        try:
            trace = self._trace_recorder.get_trace(trace_id)
            if isinstance(trace, Mapping):
                debug_event_index = self._normalize_debug_event_index(
                    trace.get("debug_event_index")
                )
        except Exception:
            debug_event_index = None
        if debug_event_index is None:
            debug_event_index = self._current_debug_event_index()
        metadata = {
            "session_id": session_id,
            "trace_id": trace_id,
            "node_id": operation.node_id,
            "operation_id": operation.operation_id,
            "protocol": protocol,
            "subprotocol": subprotocol,
            "connection_id": resolved_connection_id,
            "connection_epoch": 1,
            "message_count": 0,
            "reconnect_count": 0,
            "reconnect_reason": None,
            "debug_event_index": debug_event_index,
        }
        metadata.update(self._connection_queue_metrics(handle))
        metadata.update(self._session_activation_queue_metrics(session_id))
        with self._lock:
            self._connection_trace_metadata[id(handle)] = metadata
            pending_activations = self._pending_activation_trace_records.pop(
                (session_id, resolved_connection_id),
                [],
            )
        try:
            self._trace_recorder.update_connection(
                trace_id=trace_id,
                debug_session_id=session_id,
                runtime_session_id=session_id,
                node_id=operation.node_id,
                operation_id=operation.operation_id,
                connection_id=resolved_connection_id,
                connection_epoch=1,
                protocol=protocol,
                subprotocol=subprotocol,
                connection_state="connected",
                message_count=0,
                queue_depth=(
                    metadata.get("queue_depth")
                    if isinstance(metadata.get("queue_depth"), int)
                    else None
                ),
                dropped_count=(
                    metadata.get("dropped_count")
                    if isinstance(metadata.get("dropped_count"), int)
                    else None
                ),
                drop_events=(
                    metadata.get("drop_events")
                    if isinstance(metadata.get("drop_events"), list)
                    else None
                ),
                activation_queue_depth=(
                    metadata.get("activation_queue_depth")
                    if isinstance(metadata.get("activation_queue_depth"), int)
                    else None
                ),
                activation_dropped_count=(
                    metadata.get("activation_dropped_count")
                    if isinstance(metadata.get("activation_dropped_count"), int)
                    else None
                ),
                activation_drop_events=(
                    metadata.get("activation_drop_events")
                    if isinstance(metadata.get("activation_drop_events"), list)
                    else None
                ),
                backpressure_policy=(
                    metadata.get("backpressure_policy")
                    if isinstance(metadata.get("backpressure_policy"), str)
                    else None
                ),
                reconnect_count=(
                    metadata.get("reconnect_count")
                    if isinstance(metadata.get("reconnect_count"), int)
                    else None
                ),
                reconnect_reason=(
                    metadata.get("reconnect_reason")
                    if isinstance(metadata.get("reconnect_reason"), str)
                    else None
                ),
                debug_event_index=(
                    metadata.get("debug_event_index")
                    if isinstance(metadata.get("debug_event_index"), int)
                    and not isinstance(metadata.get("debug_event_index"), bool)
                    else None
                ),
            )
        except Exception:
            pass
        for activation in pending_activations:
            self.record_connection_activation(
                session_id=session_id,
                connection_id=resolved_connection_id,
                activation=activation,
            )

    def _record_connection_closed(
        self,
        session_id: str,
        handle: object,
        *,
        close_reason: str,
    ) -> None:
        recorder = self._trace_recorder
        queue_metrics = self._connection_queue_metrics(handle)
        activation_metrics = self._session_activation_queue_metrics(session_id)
        with self._lock:
            metadata = self._connection_trace_metadata.pop(id(handle), None)
            self._connection_activation_keys.pop(id(handle), None)
        if recorder is None or metadata is None:
            return
        if session_id and metadata.get("session_id") != session_id:
            return
        trace_id = metadata.get("trace_id")
        connection_id = metadata.get("connection_id")
        if not isinstance(trace_id, str) or not isinstance(connection_id, str):
            return
        metadata.update(queue_metrics)
        metadata.update(activation_metrics)
        owner_session_id = str(metadata.get("session_id") or session_id)
        try:
            recorder.update_connection(
                trace_id=trace_id,
                debug_session_id=owner_session_id,
                runtime_session_id=owner_session_id,
                node_id=(
                    metadata.get("node_id")
                    if isinstance(metadata.get("node_id"), str)
                    else None
                ),
                operation_id=(
                    metadata.get("operation_id")
                    if isinstance(metadata.get("operation_id"), str)
                    else None
                ),
                connection_id=connection_id,
                connection_epoch=(
                    metadata.get("connection_epoch")
                    if isinstance(metadata.get("connection_epoch"), int)
                    else None
                ),
                protocol=(
                    metadata.get("protocol")
                    if isinstance(metadata.get("protocol"), str)
                    else None
                ),
                subprotocol=(
                    metadata.get("subprotocol")
                    if isinstance(metadata.get("subprotocol"), str)
                    else None
                ),
                connection_state=(
                    "failed"
                    if metadata.get("connection_state") == "failed"
                    else "closed"
                ),
                message_count=int(metadata.get("message_count", 0)),
                queue_depth=(
                    metadata.get("queue_depth")
                    if isinstance(metadata.get("queue_depth"), int)
                    else None
                ),
                dropped_count=(
                    metadata.get("dropped_count")
                    if isinstance(metadata.get("dropped_count"), int)
                    else None
                ),
                drop_events=(
                    metadata.get("drop_events")
                    if isinstance(metadata.get("drop_events"), list)
                    else None
                ),
                activation_queue_depth=(
                    metadata.get("activation_queue_depth")
                    if isinstance(metadata.get("activation_queue_depth"), int)
                    else None
                ),
                activation_dropped_count=(
                    metadata.get("activation_dropped_count")
                    if isinstance(metadata.get("activation_dropped_count"), int)
                    else None
                ),
                activation_drop_events=(
                    metadata.get("activation_drop_events")
                    if isinstance(metadata.get("activation_drop_events"), list)
                    else None
                ),
                backpressure_policy=(
                    metadata.get("backpressure_policy")
                    if isinstance(metadata.get("backpressure_policy"), str)
                    else None
                ),
                reconnect_count=(
                    metadata.get("reconnect_count")
                    if isinstance(metadata.get("reconnect_count"), int)
                    else None
                ),
                reconnect_reason=(
                    metadata.get("reconnect_reason")
                    if isinstance(metadata.get("reconnect_reason"), str)
                    else None
                ),
                close_reason=close_reason,
                debug_event_index=(
                    metadata.get("debug_event_index")
                    if isinstance(metadata.get("debug_event_index"), int)
                    and not isinstance(metadata.get("debug_event_index"), bool)
                    else None
                ),
            )
        except Exception:
            return

    def _require_session_connection(self, session_id: str, handle: object) -> None:
        with self._lock:
            connections = self._long_connections.get(session_id)
            if connections is None or handle not in connections:
                raise ValueError("network.connection_not_found")

    @staticmethod
    def _connection_queue_metrics(handle: object) -> dict[str, object]:
        try:
            status = getattr(handle, "queue_status", None)
            if callable(status):
                status = status()
        except Exception:
            return {}
        if not isinstance(status, Mapping):
            return {}

        metrics: dict[str, object] = {}
        depth = status.get("depth")
        dropped_count = status.get("dropped_count")
        connection_epoch = status.get("connection_epoch")
        if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 0:
            metrics["queue_depth"] = depth
        if isinstance(dropped_count, int) and not isinstance(dropped_count, bool) and dropped_count >= 0:
            metrics["dropped_count"] = dropped_count
        drop_events = status.get("drop_events")
        if isinstance(drop_events, list):
            metrics["drop_events"] = [
                dict(item)
                for item in drop_events
                if isinstance(item, Mapping)
            ]
        if isinstance(connection_epoch, int) and not isinstance(connection_epoch, bool) and connection_epoch >= 1:
            metrics["connection_epoch"] = connection_epoch
            metrics["reconnect_count"] = max(connection_epoch - 1, 0)
        reconnect_reason = status.get("reconnect_reason")
        if isinstance(reconnect_reason, str) and reconnect_reason.strip():
            metrics["reconnect_reason"] = reconnect_reason.strip()
        connection_state = status.get("connection_state")
        if isinstance(connection_state, str) and connection_state.strip():
            metrics["connection_state"] = connection_state
        elif status.get("closed") is True:
            metrics["connection_state"] = "closed"
        last_event_id = getattr(handle, "last_event_id", None)
        if isinstance(last_event_id, str) and last_event_id:
            metrics["last_event_id"] = last_event_id
        policy = status.get("backpressure_policy")
        if isinstance(policy, str) and policy.strip():
            metrics["backpressure_policy"] = policy
        return metrics

    def _session_activation_queue_metrics(self, session_id: str) -> dict[str, object]:
        with self._lock:
            activation_queue = self._session_activation_queues.get(session_id)
        if activation_queue is None:
            return {}
        try:
            status = activation_queue.status()
        except Exception:
            return {}
        if not isinstance(status, Mapping):
            return {}
        metrics: dict[str, object] = {}
        depth = status.get("depth")
        dropped_count = status.get("dropped_count")
        drop_events = status.get("drop_events")
        if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 0:
            metrics["activation_queue_depth"] = depth
        if isinstance(dropped_count, int) and not isinstance(dropped_count, bool) and dropped_count >= 0:
            metrics["activation_dropped_count"] = dropped_count
        if isinstance(drop_events, list):
            metrics["activation_drop_events"] = [
                dict(item) for item in drop_events if isinstance(item, Mapping)
            ]
        return metrics

    def _close_session_connections(self, session_id: str) -> None:
        with self._lock:
            connections = tuple(self._long_connections.pop(session_id, ()))
            activation_queue = self._session_activation_queues.get(session_id)
            for key in tuple(self._pending_activation_trace_records):
                if key[0] == session_id:
                    self._pending_activation_trace_records.pop(key, None)
        if activation_queue is not None:
            activation_queue.cancel()
        for connection in connections:
            activation_key = self._connection_activation_key(connection)
            if activation_key is not None:
                self._discard_connection_activation(*activation_key)
            self._record_connection_closed(session_id, connection, close_reason="session_cancelled")
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        if activation_queue is not None:
            with self._lock:
                if self._session_activation_queues.get(session_id) is activation_queue:
                    self._session_activation_queues.pop(session_id, None)

    def _close_all_connections(self) -> None:
        with self._lock:
            connections = tuple(
                connection
                for session_connections in self._long_connections.values()
                for connection in session_connections
            )
            self._long_connections.clear()
            activation_queues = tuple(self._session_activation_queues.items())
            self._pending_activation_trace_records.clear()
        for connection in connections:
            activation_key = self._connection_activation_key(connection)
            owner_session_id = activation_key[0] if activation_key is not None else ""
            if activation_key is not None:
                self._discard_connection_activation(*activation_key)
            self._record_connection_closed(owner_session_id, connection, close_reason="service_closed")
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        with self._lock:
            for session_id, activation_queue in activation_queues:
                if self._session_activation_queues.get(session_id) is activation_queue:
                    self._session_activation_queues.pop(session_id, None)
        for _, activation_queue in activation_queues:
            activation_queue.close()

    def _require_open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("network runtime service is closed")

    def _effective_headers(
        self,
        snapshot: NetworkContextSnapshot,
        headers: Mapping[str, object] | None,
    ) -> dict[str, str]:
        effective = self._resolve_sensitive_mapping(snapshot.headers)
        effective.update(self._resolve_sensitive_mapping(headers or {}))
        if snapshot.cookies and not any(key.lower() == "cookie" for key in effective):
            effective["Cookie"] = "; ".join(
                f"{name}={value}"
                for name, value in self._resolve_sensitive_mapping(snapshot.cookies).items()
            )
        return apply_static_auth(effective, snapshot.auth)

    def _resolve_proxy(self, snapshot: NetworkContextSnapshot, url: str) -> str | None:
        config = snapshot.proxy if isinstance(snapshot.proxy, dict) else {"mode": "direct"}
        return ProxyResolver(access_policy=self._access_policy).resolve(config, url).url

    async def _shutdown(self) -> None:
        active_tasks = [task for tasks in self._active_tasks.values() for task in tasks]
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        await self._adapter.aclose()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()


def _with_proxy_credentials(
    raw_url: str,
    *,
    username: str | None,
    password: str | None,
) -> str:
    parsed = urlsplit(raw_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("network.proxy_credentials_invalid")
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    host_port = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    userinfo = quote(username or "", safe="")
    if password is not None:
        userinfo = f"{userinfo}:{quote(password, safe='')}"
    return urlunsplit(
        (parsed.scheme, f"{userinfo}@{host_port}", parsed.path, parsed.query, parsed.fragment)
    )
