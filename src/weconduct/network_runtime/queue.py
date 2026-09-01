from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition, Lock
from time import monotonic
from typing import Any


class QueueBackpressureError(RuntimeError):
    pass


class QueueClosedError(RuntimeError):
    pass


class QueueCancelledError(RuntimeError):
    pass


_VALID_POLICIES = {"fail_stream", "drop_oldest", "drop_newest", "close_connection"}


class SequenceAllocator:
    """为同一执行会话中的多个网络队列分配单调递增序号。"""

    def __init__(self, *, initial: int = 0) -> None:
        if not isinstance(initial, int) or isinstance(initial, bool) or initial < 0:
            raise ValueError("initial sequence must be a non-negative integer")
        self._value = initial
        self._lock = Lock()

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    def observe(self, sequence_id: int) -> int:
        if not isinstance(sequence_id, int) or isinstance(sequence_id, bool) or sequence_id <= 0:
            raise ValueError("sequence_id must be a positive integer")
        with self._lock:
            self._value = max(self._value, sequence_id)
            return self._value


def _record(
    *,
    sequence_id: int,
    payload: Any,
    connection_id: str | None,
    connection_epoch: int | None,
) -> dict[str, Any]:
    return {
        "sequence_id": sequence_id,
        "payload": payload,
        "connection_id": connection_id,
        "connection_epoch": connection_epoch,
        "enqueued_at": monotonic(),
    }


@dataclass
class _DropStats:
    count: int = 0


