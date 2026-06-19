from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Lock
from typing import Any, Iterator
import uuid


_STOP_EVENT = object()


@dataclass
class RuntimeSessionStreamSubscriber:
    subscriber_id: str
    queue: Queue = field(default_factory=Queue)


class RuntimeSessionStreamBroker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscribers_by_session_id: dict[str, dict[str, RuntimeSessionStreamSubscriber]] = defaultdict(dict)
        self._latest_snapshot_by_session_id: dict[str, dict[str, Any]] = {}

    def publish_snapshot(self, session_id: str, snapshot: dict[str, Any]) -> None:
        self._latest_snapshot_by_session_id[session_id] = dict(snapshot)
        self._publish(session_id, "runtime.snapshot", dict(snapshot))

    def publish_event(self, session_id: str, event_name: str, payload: dict[str, Any]) -> None:
        self._publish(session_id, event_name, dict(payload))

    def get_latest_snapshot(self, session_id: str) -> dict[str, Any] | None:
        snapshot = self._latest_snapshot_by_session_id.get(session_id)
        return dict(snapshot) if isinstance(snapshot, dict) else None

    def subscribe(self, session_id: str) -> tuple[str, Queue]:
        subscriber_id = uuid.uuid4().hex
        subscriber = RuntimeSessionStreamSubscriber(subscriber_id=subscriber_id)
        with self._lock:
            self._subscribers_by_session_id[session_id][subscriber_id] = subscriber
        snapshot = self.get_latest_snapshot(session_id)
        if snapshot is not None:
            subscriber.queue.put(("runtime.snapshot", snapshot))
        return subscriber_id, subscriber.queue

    def unsubscribe(self, session_id: str, subscriber_id: str) -> None:
        with self._lock:
            subscribers = self._subscribers_by_session_id.get(session_id)
            if not subscribers:
                return
            subscriber = subscribers.pop(subscriber_id, None)
            if subscriber is not None:
                subscriber.queue.put(_STOP_EVENT)
            if not subscribers:
                self._subscribers_by_session_id.pop(session_id, None)

    def close_session(self, session_id: str) -> None:
        with self._lock:
            subscribers = self._subscribers_by_session_id.pop(session_id, {})
            for subscriber in subscribers.values():
                subscriber.queue.put(_STOP_EVENT)

    def _publish(self, session_id: str, event_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers_by_session_id.get(session_id, {}).values())
        for subscriber in subscribers:
            subscriber.queue.put((event_name, payload))

    def iter_events(self, queue: Queue) -> Iterator[tuple[str, dict[str, Any]]]:
        while True:
            try:
                item = queue.get(timeout=0.5)
            except Empty:
                continue
            if item is _STOP_EVENT:
                return
            event_name, payload = item
            yield event_name, payload
