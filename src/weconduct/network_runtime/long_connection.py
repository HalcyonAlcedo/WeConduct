from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import ssl
import sys
from threading import Event, RLock, Thread
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx
from httpx_sse import aconnect_sse
import websockets

from .access_policy import NetworkAccessPolicy, ResolvedNetworkTarget
from .errors import redact_network_message
from .tls import verify_response_certificate_pins, verify_websocket_certificate_pins
from .transport import PinnedDnsAsyncHTTPTransport


class SSEConnectionClosed(RuntimeError):
    error_code = "network.sse_closed"


class WebSocketConnectionError(RuntimeError):
    error_code = "network.websocket_error"


@dataclass(frozen=True)
class SSEEvent:
    event_id: str | None
    event_type: str
    data: str
    retry_ms: int | None = None


class SSEConnection:
    """Pull-based SSE handle; raw frame parsing remains delegated to httpx-sse."""

    def __init__(self, *, max_queue_size: int = 100) -> None:
        if not isinstance(max_queue_size, int) or max_queue_size <= 0:
            raise ValueError("max_queue_size must be a positive integer")
        self._queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=max_queue_size)
        self._last_event_id: str | None = None
        self._closed = False

    @property
    def last_event_id(self) -> str | None:
        return self._last_event_id

    async def feed(self, event: Mapping[str, object] | object) -> None:
        if self._closed:
            raise SSEConnectionClosed("network.sse_closed")
        normalized = self._normalize_event(event)
        await self._queue.put(normalized)
        if normalized.event_id:
            self._last_event_id = normalized.event_id

    async def receive(self, *, timeout_seconds: float | None = None) -> SSEEvent:
        if self._closed and self._queue.empty():
            raise SSEConnectionClosed("network.sse_closed")
        try:
            item = (
                await asyncio.wait_for(self._queue.get(), timeout_seconds)
                if timeout_seconds is not None
                else await self._queue.get()
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError("network.sse_receive_timeout") from exc
        if item is None:
            raise SSEConnectionClosed("network.sse_closed")
        return item

    def build_reconnect_headers(self) -> dict[str, str]:
        return {"Last-Event-ID": self._last_event_id} if self._last_event_id else {}

    async def consume(self, source) -> None:
        try:
            async for event in source:
                await self.feed(event)
        finally:
            await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Events already received before the peer closes remain available to
        # pull-based nodes. A later receive observes the closed state after
        # draining them, while an empty queue still receives an immediate wakeup.
        try:
            if self._queue.empty():
                self._queue.put_nowait(None)
        except asyncio.QueueFull:
            # A pending consumer can drain the queued event; its next receive
            # sees the closed flag and fails without waiting.
            pass

    @staticmethod
    def _normalize_event(event: Mapping[str, object] | object) -> SSEEvent:
        if isinstance(event, Mapping):
            event_id = event.get("id")
            event_type = event.get("event", "message")
            data = event.get("data", "")
            retry = event.get("retry")
        else:
            event_id = getattr(event, "id", None)
            event_type = getattr(event, "event", "message")
            data = getattr(event, "data", "")
            retry = getattr(event, "retry", None)
        if event_id is not None and not isinstance(event_id, str):
            raise ValueError("SSE event id must be a string")
        if not isinstance(event_type, str) or not event_type:
            event_type = "message"
        if not isinstance(data, str):
            data = str(data)
        if retry is not None and (
            not isinstance(retry, int) or isinstance(retry, bool) or retry < 0
        ):
            retry = None
        return SSEEvent(event_id=event_id, event_type=event_type, data=data, retry_ms=retry)


class WebSocketConnection:
    """Pull-based WebSocket handle with an explicit connection epoch."""

    def __init__(self, socket) -> None:
        self._socket = socket
        self._connection_epoch = 1
        self._closed = False

    @property
    def connection_epoch(self) -> int:
        return self._connection_epoch

    async def send(self, value: object) -> None:
        self._ensure_open()
        await self._socket.send(value)

    async def receive(self) -> object:
        self._ensure_open()
        return await self._socket.recv()

    async def ping(self, value: bytes | None = None) -> None:
        self._ensure_open()
        await self._socket.ping(value)

    async def replace_socket(self, socket) -> None:
        self._ensure_open()
        await self._socket.close()
        self._socket = socket
        self._connection_epoch += 1

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._socket.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise WebSocketConnectionError("network.websocket_closed")


def _consume_async_task_result(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except BaseException:
        return


class _AsyncHandleLoop:
    """Run one long-lived client handle on a dedicated asyncio loop thread."""

    def __init__(self, *, name: str) -> None:
        # Windows ProactorEventLoop 无法稳定承载“主线程运行本地 fixture、后台线程
        # 建立 websockets 客户端”的组合；长连接线程固定使用 selector loop，避免
        # 后台连接超时并留下 Proactor server transport 断言。
        self._loop = (
            asyncio.SelectorEventLoop()
            if sys.platform == "win32"
            else asyncio.new_event_loop()
        )
        self._ready = Event()
        self._closed = False
        self._lock = RLock()
        self._thread = Thread(target=self._run, daemon=True, name=name)
        self._thread.start()
        if not self._ready.wait(timeout=1):
            raise RuntimeError("network.long_connection_loop_start_timeout")

    def start_task(self, coroutine) -> object:
        with self._lock:
            if self._closed:
                raise RuntimeError("network.long_connection_loop_closed")
            return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def submit(self, coroutine, *, timeout_seconds: float | None = None):
        with self._lock:
            if self._closed:
                raise RuntimeError("network.long_connection_loop_closed")
            future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError("network.long_connection_operation_timeout") from exc

    def close(self, task_future: object | None = None) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if task_future is not None and hasattr(task_future, "cancel"):
            task_future.cancel()
            try:
                task_future.result(timeout=1)  # type: ignore[union-attr]
            except BaseException:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()


class SSEClientHandle:
    """Synchronous facade for a pull-based SSE stream."""

    def __init__(
        self,
        *,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        proxy: str | None = None,
        timeout_seconds: float = 30.0,
        max_queue_size: int = 100,
        access_policy: NetworkAccessPolicy | None = None,
        ssl_context: ssl.SSLContext | None = None,
        certificate_pins: tuple[str, ...] = (),
        resolved_target: ResolvedNetworkTarget | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("network.sse_url_required")
        if timeout_seconds <= 0:
            raise ValueError("network.sse_timeout_invalid")
        self.url = url.strip()
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._resolved_target = resolved_target or self._access_policy.validate_url(self.url)
        self.headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self.params = {str(key): str(value) for key, value in (params or {}).items()}
        self.proxy = proxy.strip() if isinstance(proxy, str) and proxy.strip() else None
        self.timeout_seconds = float(timeout_seconds)
        self.ssl_context = ssl_context
        self.certificate_pins = tuple(certificate_pins)
        self.connection = SSEConnection(max_queue_size=max_queue_size)
        self._loop = _AsyncHandleLoop(name="weconduct-sse-client")
        self._task_future = None
        self._ready = Event()
        self._lock = RLock()
        self._closed = False
        self._error: BaseException | None = None
        self._status_code: int | None = None
        self._response_headers: dict[str, str] = {}

    @property
    def last_event_id(self) -> str | None:
        return self.connection.last_event_id

    def start(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        with self._lock:
            if self._closed:
                raise RuntimeError("network.sse_closed")
            if self._task_future is None:
                self._task_future = self._loop.start_task(self._run())
        wait_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        if not self._ready.wait(timeout=wait_timeout):
            self.close()
            raise TimeoutError("network.sse_connect_timeout")
        if self._error is not None:
            self.close()
            raise RuntimeError(redact_network_message(str(self._error))) from self._error
        return {
            "status_code": self._status_code,
            "headers": dict(self._response_headers),
            "url": self.url,
        }

    def receive(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        self._ensure_started()
        if self._closed:
            raise RuntimeError("network.sse_closed")
        try:
            event = self._loop.submit(
                self.connection.receive(timeout_seconds=timeout_seconds),
                timeout_seconds=(timeout_seconds + 1 if timeout_seconds is not None else None),
            )
        except FutureTimeoutError as exc:
            raise TimeoutError("network.sse_receive_timeout") from exc
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "data": event.data,
            "retry_ms": event.retry_ms,
        }

    def reconnect_headers(self) -> dict[str, str]:
        return self.connection.build_reconnect_headers()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._loop.close(self._task_future)

    def _ensure_started(self) -> None:
        if self._closed:
            raise RuntimeError("network.sse_closed")
        if self._task_future is None:
            raise RuntimeError("network.sse_not_connected")

    async def _run(self) -> None:
        try:
            transport = PinnedDnsAsyncHTTPTransport(
                access_policy=self._access_policy,
                verify=self.ssl_context or True,
                proxy=self.proxy,
                trust_env=False,
                http2=True,
            )
            async with httpx.AsyncClient(
                transport=transport,
                timeout=self.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                extensions = (
                    {"weconduct.resolved_network_target": self._resolved_target}
                    if self._resolved_target is not None
                    else None
                )
                async with aconnect_sse(
                    client,
                    "GET",
                    self.url,
                    headers=self.headers,
                    params=self.params,
                    extensions=extensions,
                ) as source:
                    verify_response_certificate_pins(
                        source.response,
                        self.certificate_pins,
                    )
                    self._status_code = source.response.status_code
                    self._response_headers = {
                        str(key).lower(): str(value)
                        for key, value in source.response.headers.items()
                    }
                    self._ready.set()
                    async for event in source.aiter_sse():
                        await self.connection.feed(event)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            await self.connection.close()


class WebSocketClientHandle:
    """Synchronous facade for a pull-based WebSocket connection."""

    def __init__(
        self,
        *,
        url: str,
        headers: Mapping[str, str] | None = None,
        proxy: str | None = None,
        timeout_seconds: float = 30.0,
        subprotocols: list[str] | None = None,
        access_policy: NetworkAccessPolicy | None = None,
        ssl_context: ssl.SSLContext | None = None,
        certificate_pins: tuple[str, ...] = (),
        resolved_target: ResolvedNetworkTarget | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("network.websocket_url_required")
        if timeout_seconds <= 0:
            raise ValueError("network.websocket_timeout_invalid")
        self.url = url.strip()
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._resolved_target = resolved_target or self._access_policy.validate_url(
            self.url,
            allowed_schemes=frozenset({"ws", "wss"}),
        )
        self.headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self.proxy = proxy.strip() if isinstance(proxy, str) and proxy.strip() else None
        self.timeout_seconds = float(timeout_seconds)
        self.subprotocols = list(subprotocols or [])
        self.ssl_context = ssl_context
        self.certificate_pins = tuple(certificate_pins)
        self.connection: WebSocketConnection | None = None
        self._loop = _AsyncHandleLoop(name="weconduct-websocket-client")
        self._task_future = None
        self._ready = Event()
        self._closed_event: asyncio.Event | None = None
        self._lock = RLock()
        self._closed = False
        self._error: BaseException | None = None

    def start(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        with self._lock:
            if self._closed:
                raise RuntimeError("network.websocket_closed")
            if self._task_future is None:
                self._task_future = self._loop.start_task(self._run())
        wait_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        if not self._ready.wait(timeout=wait_timeout):
            self.close()
            raise TimeoutError("network.websocket_connect_timeout")
        if self._error is not None:
            self.close()
            raise RuntimeError(redact_network_message(str(self._error))) from self._error
        return {"status": "connected", "url": self.url}

    def send(self, value: object) -> None:
        connection = self._ensure_connection()
        self._loop.submit(connection.send(value), timeout_seconds=self.timeout_seconds)

    def receive(self, *, timeout_seconds: float | None = None) -> object:
        connection = self._ensure_connection()
        try:
            return self._loop.submit(
                self._receive_async(connection, timeout_seconds),
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError as exc:
            if str(exc) == "network.long_connection_operation_timeout":
                raise TimeoutError("network.websocket_receive_timeout") from exc
            raise

    def ping(self, value: bytes | None = None) -> None:
        connection = self._ensure_connection()
        self._loop.submit(connection.ping(value), timeout_seconds=self.timeout_seconds)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self.connection is not None:
            try:
                self._loop.submit(self._close_async(), timeout_seconds=1)
            except BaseException:
                pass
        self._loop.close(self._task_future)

    def _ensure_connection(self) -> WebSocketConnection:
        if self._closed:
            raise RuntimeError("network.websocket_closed")
        if self.connection is None:
            raise RuntimeError("network.websocket_not_connected")
        return self.connection

    async def _run(self) -> None:
        socket = None
        try:
            connect_url, headers, connect_options = self._build_connect_arguments()
            socket = await websockets.connect(
                connect_url,
                additional_headers=headers or None,
                subprotocols=self.subprotocols or None,
                proxy=self.proxy,
                open_timeout=self.timeout_seconds,
                **connect_options,
            )
            verify_websocket_certificate_pins(socket, self.certificate_pins)
            self.connection = WebSocketConnection(socket)
            self._closed_event = asyncio.Event()
            self._ready.set()
            await self._closed_event.wait()
        except asyncio.CancelledError:
            if socket is not None:
                await socket.close()
            raise
        except BaseException as exc:
            if socket is not None:
                await socket.close()
            self._error = exc
            self._ready.set()

    def _build_connect_arguments(self) -> tuple[str, dict[str, str], dict[str, object]]:
        parsed = urlsplit(self.url)
        headers = dict(self.headers)
        options: dict[str, object] = {}
        if parsed.scheme == "wss" and self.ssl_context is not None:
            options["ssl"] = self.ssl_context
        if self._resolved_target is None:
            return self.url, headers, options
        connect_host = self._resolved_target.addresses[0]
        original_host = parsed.hostname or ""
        if self.proxy:
            authority = original_host
            default_port = 443 if parsed.scheme == "wss" else 80
            if self._resolved_target.port != default_port:
                authority = f"{authority}:{self._resolved_target.port}"
            headers.setdefault("Host", authority)
            pinned_authority = connect_host
            if ":" in connect_host:
                pinned_authority = f"[{connect_host}]"
            if self._resolved_target.port != default_port:
                pinned_authority = f"{pinned_authority}:{self._resolved_target.port}"
            connect_url = urlunsplit(
                (parsed.scheme, pinned_authority, parsed.path, parsed.query, parsed.fragment)
            )
            if parsed.scheme == "wss":
                options["server_hostname"] = original_host
            return connect_url, headers, options
        options["host"] = connect_host
        options["port"] = self._resolved_target.port
        if parsed.scheme == "wss":
            options["server_hostname"] = original_host
        return self.url, headers, options

    async def _close_async(self) -> None:
        if self._closed_event is not None:
            self._closed_event.set()
        if self.connection is not None:
            await self.connection.close()

    @staticmethod
    async def _receive_async(
        connection: WebSocketConnection,
        timeout_seconds: float | None,
    ) -> object:
        if timeout_seconds is None:
            return await connection.receive()
        task = asyncio.create_task(connection.receive())
        done, pending = await asyncio.wait({task}, timeout=timeout_seconds)
        if not done:
            # websockets.recv() may spend a long time unwinding cancellation on
            # Windows. Leave this single pending receive attached to the loop;
            # close() will terminate the connection and drain it. The public
            # operation still returns at the configured deadline.
            for pending_task in pending:
                pending_task.add_done_callback(_consume_async_task_result)
            raise TimeoutError("network.websocket_receive_timeout")
        return await task
