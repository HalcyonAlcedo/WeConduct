from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import json
import ssl
import sys
from threading import Event, RLock, Thread
from typing import Awaitable, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx
from httpx_sse import aconnect_sse
import websockets

from .access_policy import NetworkAccessPolicy, ResolvedNetworkTarget
from .errors import redact_network_message
from .tls import verify_response_certificate_pins, verify_websocket_certificate_pins
from .transport import PinnedDnsAsyncHTTPTransport
from .queue import (
    BoundedMessageQueue,
    ExecutionActivationQueue,
    QueueBackpressureError,
    QueueClosedError,
    QueueCancelledError,
    SequenceAllocator,
)


class SSEConnectionClosed(RuntimeError):
    error_code = "network.sse_closed"


class WebSocketConnectionError(RuntimeError):
    error_code = "network.websocket_error"


ReconnectCallback = Callable[["WebSocketConnection"], Awaitable[None]]


def _serialize_websocket_message(value: object) -> object:
    """将节点中的结构化值编码为 WebSocket 文本帧。"""
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        return value
    if value is None or isinstance(value, (bool, int, float, list, tuple, Mapping)):
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("network.websocket_message_invalid") from exc
    raise ValueError("network.websocket_message_invalid")


def _safe_reconnect_reason(error: BaseException, fallback: str) -> str:
    """只保留结构化网络错误码，避免将 URL 或凭据写入 Debug Trace。"""
    error_code = getattr(error, "error_code", None)
    if isinstance(error_code, str) and error_code.strip():
        return error_code.strip()
    text = str(error).strip()
    return text if text.startswith("network.") else fallback


@dataclass(frozen=True)
class SSEEvent:
    event_id: str | None
    event_type: str
    data: str
    retry_ms: int | None = None


