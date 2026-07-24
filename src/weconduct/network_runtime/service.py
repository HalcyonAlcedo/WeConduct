from __future__ import annotations

import asyncio
from concurrent.futures import Future
from pathlib import Path
from threading import Event, RLock, Thread

import httpx

from .access_policy import NetworkAccessPolicy
from .http_adapter import HttpxAdapter
from .long_connection import SSEClientHandle, WebSocketClientHandle
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .proxy import ProxyResolver


class NetworkRuntimeService:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
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
        with self._lock:
            if self._closed:
                return
            self._loop.call_soon_threadsafe(self._cancel_session_on_loop, session_id)

    def close(self) -> None:
        self._close_all_connections()
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
        proxy = self._resolve_proxy(snapshot, url)
        handle = SSEClientHandle(
            url=url,
            headers=self._effective_headers(snapshot, headers),
            params={**dict(snapshot.query), **(params or {})},
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            max_queue_size=max_queue_size,
            access_policy=self._access_policy,
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
        proxy = self._resolve_proxy(snapshot, url)
        handle = WebSocketClientHandle(
            url=url,
            headers=self._effective_headers(snapshot, headers),
            proxy=proxy,
            timeout_seconds=timeout_seconds,
            subprotocols=subprotocols,
            access_policy=self._access_policy,
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
        task = self._loop.create_task(self._adapter.execute_async(operation, snapshot))
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
                result_future.set_result(
                    NetworkResult(
                        status="failed",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        transport_error="network.cancelled",
                    )
                )
            except Exception as exc:
                result_future.set_result(
                    NetworkResult(
                        status="failed",
                        operation_id=operation.operation_id,
                        session_id=operation.session_id,
                        transport_error=str(exc),
                    )
                )

        task.add_done_callback(complete)

    def _cancel_session_on_loop(self, session_id: str) -> None:
        for task in tuple(self._active_tasks.get(session_id, ())):
            task.cancel()
        self._adapter.close_session(session_id)

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
        return effective

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