class BoundedMessageQueue:
    def __init__(
        self,
        *,
        maxsize: int,
        backpressure_policy: str = "fail_stream",
        sequence_allocator: SequenceAllocator | None = None,
    ) -> None:
        if not isinstance(maxsize, int) or maxsize <= 0:
            raise ValueError("maxsize must be a positive integer")
        if backpressure_policy not in _VALID_POLICIES:
            raise ValueError("unknown backpressure_policy")
        self._maxsize = maxsize
        self._backpressure_policy = backpressure_policy
        self._items: deque[dict[str, Any]] = deque()
        self._condition = __import__("asyncio").Condition()
        self._closed = False
        self._cancelled = False
        self._sequence_allocator = sequence_allocator or SequenceAllocator()
        self._dropped = _DropStats()
        # Drop events are diagnostic metadata only. Keep a bounded recent
        # window so a sustained flood cannot turn the diagnostic path into an
        # unbounded memory sink.
        self._drop_events: deque[dict[str, Any]] = deque(
            maxlen=max(32, min(maxsize * 4, 4096))
        )

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def dropped_count(self) -> int:
        return self._dropped.count

    @property
    def backpressure_policy(self) -> str:
        return self._backpressure_policy

    @property
    def drop_events(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self._drop_events]

    @property
    def size(self) -> int:
        return len(self._items)

    async def put(
        self,
        payload: Any,
        *,
        connection_id: str | None = None,
        connection_epoch: int | None = None,
        sequence_id: int | None = None,
    ) -> dict[str, Any] | None:
        async with self._condition:
            self._ensure_open()
            if sequence_id is None:
                resolved_sequence_id = self._sequence_allocator.next()
            else:
                self._sequence_allocator.observe(sequence_id)
                resolved_sequence_id = sequence_id
            record = _record(
                sequence_id=resolved_sequence_id,
                payload=payload,
                connection_id=connection_id,
                connection_epoch=connection_epoch,
            )
            if len(self._items) < self._maxsize:
                self._items.append(record)
                self._condition.notify()
                return record
            if self._backpressure_policy == "drop_oldest":
                dropped = self._items.popleft()
                self._dropped.count += 1
                self._record_drop(
                    dropped_count=1,
                    first_sequence_id=dropped["sequence_id"],
                    last_sequence_id=dropped["sequence_id"],
                    connection_id=dropped.get("connection_id"),
                    connection_epoch=dropped.get("connection_epoch"),
                )
                self._items.append(record)
                self._condition.notify()
                return record
            if self._backpressure_policy == "drop_newest":
                self._dropped.count += 1
                self._record_drop(
                    dropped_count=1,
                    first_sequence_id=record["sequence_id"],
                    last_sequence_id=record["sequence_id"],
                    connection_id=record.get("connection_id"),
                    connection_epoch=record.get("connection_epoch"),
                )
                return None
            if self._backpressure_policy == "close_connection":
                self._dropped.count += 1
                self._record_drop(
                    dropped_count=1,
                    first_sequence_id=record["sequence_id"],
                    last_sequence_id=record["sequence_id"],
                    connection_id=record.get("connection_id"),
                    connection_epoch=record.get("connection_epoch"),
                )
                self._closed = True
                self._condition.notify_all()
                raise QueueClosedError("network.queue_closed")
            raise QueueBackpressureError("network.queue_backpressure")

    async def get(self, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        async with self._condition:
            while True:
                self._ensure_cancelled()
                if self._items:
                    return self._items.popleft()
                if self._closed:
                    raise QueueClosedError("network.queue_closed")
                try:
                    if timeout_seconds is None:
                        await self._condition.wait()
                    else:
                        await __import__("asyncio").wait_for(
                            self._condition.wait(),
                            timeout_seconds,
                        )
                except __import__("asyncio").TimeoutError as exc:
                    raise TimeoutError("network.queue_wait_timeout") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._wake_all()

    def reopen(self) -> None:
        """在同一连接句柄重连后恢复队列写入能力并保留既有记录。"""
        if self._cancelled:
            raise QueueCancelledError("network.queue_cancelled")
        self._closed = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._wake_all()

    def _wake_all(self) -> None:
        async def _notify() -> None:
            async with self._condition:
                self._condition.notify_all()

        try:
            __import__("asyncio").get_running_loop()
        except RuntimeError:
            return
        __import__("asyncio").create_task(_notify())

    def _ensure_open(self) -> None:
        self._ensure_cancelled()
        if self._closed:
            raise QueueClosedError("network.queue_closed")

    def _ensure_cancelled(self) -> None:
        if self._cancelled:
            raise QueueCancelledError("network.queue_cancelled")

    def _record_drop(
        self,
        *,
        dropped_count: int,
        first_sequence_id: int,
        last_sequence_id: int,
        connection_id: str | None,
        connection_epoch: int | None,
    ) -> None:
        self._drop_events.append(
            {
                "event_kind": "network.queue_message_dropped",
                "policy": self._backpressure_policy,
                "dropped_count": dropped_count,
                "first_sequence_id": first_sequence_id,
                "last_sequence_id": last_sequence_id,
                "connection_id": connection_id,
                "connection_epoch": connection_epoch,
            }
        )


class ExecutionActivationQueue(BoundedMessageQueue):
    async def activate(
        self,
        payload: Any,
        *,
        connection_id: str | None = None,
        connection_epoch: int | None = None,
        sequence_id: int | None = None,
    ) -> dict[str, Any] | None:
        return await self.put(
            payload,
            connection_id=connection_id,
            connection_epoch=connection_epoch,
            sequence_id=sequence_id,
        )

    async def wait_next(self, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        return await self.get(timeout_seconds=timeout_seconds)


class SessionActivationQueue:
    """在线程之间汇聚同一执行会话的长连接激活事件。

    长连接句柄各自运行在独立的 asyncio loop 中，不能直接共享
    ``asyncio.Condition``。该路由器只负责跨 loop 的有界排队和按连接
    分发，真正的节点执行仍由调用方串行完成。
    """

    def __init__(self, *, maxsize: int = 1024) -> None:
        if not isinstance(maxsize, int) or isinstance(maxsize, bool) or maxsize <= 0:
            raise ValueError("maxsize must be a positive integer")
        self._maxsize = maxsize
        self._items: deque[tuple[str, dict[str, Any]]] = deque()
        self._pending: dict[str, deque[dict[str, Any]]] = {}
        self._condition = Condition(Lock())
        self._closed = False
        self._cancelled = False
        self._dropped_count = 0
        self._drop_events: deque[dict[str, Any]] = deque(maxlen=max(32, min(maxsize * 4, 4096)))

    @property
    def size(self) -> int:
        with self._condition:
            return len(self._items) + sum(len(items) for items in self._pending.values())

    @property
    def dropped_count(self) -> int:
        with self._condition:
            return self._dropped_count

    @property
    def drop_events(self) -> list[dict[str, Any]]:
        with self._condition:
            return [dict(item) for item in self._drop_events]

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def cancelled(self) -> bool:
        with self._condition:
            return self._cancelled

    def publish(
        self,
        connection_key: str,
        activation: dict[str, Any],
        *,
        backpressure_policy: str = "fail_stream",
    ) -> bool:
        if not isinstance(connection_key, str) or not connection_key:
            raise ValueError("connection_key must be a non-empty string")
        if not isinstance(activation, dict):
            raise ValueError("activation must be an object")
        if backpressure_policy not in _VALID_POLICIES:
            raise ValueError("unknown backpressure_policy")
        with self._condition:
            self._ensure_open()
            if self._size_locked() >= self._maxsize:
                if backpressure_policy == "drop_oldest":
                    dropped = self._pop_oldest_locked()
                    self._record_drop_locked(
                        dropped,
                        policy=backpressure_policy,
                    )
                elif backpressure_policy == "drop_newest":
                    self._record_drop_locked(
                        (connection_key, activation),
                        policy=backpressure_policy,
                    )
                    return False
                elif backpressure_policy == "close_connection":
                    self._record_drop_locked(
                        (connection_key, activation),
                        policy=backpressure_policy,
                    )
                    self._closed = True
                    self._condition.notify_all()
                    raise QueueClosedError("network.queue_closed")
                else:
                    raise QueueBackpressureError("network.queue_backpressure")
            self._items.append((connection_key, dict(activation)))
            self._condition.notify_all()
            return True

    def wait(
        self,
        connection_key: str,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(connection_key, str) or not connection_key:
            raise ValueError("connection_key must be a non-empty string")
        deadline = monotonic() + timeout_seconds if timeout_seconds is not None else None
        with self._condition:
            while True:
                self._ensure_not_cancelled()
                pending = self._pending.get(connection_key)
                if pending:
                    activation = pending.popleft()
                    if not pending:
                        self._pending.pop(connection_key, None)
                    return activation
                while self._items:
                    item_key, activation = self._items.popleft()
                    if item_key == connection_key:
                        return activation
                    self._pending.setdefault(item_key, deque()).append(activation)
                if self._closed:
                    raise QueueClosedError("network.queue_closed")
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("network.queue_wait_timeout")
                self._condition.wait(timeout=remaining)

    def discard(self, connection_key: str) -> None:
        """移除已释放连接尚未交付的激活，避免会话历史继续持有句柄事件。"""
        with self._condition:
            if self._items:
                self._items = deque(
                    (key, activation)
                    for key, activation in self._items
                    if key != connection_key
                )
            self._pending.pop(connection_key, None)
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()

    def cancel(self) -> None:
        with self._condition:
            if self._cancelled:
                return
            self._cancelled = True
            self._condition.notify_all()

    def status(self) -> dict[str, Any]:
        with self._condition:
            return {
                "depth": self._size_locked(),
                "dropped_count": self._dropped_count,
                "drop_events": [dict(item) for item in self._drop_events],
                "closed": self._closed,
                "cancelled": self._cancelled,
                "maxsize": self._maxsize,
            }

    def _size_locked(self) -> int:
        return len(self._items) + sum(len(items) for items in self._pending.values())

    def _pop_oldest_locked(self) -> tuple[str, dict[str, Any]]:
        if self._items:
            return self._items.popleft()
        # The pending buckets are populated only when a waiter is filtering a
        # different connection. Preserve the earliest available item by using
        # insertion order of the buckets as a conservative fallback.
        for key, pending in tuple(self._pending.items()):
            if pending:
                activation = pending.popleft()
                if not pending:
                    self._pending.pop(key, None)
                return key, activation
        raise RuntimeError("activation queue accounting is inconsistent")

    def _record_drop_locked(
        self,
        item: tuple[str, dict[str, Any]],
        *,
        policy: str,
    ) -> None:
        connection_key, activation = item
        sequence_id = activation.get("sequence_id")
        self._dropped_count += 1
        self._drop_events.append(
            {
                "event_kind": "network.queue_message_dropped",
                "policy": policy,
                "dropped_count": 1,
                "first_sequence_id": sequence_id,
                "last_sequence_id": sequence_id,
                "connection_id": activation.get("connection_id") or connection_key,
                "connection_epoch": activation.get("connection_epoch"),
            }
        )

    def _ensure_open(self) -> None:
        self._ensure_not_cancelled()
        if self._closed:
            raise QueueClosedError("network.queue_closed")

    def _ensure_not_cancelled(self) -> None:
        if self._cancelled:
            raise QueueCancelledError("network.queue_cancelled")
