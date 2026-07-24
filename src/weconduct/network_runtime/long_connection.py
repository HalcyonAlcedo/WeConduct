from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping


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
        await self._queue.put(None)

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
