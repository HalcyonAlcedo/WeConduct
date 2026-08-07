from __future__ import annotations

from collections import defaultdict
from collections import deque
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Lock
from typing import Any, Iterator
import uuid

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload


_STOP_EVENT = object()
HEARTBEAT_EVENT_NAME = "__heartbeat__"


@dataclass
class RuntimeSessionStreamSubscriber:
    subscriber_id: str
    queue: Queue = field(default_factory=Queue)


class RuntimeSessionStreamBroker:
    def __init__(
        self,
        *,
        history_limit: int = 256,
        closed_session_history_limit: int = 64,
    ) -> None:
        if not isinstance(history_limit, int) or isinstance(history_limit, bool) or history_limit <= 0:
            raise ValueError("history_limit must be a positive integer")
        if (
            not isinstance(closed_session_history_limit, int)
            or isinstance(closed_session_history_limit, bool)
            or closed_session_history_limit <= 0
        ):
            raise ValueError("closed_session_history_limit must be a positive integer")
        self._lock = Lock()
        self._history_limit = history_limit
        self._closed_session_history_limit = closed_session_history_limit
        self._subscribers_by_session_id: dict[str, dict[str, RuntimeSessionStreamSubscriber]] = defaultdict(dict)
        self._latest_snapshot_by_session_id: dict[str, dict[str, Any]] = {}
        self._event_history_by_session_id: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._next_event_id_by_session_id: dict[str, int] = defaultdict(int)
        self._closed_session_ids: deque[str] = deque()
        self._closed_session_id_set: set[str] = set()

    def publish_snapshot(self, session_id: str, snapshot: dict[str, Any]) -> None:
        snapshot_payload = redact_sensitive_payload(snapshot)
        if not isinstance(snapshot_payload, dict):
            raise TypeError("runtime snapshot must be a mapping")
        with self._lock:
            if session_id in self._closed_session_id_set:
                return
            self._latest_snapshot_by_session_id[session_id] = snapshot_payload
            self._record_event_locked(session_id, "runtime.snapshot", snapshot_payload)
            subscribers = list(self._subscribers_by_session_id.get(session_id, {}).values())
            for subscriber in subscribers:
                subscriber.queue.put(("runtime.snapshot", dict(snapshot_payload)))

    def publish_event(self, session_id: str, event_name: str, payload: dict[str, Any]) -> None:
        event_payload = redact_sensitive_payload(payload)
        if not isinstance(event_payload, dict):
            raise TypeError("runtime event payload must be a mapping")
        self._publish(session_id, event_name, event_payload)

    def get_latest_snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._latest_snapshot_by_session_id.get(session_id)
        return dict(snapshot) if isinstance(snapshot, dict) else None

    def subscribe(self, session_id: str) -> tuple[str, Queue]:
        subscriber_id = uuid.uuid4().hex
        subscriber = RuntimeSessionStreamSubscriber(subscriber_id=subscriber_id)
        with self._lock:
            snapshot = self._latest_snapshot_by_session_id.get(session_id)
            if isinstance(snapshot, dict):
                subscriber.queue.put(("runtime.snapshot", dict(snapshot)))
            if session_id in self._closed_session_id_set:
                subscriber.queue.put(_STOP_EVENT)
            else:
                self._subscribers_by_session_id[session_id][subscriber_id] = subscriber
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
            self._remember_closed_session_locked(session_id)

    def get_events_since(
        self,
        session_id: str,
        *,
        after_event_id: int | None = None,
    ) -> dict[str, Any]:
        if after_event_id is not None and (
            not isinstance(after_event_id, int)
            or isinstance(after_event_id, bool)
            or after_event_id < 0
        ):
            raise ValueError("execution.event_cursor_invalid")
        with self._lock:
            history = list(self._event_history_by_session_id.get(session_id, ()))
        if not history:
            return {
                "oldest_event_id": None,
                "latest_event_id": None,
                "events": [],
            }
        oldest_event_id = int(history[0]["event_id"])
        latest_event_id = int(history[-1]["event_id"])
        cursor = after_event_id if after_event_id is not None else 0
        if cursor < oldest_event_id - 1:
            raise ValueError("execution.event_cursor_expired")
        return {
            "oldest_event_id": oldest_event_id,
            "latest_event_id": latest_event_id,
            "events": [
                {
                    "event_id": int(event["event_id"]),
                    "event_name": event["event_name"],
                    "payload": dict(event["payload"]),
                }
                for event in history
                if int(event["event_id"]) > cursor
            ],
        }

    def get_event_bounds(self, session_id: str) -> dict[str, int | None]:
        with self._lock:
            history = list(self._event_history_by_session_id.get(session_id, ()))
        if not history:
            return {"oldest_event_id": None, "latest_event_id": None}
        return {
            "oldest_event_id": int(history[0]["event_id"]),
            "latest_event_id": int(history[-1]["event_id"]),
        }

    def _publish(self, session_id: str, event_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            if session_id in self._closed_session_id_set:
                return
            self._record_event_locked(session_id, event_name, payload)
            subscribers = list(self._subscribers_by_session_id.get(session_id, {}).values())
            for subscriber in subscribers:
                subscriber.queue.put((event_name, payload))

    def _record_event_locked(self, session_id: str, event_name: str, payload: dict[str, Any]) -> None:
        next_event_id = self._next_event_id_by_session_id[session_id] + 1
        self._next_event_id_by_session_id[session_id] = next_event_id
        self._event_history_by_session_id[session_id].append(
            {
                "event_id": next_event_id,
                "event_name": event_name,
                "payload": dict(payload),
            }
        )

    def _remember_closed_session_locked(self, session_id: str) -> None:
        if session_id in self._closed_session_id_set:
            return
        self._closed_session_ids.append(session_id)
        self._closed_session_id_set.add(session_id)
        while len(self._closed_session_ids) > self._closed_session_history_limit:
            expired_session_id = self._closed_session_ids.popleft()
            self._closed_session_id_set.discard(expired_session_id)
            self._latest_snapshot_by_session_id.pop(expired_session_id, None)
            self._event_history_by_session_id.pop(expired_session_id, None)
            self._next_event_id_by_session_id.pop(expired_session_id, None)

    def iter_events(
        self,
        queue: Queue,
        *,
        heartbeat_seconds: float | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        if heartbeat_seconds is not None and heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        while True:
            try:
                item = queue.get(timeout=heartbeat_seconds or 0.5)
            except Empty:
                if heartbeat_seconds is not None:
                    yield HEARTBEAT_EVENT_NAME, {}
                continue
            if item is _STOP_EVENT:
                return
            event_name, payload = item
            yield event_name, payload
