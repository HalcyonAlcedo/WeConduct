from __future__ import annotations

import asyncio
from concurrent.futures import Future
from pathlib import Path
from threading import Event, RLock, Thread

import httpx

from .access_policy import NetworkAccessPolicy
from .http_adapter import HttpxAdapter
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult


class NetworkRuntimeService:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
    ) -> None:
        self._adapter = HttpxAdapter(
            response_root_directory=response_root_directory,
            access_policy=access_policy,
            client=httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ),
        )
        self._client = self._adapter._client
        self._loop = asyncio.new_event_loop()
        self._ready = Event()
        self._closed = False
        self._lock = RLock()
        self._active_tasks: dict[str, set[asyncio.Task[NetworkResult]]] = {}
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
        with self._lock:
            if self._closed:
                return
            self._loop.call_soon_threadsafe(self._cancel_session_on_loop, session_id)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            shutdown = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        shutdown.result(timeout=1)
        with self._lock:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)

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

    async def _shutdown(self) -> None:
        active_tasks = [task for tasks in self._active_tasks.values() for task in tasks]
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        await self._adapter.aclose()
        await self._client.aclose()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()
