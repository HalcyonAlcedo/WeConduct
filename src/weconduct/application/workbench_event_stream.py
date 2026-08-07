from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Lock
from typing import Any, Callable, Iterator
import uuid

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload


HEARTBEAT_EVENT_NAME = "__heartbeat__"
_STOP_EVENT = object()


@dataclass
class WorkbenchEventSubscriber:
    subscriber_id: str
    queue: Queue = field(default_factory=Queue)


class WorkbenchEventStreamBroker:
    """进程内工作台事件总线；事件只用于 UI 收敛，不写入项目或运行历史。"""

    def __init__(self, *, history_limit: int = 256) -> None:
        if not isinstance(history_limit, int) or isinstance(history_limit, bool) or history_limit <= 0:
            raise ValueError("history_limit must be a positive integer")
        self._lock = Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self._next_event_id = 0
        self._subscribers: dict[str, WorkbenchEventSubscriber] = {}

    def publish(self, event_name: str, payload: dict[str, Any]) -> int:
        if not isinstance(event_name, str) or not event_name.strip():
            raise ValueError("event_name must be a non-empty string")
        redacted_payload = redact_sensitive_payload(payload)
        if not isinstance(redacted_payload, dict):
            raise TypeError("workbench event payload must be a mapping")
        with self._lock:
            self._next_event_id += 1
            event = {
                "event_id": self._next_event_id,
                "event_name": event_name,
                "payload": dict(redacted_payload),
            }
            self._history.append(event)
            for subscriber in list(self._subscribers.values()):
                subscriber.queue.put(dict(event))
            return self._next_event_id

    def get_event_bounds(self) -> dict[str, int | None]:
        with self._lock:
            if not self._history:
                return {"oldest_event_id": None, "latest_event_id": None}
            return {
                "oldest_event_id": int(self._history[0]["event_id"]),
                "latest_event_id": int(self._history[-1]["event_id"]),
            }

    def subscribe(
        self,
        *,
        after_event_id: int | None = None,
        snapshot: dict[str, Any] | None = None,
        snapshot_factory: Callable[[], dict[str, Any]] | None = None,
    ) -> tuple[str, Queue]:
        self._validate_cursor(after_event_id)
        if snapshot is not None and snapshot_factory is not None:
            raise ValueError("workbench.snapshot_source_conflict")
        subscriber = WorkbenchEventSubscriber(subscriber_id=uuid.uuid4().hex)

        # 读取工作台快照可能触及状态存储。先在锁内捕获事件边界，再释放
        # Broker 锁执行回调，避免“状态存储锁 -> Broker 锁”和
        # “Broker 锁 -> 状态存储锁”形成反向等待。
        initial_history: list[dict[str, Any]] | None = None
        snapshot_base_event_id: int | None = None
        redacted_snapshot: dict[str, Any] | None = None
        snapshot_requested = after_event_id is None and (
            snapshot is not None or snapshot_factory is not None
        )
        if snapshot_factory is not None and after_event_id is None:
            with self._lock:
                self._assert_cursor_available_locked(after_event_id)
                snapshot_base_event_id = self._next_event_id
                initial_history = [dict(event) for event in self._history]
            raw_snapshot = snapshot_factory()
            redacted_snapshot = redact_sensitive_payload(raw_snapshot)
            if not isinstance(redacted_snapshot, dict):
                raise TypeError("workbench snapshot must be a mapping")
        elif snapshot_requested:
            redacted_snapshot = redact_sensitive_payload(snapshot)
            if not isinstance(redacted_snapshot, dict):
                raise TypeError("workbench snapshot must be a mapping")

        with self._lock:
            self._assert_cursor_available_locked(after_event_id)
            if after_event_id is None:
                # A first-time UI subscriber may connect after an external
                # operation has already reached a terminal state.  Replay the
                # current process history before the snapshot so the UI can
                # discover that operation instead of only seeing its final
                # workspace state.
                if initial_history is None:
                    initial_history = [dict(event) for event in self._history]
                    snapshot_base_event_id = self._next_event_id
                for event in initial_history:
                    subscriber.queue.put(dict(event))

            if snapshot_requested:
                snapshot_event_id = (
                    snapshot_base_event_id
                    if snapshot_factory is not None
                    else self._next_event_id
                )
                subscriber.queue.put(
                    {
                        "event_id": snapshot_event_id,
                        "event_name": "workbench.snapshot",
                        "payload": dict(redacted_snapshot),
                    }
                )
                if snapshot_factory is not None:
                    for event in self._history:
                        if int(event["event_id"]) > int(snapshot_base_event_id):
                            subscriber.queue.put(dict(event))
            elif after_event_id is not None:
                for event in self._history:
                    if int(event["event_id"]) > after_event_id:
                        subscriber.queue.put(dict(event))
            self._subscribers[subscriber.subscriber_id] = subscriber
        return subscriber.subscriber_id, subscriber.queue

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            subscriber = self._subscribers.pop(subscriber_id, None)
            if subscriber is not None:
                subscriber.queue.put(_STOP_EVENT)

    def close(self) -> None:
        with self._lock:
            subscribers = list(self._subscribers.values())
            self._subscribers.clear()
            for subscriber in subscribers:
                subscriber.queue.put(_STOP_EVENT)

    def iter_events(
        self,
        queue: Queue,
        *,
        heartbeat_seconds: float | None = None,
    ) -> Iterator[dict[str, Any]]:
        if heartbeat_seconds is not None and heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        while True:
            try:
                item = queue.get(timeout=heartbeat_seconds or 0.5)
            except Empty:
                if heartbeat_seconds is not None:
                    yield {
                        "event_id": None,
                        "event_name": HEARTBEAT_EVENT_NAME,
                        "payload": {},
                    }
                continue
            if item is _STOP_EVENT:
                return
            if isinstance(item, dict):
                yield item

    def _validate_cursor(self, after_event_id: int | None) -> None:
        if after_event_id is not None and (
            not isinstance(after_event_id, int)
            or isinstance(after_event_id, bool)
            or after_event_id < 0
        ):
            raise ValueError("workbench.event_cursor_invalid")

    def _assert_cursor_available_locked(self, after_event_id: int | None) -> None:
        if after_event_id is None or not self._history:
            return
        oldest_event_id = int(self._history[0]["event_id"])
        if after_event_id < oldest_event_id - 1:
            raise ValueError("workbench.event_cursor_expired")
