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
from typing import Mapping

import httpx

from .access_policy import NetworkAccessPolicy
from .authentication import apply_static_auth
from .errors import build_network_error
from .http_adapter import HttpxAdapter
from .long_connection import SSEClientHandle, WebSocketClientHandle
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .oauth import OAuthService, OAuthTokenState
from .proxy import ProxyResolver
from .tls import TlsResolver, build_ssl_context


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
        return result
    error = result.error or build_network_error(
        result.transport_error or "network.transport_failed",
        operation=operation,
        snapshot=snapshot,
    )
    error = error.with_retry_attempt(retry_attempt)
    return replace(result, transport_error=error.error_code, error=error)


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


class NetworkRuntimeService:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
        sensitive_values: object | None = None,
    ) -> None:
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._adapter = HttpxAdapter(
            response_root_directory=response_root_directory,
            access_policy=self._access_policy,
            transport=transport,
        )
        self._client = self._adapter._client
        self._loop = asyncio.new_event_loop()
        self._ready = Event()
        self._closed = False
        self._lock = RLock()
        self._active_tasks: dict[str, set[asyncio.Task[NetworkResult]]] = {}
        self._long_connections: dict[str, set[object]] = {}
        self._sensitive_values = sensitive_values
        self._oauth_service = (
            OAuthService(
                sensitive_values=sensitive_values,  # type: ignore[arg-type]
                transport=transport,  # type: ignore[arg-type]
                access_policy=self._access_policy,
            )
            if sensitive_values is not None
            else None
        )
        self._oauth_tokens: dict[tuple[str, str | None], OAuthTokenState] = {}
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
            self._loop.call_soon_threadsafe(
                self._schedule_operation,
                operation,
                snapshot,
                future,
            )
            return future

    def cancel_session(self, session_id: str) -> None:
        self._close_session_connections(session_id)
        self._clear_session_oauth(session_id)
        with self._lock:
            if self._closed:
                return
            self._loop.call_soon_threadsafe(self._cancel_session_on_loop, session_id)

    def close(self) -> None:
        self._close_all_connections()
        self._oauth_tokens.clear()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            shutdown = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
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
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        max_queue_size: int = 100,
    ) -> tuple[SSEClientHandle, dict[str, object]]:
        self._require_open()
        effective_snapshot = self._resolve_oauth_snapshot_sync(
            operation=NetworkOperation(
                operation_id="network.sse_connect",
                session_id=session_id,
                method="GET",
                url=url,
            ),
            snapshot=snapshot,
            timeout_seconds=timeout_seconds,
        )
        proxy = self._resolve_proxy(effective_snapshot, url)
        resolved_tls = TlsResolver().resolve(
            effective_snapshot.tls if isinstance(effective_snapshot.tls, dict) else {}
        )
        handle = SSEClientHandle(
            url=url,
            headers=self._effective_headers(effective_snapshot, headers),
            params={**dict(effective_snapshot.query), **(params or {})},
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            max_queue_size=max_queue_size,
            access_policy=self._access_policy,
            ssl_context=build_ssl_context(resolved_tls),
            certificate_pins=resolved_tls.certificate_pins,
        )
        try:
            metadata = handle.start(timeout_seconds=timeout_seconds)
        except BaseException:
            handle.close()
            raise
        self._register_long_connection(session_id, handle)
        return handle, metadata

    def connect_websocket(
        self,
        *,
        session_id: str,
        snapshot: NetworkContextSnapshot,
        url: str,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        subprotocols: list[str] | None = None,
    ) -> tuple[WebSocketClientHandle, dict[str, object]]:
        self._require_open()
        effective_snapshot = self._resolve_oauth_snapshot_sync(
            operation=NetworkOperation(
                operation_id="network.websocket_connect",
                session_id=session_id,
                method="GET",
                url=url,
            ),
            snapshot=snapshot,
            timeout_seconds=timeout_seconds,
        )
        proxy = self._resolve_proxy(effective_snapshot, url)
        resolved_tls = TlsResolver().resolve(
            effective_snapshot.tls if isinstance(effective_snapshot.tls, dict) else {}
        )
        handle = WebSocketClientHandle(
            url=url,
            headers=self._effective_headers(effective_snapshot, headers),
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            subprotocols=subprotocols,
            access_policy=self._access_policy,
            ssl_context=build_ssl_context(resolved_tls),
            certificate_pins=resolved_tls.certificate_pins,
        )
        try:
            metadata = handle.start(timeout_seconds=timeout_seconds)
        except BaseException:
            handle.close()
            raise
        self._register_long_connection(session_id, handle)
        return handle, metadata

    def release_connection(self, session_id: str, handle: object) -> None:
        with self._lock:
            connections = self._long_connections.get(session_id)
            if connections is None:
                return
            connections.discard(handle)
            if not connections:
                self._long_connections.pop(session_id, None)

    def _schedule_operation(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
        result_future: Future[NetworkResult],
    ) -> None:
        task = self._loop.create_task(self._execute_with_retry(operation, snapshot))
        active_tasks = self._active_tasks.setdefault(operation.session_id, set())
        active_tasks.add(task)

        def complete(completed_task: asyncio.Task[NetworkResult]) -> None:
            active_tasks.discard(completed_task)
            if not active_tasks:
                self._active_tasks.pop(operation.session_id, None)
            if result_future.done():
                return
            try:
                result_future.set_result(completed_task.result())
            except asyncio.CancelledError:
                error = build_network_error(
                    "network.cancelled",
                    operation=operation,
                    snapshot=snapshot,
                )
                result_future.set_result(
                    NetworkResult(
                        status="failed",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        transport_error=error.error_code,
                        error=error,
                    )
                )
            except Exception as exc:
                error = build_network_error(
                    exc,
                    operation=operation,
                    snapshot=snapshot,
                )
                result_future.set_result(
                    NetworkResult(
                        status="failed",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        transport_error=error.error_code,
                        error=error,
                    )
                )

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
            result = _with_retry_attempt(
                await self._adapter.execute_async(operation, effective_snapshot),
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
        auth = snapshot.auth
        if not isinstance(auth, Mapping):
            return snapshot
        auth_type = auth.get("type")
        if not isinstance(auth_type, str) or auth_type.strip().lower() != "oauth_client_credentials":
            return snapshot
        if self._oauth_service is None or self._sensitive_values is None:
            raise ValueError("network.oauth_sensitive_values_unavailable")
        key = (operation.session_id, snapshot.context_id)
        token_state = self._oauth_tokens.get(key)
        if token_state is None or (
            token_state.expires_at is not None and token_state.expires_at <= time() + 5
        ):
            token_url = auth.get("token_url")
            client_id = auth.get("client_id")
            client_secret = auth.get("client_secret")
            scope = auth.get("scope")
            if token_state is not None and token_state.refresh_token is not None:
                token_state = await asyncio.to_thread(
                    self._oauth_service.refresh_access_token,
                    token_url=token_url,
                    refresh_token=token_state.refresh_token,
                    scope_id=operation.session_id,
                    client_id=client_id,
                    scope=scope,
                    snapshot=snapshot,
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
                    snapshot=snapshot,
                )
            self._oauth_tokens[key] = token_state
        from weconduct.application.sensitive_values.models import SensitiveConsumer

        access_token = self._sensitive_values.resolve(
            token_state.access_token,
            consumer=SensitiveConsumer.NETWORK_RUNTIME,
        )
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("network.oauth_access_token_invalid")
        return replace(snapshot, auth={"type": "bearer", "token": access_token})

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
        for key in tuple(self._oauth_tokens):
            if key[0] == session_id:
                self._oauth_tokens.pop(key, None)

    def _register_long_connection(self, session_id: str, handle: object) -> None:
        with self._lock:
            if self._closed:
                close = getattr(handle, "close", None)
                if callable(close):
                    close()
                raise RuntimeError("network runtime service is closed")
            self._long_connections.setdefault(session_id, set()).add(handle)

    def _close_session_connections(self, session_id: str) -> None:
        with self._lock:
            connections = tuple(self._long_connections.pop(session_id, ()))
        for connection in connections:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def _close_all_connections(self) -> None:
        with self._lock:
            connections = tuple(
                connection
                for session_connections in self._long_connections.values()
                for connection in session_connections
            )
            self._long_connections.clear()
        for connection in connections:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def _require_open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("network runtime service is closed")

    @staticmethod
    def _effective_headers(
        snapshot: NetworkContextSnapshot,
        headers: dict[str, str] | None,
    ) -> dict[str, str]:
        effective = {str(key): str(value) for key, value in snapshot.headers.items()}
        effective.update({str(key): str(value) for key, value in (headers or {}).items()})
        if snapshot.cookies and not any(key.lower() == "cookie" for key in effective):
            effective["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in snapshot.cookies.items()
            )
        return apply_static_auth(effective, snapshot.auth)

    @staticmethod
    def _resolve_proxy(snapshot: NetworkContextSnapshot, url: str) -> str | None:
        config = snapshot.proxy if isinstance(snapshot.proxy, dict) else {"mode": "direct"}
        return ProxyResolver().resolve(config, url).url

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