class SSEConnection:
    """Pull-based SSE handle; raw frame parsing remains delegated to httpx-sse."""

    def __init__(
        self,
        *,
        max_queue_size: int = 100,
        backpressure_policy: str = "fail_stream",
        connection_id: str | None = None,
        connection_epoch: int = 1,
        sequence_allocator: SequenceAllocator | None = None,
        activation_sink: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        allocator = sequence_allocator or SequenceAllocator()
        self._queue = BoundedMessageQueue(
            maxsize=max_queue_size,
            backpressure_policy=backpressure_policy,
            sequence_allocator=allocator,
        )
        self._activation_queue = ExecutionActivationQueue(
            maxsize=max_queue_size + 1,
            backpressure_policy=backpressure_policy,
            sequence_allocator=allocator,
        )
        self._connection_id = connection_id
        self._connection_epoch = connection_epoch
        self._last_event_id: str | None = None
        self._last_retry_ms: int | None = None
        self._last_received_record: dict[str, object] | None = None
        self._reconnect_reason: str | None = None
        self._terminal_state: str | None = None
        self._reconnecting = False
        self._closed = False
        self._activation_sink = activation_sink

    @property
    def last_event_id(self) -> str | None:
        return self._last_event_id

    @property
    def activation_queue(self) -> ExecutionActivationQueue:
        return self._activation_queue

    @property
    def queue_depth(self) -> int:
        return self._queue.size

    @property
    def dropped_count(self) -> int:
        return self._queue.dropped_count

    @property
    def queue_status(self) -> dict[str, object]:
        return {
            "depth": self.queue_depth,
            "dropped_count": self.dropped_count,
            "drop_events": self._queue.drop_events,
            "closed": self._closed,
            "cancelled": self._queue.cancelled,
            "backpressure_policy": self._queue.backpressure_policy,
            "connection_id": self._connection_id,
            "connection_epoch": self._connection_epoch,
            "reconnect_count": max(self._connection_epoch - 1, 0),
            "reconnect_reason": self._reconnect_reason,
            "connection_state": (
                self._terminal_state
                if self._terminal_state is not None
                else "closed"
                if self._closed
                else "reconnecting"
                if self._reconnecting
                else "connected"
            ),
        }

    @property
    def last_received_record(self) -> dict[str, object] | None:
        return dict(self._last_received_record) if self._last_received_record is not None else None

    async def advance_epoch(self) -> int:
        """在保持队列和 Last-Event-ID 的前提下开始下一次连接。"""
        if self._closed:
            raise SSEConnectionClosed("network.sse_closed")
        self._connection_epoch += 1
        return self._connection_epoch

    def set_reconnect_reason(self, reason: str | None) -> None:
        self._reconnect_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None

    def mark_failed(self) -> None:
        """记录不可恢复的异常终态，供 Debug Trace 区分主动关闭。"""
        self._reconnecting = False
        self._terminal_state = "failed"

    def mark_reconnecting(self) -> None:
        if not self._closed and self._terminal_state is None:
            self._reconnecting = True

    def mark_connected(self) -> None:
        if not self._closed and self._terminal_state is None:
            self._reconnecting = False

    @property
    def retry_delay_seconds(self) -> float | None:
        return self._last_retry_ms / 1000 if self._last_retry_ms is not None else None

    async def feed(self, event: Mapping[str, object] | object) -> None:
        if self._closed:
            raise SSEConnectionClosed("network.sse_closed")
        normalized = self._normalize_event(event)
        try:
            message = await self._queue.put(
                normalized,
                connection_id=self._connection_id,
                connection_epoch=self._connection_epoch,
            )
        except (QueueBackpressureError, QueueClosedError, QueueCancelledError) as exc:
            raise SSEConnectionClosed(str(exc)) from exc
        if message is not None:
            activation = await self._activation_queue.activate(
                {
                    "event_kind": "sse.message",
                    "message": message,
                },
                connection_id=self._connection_id,
                connection_epoch=self._connection_epoch,
                sequence_id=message["sequence_id"],
            )
            if activation is not None and self._activation_sink is not None:
                self._activation_sink(activation)
        if normalized.event_id:
            self._last_event_id = normalized.event_id
        if normalized.retry_ms is not None:
            self._last_retry_ms = normalized.retry_ms

    async def receive(self, *, timeout_seconds: float | None = None) -> SSEEvent:
        try:
            item = await self._queue.get(timeout_seconds=timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError("network.sse_receive_timeout") from exc
        except (QueueClosedError, QueueCancelledError) as exc:
            raise SSEConnectionClosed("network.sse_closed")
        self._last_received_record = dict(item)
        return item["payload"]

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
        self._queue.close()
        self._activation_queue.close()

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

    def __init__(
        self,
        socket,
        *,
        max_queue_size: int = 100,
        backpressure_policy: str = "fail_stream",
        connection_id: str | None = None,
        sequence_allocator: SequenceAllocator | None = None,
        activation_sink: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._socket = socket
        self._connection_epoch = 1
        self._closed = False
        self._connection_id = connection_id
        self._activation_sink = activation_sink
        allocator = sequence_allocator or SequenceAllocator()
        self._queue = BoundedMessageQueue(
            maxsize=max_queue_size,
            backpressure_policy=backpressure_policy,
            sequence_allocator=allocator,
        )
        self._activation_queue = ExecutionActivationQueue(
            maxsize=max_queue_size + 1,
            backpressure_policy=backpressure_policy,
            sequence_allocator=allocator,
        )
        self._receiver_task: asyncio.Task[None] | None = None
        self._receiver_error: BaseException | None = None
        self._last_received_record: dict[str, object] | None = None
        self._reconnect_reason: str | None = None
        self._terminal_state: str | None = None
        self._reconnecting = False
        self._closed_event = asyncio.Event()

    @property
    def connection_epoch(self) -> int:
        return self._connection_epoch

    @property
    def activation_queue(self) -> ExecutionActivationQueue:
        return self._activation_queue

    @property
    def queue_depth(self) -> int:
        return self._queue.size

    @property
    def dropped_count(self) -> int:
        return self._queue.dropped_count

    @property
    def queue_status(self) -> dict[str, object]:
        return {
            "depth": self.queue_depth,
            "dropped_count": self.dropped_count,
            "drop_events": self._queue.drop_events,
            "closed": self._closed,
            "cancelled": self._queue.cancelled,
            "backpressure_policy": self._queue.backpressure_policy,
            "connection_id": self._connection_id,
            "connection_epoch": self._connection_epoch,
            "reconnect_count": max(self._connection_epoch - 1, 0),
            "reconnect_reason": self._reconnect_reason,
            "connection_state": (
                self._terminal_state
                if self._terminal_state is not None
                else "closed"
                if self._closed
                else "reconnecting"
                if self._reconnecting
                else "disconnected"
                if self._receiver_error is not None
                else "connected"
            ),
        }

    @property
    def receiver_error(self) -> BaseException | None:
        return self._receiver_error

    @property
    def last_received_record(self) -> dict[str, object] | None:
        return dict(self._last_received_record) if self._last_received_record is not None else None

    async def wait_closed(self) -> None:
        await self._closed_event.wait()

    async def start_receiver(self) -> None:
        self._ensure_open()
        if self._receiver_task is None:
            self._receiver_task = asyncio.create_task(self._receive_loop())

    async def send(self, value: object) -> None:
        self._ensure_open()
        await self._socket.send(value)

    async def receive(self, *, timeout_seconds: float | None = None) -> object:
        # 对端终止或重连耗尽后，已入队的消息仍须可被拉取；空队列才报告关闭。
        if self._closed and self._queue.size == 0:
            self._ensure_open()
        if self._receiver_task is not None:
            try:
                message = await self._queue.get(timeout_seconds=timeout_seconds)
            except TimeoutError as exc:
                raise TimeoutError("network.websocket_receive_timeout") from exc
            except (QueueClosedError, QueueCancelledError) as exc:
                raise WebSocketConnectionError("network.websocket_closed") from exc
            self._last_received_record = dict(message)
            return message["payload"]
        if self._closed and self._queue.size:
            try:
                message = await self._queue.get(timeout_seconds=timeout_seconds)
            except (QueueClosedError, QueueCancelledError) as exc:
                raise WebSocketConnectionError("network.websocket_closed") from exc
            self._last_received_record = dict(message)
            return message["payload"]
        self._ensure_open()
        return await self._socket.recv()

    async def ping(self, value: bytes | None = None) -> None:
        self._ensure_open()
        await self._socket.ping(value)

    async def replace_socket(self, socket) -> None:
        self._ensure_open()
        if self._receiver_task is not None:
            self._receiver_task.cancel()
            await asyncio.gather(self._receiver_task, return_exceptions=True)
            self._receiver_task = None
        await self._socket.close()
        self._socket = socket
        self._connection_epoch += 1
        self._queue.reopen()
        self._activation_queue.reopen()
        self._receiver_error = None
        self._terminal_state = None
        self._closed_event = asyncio.Event()

    def set_reconnect_reason(self, reason: str | None) -> None:
        self._reconnect_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None

    def mark_failed(self) -> None:
        """记录不可恢复的异常终态，供 Debug Trace 区分主动关闭。"""
        self._reconnecting = False
        self._terminal_state = "failed"

    def mark_reconnecting(self) -> None:
        if not self._closed and self._terminal_state is None:
            self._reconnecting = True

    def mark_connected(self) -> None:
        if not self._closed and self._terminal_state is None:
            self._reconnecting = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receiver_task is not None:
            self._receiver_task.cancel()
            await asyncio.gather(self._receiver_task, return_exceptions=True)
            self._receiver_task = None
        self._queue.close()
        self._activation_queue.close()
        self._closed_event.set()
        await self._socket.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise WebSocketConnectionError("network.websocket_closed")

    async def _receive_loop(self) -> None:
        try:
            while not self._closed:
                value = await self._socket.recv()
                message = await self._queue.put(
                    value,
                    connection_id=self._connection_id,
                    connection_epoch=self._connection_epoch,
                )
                if message is not None:
                    activation = await self._activation_queue.activate(
                        {
                            "event_kind": "websocket.message",
                            "message": message,
                        },
                        connection_id=self._connection_id,
                        connection_epoch=self._connection_epoch,
                        sequence_id=message["sequence_id"],
                    )
                    if activation is not None and self._activation_sink is not None:
                        self._activation_sink(activation)
        except asyncio.CancelledError:
            raise
        except (QueueBackpressureError, QueueClosedError, QueueCancelledError) as exc:
            self._receiver_error = WebSocketConnectionError(str(exc))
            self._queue.close()
            self._activation_queue.close()
            self._closed_event.set()
        except BaseException as exc:
            if not self._closed:
                self._receiver_error = exc
                # 接收线程已终止时必须关闭两个队列，唤醒正在等待消息的
                # pull/执行激活消费者；连接对象仍保持 disconnected 状态，
                # 由上层 WebSocketClientHandle 决定是否重连。
                self._queue.close()
                self._activation_queue.close()
                self._closed_event.set()


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
        backpressure_policy: str = "fail_stream",
        connection_id: str | None = None,
        access_policy: NetworkAccessPolicy | None = None,
        ssl_context: ssl.SSLContext | None = None,
        certificate_pins: tuple[str, ...] = (),
        resolved_target: ResolvedNetworkTarget | None = None,
        max_reconnect_attempts: int = 0,
        reconnect_delay_seconds: float = 0.5,
        reconnect_max_delay_seconds: float = 30.0,
        sequence_allocator: SequenceAllocator | None = None,
        activation_sink: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("network.sse_url_required")
        if timeout_seconds <= 0:
            raise ValueError("network.sse_timeout_invalid")
        if (
            not isinstance(max_reconnect_attempts, int)
            or isinstance(max_reconnect_attempts, bool)
            or max_reconnect_attempts < 0
        ):
            raise ValueError("network.sse_reconnect_attempts_invalid")
        if (
            not isinstance(reconnect_delay_seconds, (int, float))
            or isinstance(reconnect_delay_seconds, bool)
            or reconnect_delay_seconds < 0
        ):
            raise ValueError("network.sse_reconnect_delay_invalid")
        if (
            not isinstance(reconnect_max_delay_seconds, (int, float))
            or isinstance(reconnect_max_delay_seconds, bool)
            or reconnect_max_delay_seconds < reconnect_delay_seconds
        ):
            raise ValueError("network.sse_reconnect_max_delay_invalid")
        self.url = url.strip()
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._resolved_target = resolved_target or self._access_policy.validate_url(self.url)
        self.headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self.params = {str(key): str(value) for key, value in (params or {}).items()}
        self.proxy = proxy.strip() if isinstance(proxy, str) and proxy.strip() else None
        self.timeout_seconds = float(timeout_seconds)
        self.backpressure_policy = backpressure_policy
        self.connection_id = connection_id
        self.ssl_context = ssl_context
        self.certificate_pins = tuple(certificate_pins)
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_seconds = float(reconnect_delay_seconds)
        self.reconnect_max_delay_seconds = float(reconnect_max_delay_seconds)
        self.sequence_allocator = sequence_allocator or SequenceAllocator()
        self.connection = SSEConnection(
            max_queue_size=max_queue_size,
            backpressure_policy=backpressure_policy,
            connection_id=connection_id,
            sequence_allocator=self.sequence_allocator,
            activation_sink=activation_sink,
        )
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

    @property
    def queue_depth(self) -> int:
        return self.connection.queue_depth

    @property
    def dropped_count(self) -> int:
        return self.connection.dropped_count

    @property
    def queue_status(self) -> dict[str, object]:
        return self.connection.queue_status

    @property
    def activation_queue(self) -> ExecutionActivationQueue:
        return self.connection.activation_queue

    @property
    def last_received_record(self) -> dict[str, object] | None:
        return self.connection.last_received_record

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

    def wait_next_activation(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        self._ensure_started()
        if self._closed:
            raise RuntimeError("network.sse_closed")
        return self._loop.submit(
            self.connection.activation_queue.wait_next(timeout_seconds=timeout_seconds),
            timeout_seconds=(timeout_seconds + 1 if timeout_seconds is not None else None),
        )

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
        reconnect_attempt = 0
        try:
            while not self._closed:
                try:
                    await self._run_once(reconnect_attempt > 0)
                except asyncio.CancelledError:
                    raise
                except BaseException as exc:
                    # 队列背压/取消是终态，不能用重连掩盖数据丢失或取消。
                    if self._closed or str(exc).startswith("network.queue_"):
                        self._error = exc
                        break
                    self.connection.set_reconnect_reason(
                        _safe_reconnect_reason(exc, "network.sse_reconnect_failed")
                    )
                    if reconnect_attempt >= self.max_reconnect_attempts:
                        self._error = exc
                        self._ready.set()
                        break
                else:
                    if not self._closed and reconnect_attempt < self.max_reconnect_attempts:
                        # httpx-sse 将对端正常结束也表现为迭代器完成；对自动重连
                        # 来说这同样是一次可观测的断开原因。
                        self.connection.set_reconnect_reason("network.sse_stream_closed")
                if self._closed or reconnect_attempt >= self.max_reconnect_attempts:
                    break
                self.connection.mark_reconnecting()
                reconnect_attempt += 1
                delay = self._next_reconnect_delay(reconnect_attempt)
                if delay:
                    await asyncio.sleep(delay)
                if not self._closed:
                    await self.connection.advance_epoch()
        finally:
            if self._error is not None:
                self.connection.mark_failed()
            await self.connection.close()

    async def _run_once(self, reconnecting: bool) -> None:
        transport = PinnedDnsAsyncHTTPTransport(
            access_policy=self._access_policy,
            verify=self.ssl_context or True,
            proxy=self.proxy,
            trust_env=False,
            http2=True,
        )
        request_headers = dict(self.headers)
        if reconnecting:
            request_headers.update(self.connection.build_reconnect_headers())
        async with httpx.AsyncClient(
            transport=transport,
            timeout=self.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            request_url = httpx.URL(self.url)
            if self.params:
                merged_params = dict(request_url.params)
                merged_params.update(self.params)
                request_url = request_url.copy_with(params=merged_params)
            extensions = (
                {"weconduct.resolved_network_target": self._resolved_target}
                if self._resolved_target is not None
                else None
            )
            async with aconnect_sse(
                client,
                "GET",
                str(request_url),
                headers=request_headers,
                extensions=extensions,
            ) as source:
                verify_response_certificate_pins(source.response, self.certificate_pins)
                self._status_code = source.response.status_code
                self._response_headers = {
                    str(key).lower(): str(value)
                    for key, value in source.response.headers.items()
                }
                self.connection.mark_connected()
                self._ready.set()
                async for event in source.aiter_sse():
                    await self.connection.feed(event)

    def _next_reconnect_delay(self, attempt: int) -> float:
        server_delay = self.connection.retry_delay_seconds
        if server_delay is not None:
            return min(self.reconnect_max_delay_seconds, server_delay)
        return min(
            self.reconnect_max_delay_seconds,
            self.reconnect_delay_seconds * (2 ** max(attempt - 1, 0)),
        )


class WebSocketClientHandle:
    """Synchronous facade for a pull-based WebSocket connection."""

    def __init__(
        self,
        *,
        url: str,
        headers: Mapping[str, str] | None = None,
        proxy: str | None = None,
        timeout_seconds: float = 30.0,
        max_queue_size: int = 100,
        backpressure_policy: str = "fail_stream",
        connection_id: str | None = None,
        subprotocols: list[str] | None = None,
        access_policy: NetworkAccessPolicy | None = None,
        ssl_context: ssl.SSLContext | None = None,
        certificate_pins: tuple[str, ...] = (),
        resolved_target: ResolvedNetworkTarget | None = None,
        max_reconnect_attempts: int = 0,
        reconnect_delay_seconds: float = 0.5,
        reconnect_max_delay_seconds: float = 30.0,
        sequence_allocator: SequenceAllocator | None = None,
        activation_sink: Callable[[dict[str, object]], None] | None = None,
        reconnect_callback: ReconnectCallback | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("network.websocket_url_required")
        if timeout_seconds <= 0:
            raise ValueError("network.websocket_timeout_invalid")
        if (
            not isinstance(max_reconnect_attempts, int)
            or isinstance(max_reconnect_attempts, bool)
            or max_reconnect_attempts < 0
        ):
            raise ValueError("network.websocket_reconnect_attempts_invalid")
        if (
            not isinstance(reconnect_delay_seconds, (int, float))
            or isinstance(reconnect_delay_seconds, bool)
            or reconnect_delay_seconds < 0
        ):
            raise ValueError("network.websocket_reconnect_delay_invalid")
        if (
            not isinstance(reconnect_max_delay_seconds, (int, float))
            or isinstance(reconnect_max_delay_seconds, bool)
            or reconnect_max_delay_seconds < reconnect_delay_seconds
        ):
            raise ValueError("network.websocket_reconnect_max_delay_invalid")
        self.url = url.strip()
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._resolved_target = resolved_target or self._access_policy.validate_url(
            self.url,
            allowed_schemes=frozenset({"ws", "wss"}),
        )
        self.headers = {str(key): str(value) for key, value in (headers or {}).items()}
        self.proxy = proxy.strip() if isinstance(proxy, str) and proxy.strip() else None
        self.timeout_seconds = float(timeout_seconds)
        self.max_queue_size = max_queue_size
        self.backpressure_policy = backpressure_policy
        self.connection_id = connection_id
        self.subprotocols = list(subprotocols or [])
        self.ssl_context = ssl_context
        self.certificate_pins = tuple(certificate_pins)
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_seconds = float(reconnect_delay_seconds)
        self.reconnect_max_delay_seconds = float(reconnect_max_delay_seconds)
        self.sequence_allocator = sequence_allocator or SequenceAllocator()
        self.activation_sink = activation_sink
        self.connection: WebSocketConnection | None = None
        self._loop = _AsyncHandleLoop(name="weconduct-websocket-client")
        self._task_future = None
        self._ready = Event()
        self._closed_event: asyncio.Event | None = None
        self._connection_state_event: asyncio.Event | None = None
        self._lock = RLock()
        self._closed = False
        self._error: BaseException | None = None
        self._connected_once = False
        self._reconnect_callback = reconnect_callback

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
        if self._error is not None and not self._connected_once:
            self.close()
            raise RuntimeError(redact_network_message(str(self._error))) from self._error
        return {"status": "connected", "url": self.url}

    def send(self, value: object) -> None:
        connection = self._ensure_connection()
        serialized_value = _serialize_websocket_message(value)
        self._loop.submit(connection.send(serialized_value), timeout_seconds=self.timeout_seconds)

    @property
    def queue_depth(self) -> int:
        return self._ensure_connection().queue_depth

    @property
    def dropped_count(self) -> int:
        return self._ensure_connection().dropped_count

    @property
    def queue_status(self) -> dict[str, object]:
        return self._ensure_connection().queue_status

    @property
    def activation_queue(self) -> ExecutionActivationQueue:
        return self._ensure_connection().activation_queue

    @property
    def last_received_record(self) -> dict[str, object] | None:
        return self._ensure_connection().last_received_record

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

    def wait_next_activation(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        connection = self._ensure_connection()
        try:
            return self._loop.submit(
                self._wait_next_activation_async(connection, timeout_seconds),
                timeout_seconds=(timeout_seconds + 1 if timeout_seconds is not None else None),
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

    def set_reconnect_callback(self, callback: ReconnectCallback | None) -> None:
        """设置传输重连后的协议恢复回调。"""
        if callback is not None and not callable(callback):
            raise TypeError("network.websocket_reconnect_callback_invalid")
        lock = getattr(self, "_lock", None)
        if lock is None:
            self._reconnect_callback = callback
            return
        with lock:
            self._reconnect_callback = callback

    def _ensure_connection(self) -> WebSocketConnection:
        if self._closed:
            raise RuntimeError("network.websocket_closed")
        if self.connection is None:
            raise RuntimeError("network.websocket_not_connected")
        return self.connection

    async def _run(self) -> None:
        reconnect_attempt = 0
        self._connection_state_event = asyncio.Event()
        try:
            while not self._closed:
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
                    if self.connection is None:
                        self.connection = WebSocketConnection(
                            socket,
                            max_queue_size=self.max_queue_size,
                            backpressure_policy=self.backpressure_policy,
                            connection_id=self.connection_id,
                            sequence_allocator=self.sequence_allocator,
                            activation_sink=self.activation_sink,
                        )
                    else:
                        await self.connection.replace_socket(socket)
                    await self.connection.start_receiver()
                    if self._connected_once and self._reconnect_callback is not None:
                        await self._reconnect_callback(self.connection)
                    self.connection.mark_connected()
                    self._connected_once = True
                    self._connection_state_event.set()
                    self._ready.set()
                    await self.connection.wait_closed()
                    if self._closed:
                        break
                    receiver_error = self.connection.receiver_error
                    if receiver_error is not None and str(receiver_error).startswith("network.queue_"):
                        self._error = receiver_error
                        self._connection_state_event.set()
                        break
                    if receiver_error is not None:
                        self.connection.set_reconnect_reason(
                            _safe_reconnect_reason(receiver_error, "network.websocket_reconnect_failed")
                        )
                    if reconnect_attempt >= self.max_reconnect_attempts:
                        if receiver_error is not None:
                            self._error = receiver_error
                        self._connection_state_event.set()
                        break
                    # The connection queue is closed while the receiver unwinds.
                    # Keep receive callers suspended until replacement succeeds or
                    # the reconnect loop reaches a terminal state.
                    self.connection.mark_reconnecting()
                    self._connection_state_event.clear()
                except asyncio.CancelledError:
                    if socket is not None:
                        await socket.close()
                    raise
                except BaseException as exc:
                    if socket is not None:
                        await socket.close()
                    if self.connection is not None and not self._closed:
                        self.connection.set_reconnect_reason(
                            _safe_reconnect_reason(exc, "network.websocket_reconnect_failed")
                        )
                    if self._closed or reconnect_attempt >= self.max_reconnect_attempts:
                        self._error = exc
                        self._connection_state_event.set()
                        self._ready.set()
                        break
                    if self.connection is not None:
                        self.connection.mark_reconnecting()
                if self._closed or reconnect_attempt >= self.max_reconnect_attempts:
                    break
                reconnect_attempt += 1
                delay = min(
                    self.reconnect_max_delay_seconds,
                    self.reconnect_delay_seconds * (2 ** max(reconnect_attempt - 1, 0)),
                )
                if delay:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        finally:
            if self._connection_state_event is not None:
                self._connection_state_event.set()
            if self.connection is not None and self._error is not None:
                self.connection.mark_failed()
            if self.connection is not None and not self.connection.queue_status.get("closed"):
                await self.connection.close()

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

    async def _receive_async(
        self,
        connection: WebSocketConnection,
        timeout_seconds: float | None,
    ) -> object:
        deadline = (
            None
            if timeout_seconds is None
            else asyncio.get_running_loop().time() + timeout_seconds
        )
        while True:
            remaining = (
                None
                if deadline is None
                else max(deadline - asyncio.get_running_loop().time(), 0.0)
            )
            try:
                return await connection.receive(timeout_seconds=remaining)
            except WebSocketConnectionError:
                # A receiver error closes the queue before the reconnect loop can
                # install the replacement socket. Wait for that state transition
                # instead of exposing a transient websocket_closed to callers.
                if self._closed or self._error is not None:
                    raise
                if connection.queue_status.get("connection_state") == "connected":
                    # receiver_error is assigned immediately before queue.close();
                    # yield once so that the receiver and reconnect loop can finish
                    # the state transition instead of spinning on an open queue.
                    await asyncio.sleep(0)
                    continue
                state_event = self._connection_state_event
                if state_event is None:
                    raise
                state_event.clear()
                if self._closed or self._error is not None:
                    raise
                if connection.queue_status.get("connection_state") == "connected":
                    continue
                if remaining is not None:
                    if remaining <= 0:
                        raise TimeoutError("network.websocket_receive_timeout")
                    try:
                        await asyncio.wait_for(state_event.wait(), remaining)
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError("network.websocket_receive_timeout") from exc
                else:
                    await state_event.wait()

    async def _wait_next_activation_async(
        self,
        connection: WebSocketConnection,
        timeout_seconds: float | None,
    ) -> dict[str, object]:
        deadline = (
            None
            if timeout_seconds is None
            else asyncio.get_running_loop().time() + timeout_seconds
        )
        while True:
            remaining = (
                None
                if deadline is None
                else max(deadline - asyncio.get_running_loop().time(), 0.0)
            )
            try:
                return await connection.activation_queue.wait_next(timeout_seconds=remaining)
            except TimeoutError as exc:
                raise TimeoutError("network.websocket_receive_timeout") from exc
            except (QueueClosedError, QueueCancelledError):
                if self._closed or self._error is not None:
                    raise WebSocketConnectionError("network.websocket_closed")
                if connection.queue_status.get("connection_state") == "connected":
                    await asyncio.sleep(0)
                    continue
                state_event = self._connection_state_event
                if state_event is None:
                    raise WebSocketConnectionError("network.websocket_closed")
                state_event.clear()
                if self._closed or self._error is not None:
                    raise WebSocketConnectionError("network.websocket_closed")
                if connection.queue_status.get("connection_state") == "connected":
                    continue
                if remaining is not None:
                    if remaining <= 0:
                        raise TimeoutError("network.websocket_receive_timeout")
                    try:
                        await asyncio.wait_for(state_event.wait(), remaining)
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError("network.websocket_receive_timeout") from exc
                else:
                    await state_event.wait()
