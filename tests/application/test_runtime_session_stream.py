from __future__ import annotations

from queue import Queue
from threading import Event, Thread

from weconduct.application.runtime_session_stream import (
    RuntimeSessionStreamBroker,
    _STOP_EVENT,
)
from weconduct.application.sensitive_values.service import SensitiveValueService


class _BlockingTerminalQueue(Queue):
    def __init__(self) -> None:
        super().__init__()
        self.terminal_put_started = Event()
        self.release_terminal_put = Event()

    def put(self, item, *args, **kwargs) -> None:
        if isinstance(item, tuple) and item[0] == "runtime.completed":
            self.terminal_put_started.set()
            self.release_terminal_put.wait(timeout=2.0)
        super().put(item, *args, **kwargs)


class _BlockingSnapshotQueue(Queue):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_put_started = Event()
        self.release_snapshot_put = Event()

    def put(self, item, *args, **kwargs) -> None:
        if isinstance(item, tuple) and item[0] == "runtime.snapshot":
            self.snapshot_put_started.set()
            self.release_snapshot_put.wait(timeout=2.0)
        super().put(item, *args, **kwargs)


def test_close_session_cannot_overtake_terminal_event_delivery() -> None:
    broker = RuntimeSessionStreamBroker()
    subscriber_id, _ = broker.subscribe("runtime-session-race")
    probe_queue = _BlockingTerminalQueue()
    broker._subscribers_by_session_id["runtime-session-race"][subscriber_id].queue = probe_queue

    publisher = Thread(
        target=broker.publish_event,
        args=("runtime-session-race", "runtime.completed", {"status": "completed"}),
    )
    closer = Thread(target=broker.close_session, args=("runtime-session-race",))

    publisher.start()
    assert probe_queue.terminal_put_started.wait(timeout=1.0)
    closer.start()
    probe_queue.release_terminal_put.set()
    publisher.join(timeout=1.0)
    closer.join(timeout=1.0)

    assert not publisher.is_alive()
    assert not closer.is_alive()
    assert probe_queue.get_nowait()[0] == "runtime.completed"
    assert probe_queue.get_nowait() is _STOP_EVENT


def test_close_session_stops_subscribers_and_clears_only_closed_session_snapshot() -> None:
    broker = RuntimeSessionStreamBroker()
    broker.publish_snapshot("session-to-close", {"status": "running"})
    broker.publish_snapshot("session-to-keep", {"status": "idle"})

    _, closed_queue = broker.subscribe("session-to-close")
    _, kept_queue = broker.subscribe("session-to-keep")

    assert closed_queue.get_nowait() == ("runtime.snapshot", {"status": "running"})
    assert kept_queue.get_nowait() == ("runtime.snapshot", {"status": "idle"})

    broker.close_session("session-to-close")

    assert closed_queue.get_nowait() is _STOP_EVENT
    assert broker.get_latest_snapshot("session-to-close") is None
    assert broker.get_latest_snapshot("session-to-keep") == {"status": "idle"}

    broker.publish_event("session-to-keep", "runtime.progress", {"step": 2})

    assert kept_queue.get_nowait() == ("runtime.progress", {"step": 2})


def test_close_session_waits_for_in_flight_snapshot_before_clearing_it() -> None:
    broker = RuntimeSessionStreamBroker()
    subscriber_id, _ = broker.subscribe("session-to-close")
    blocking_queue = _BlockingSnapshotQueue()
    broker._subscribers_by_session_id["session-to-close"][subscriber_id].queue = blocking_queue

    publisher = Thread(
        target=broker.publish_snapshot,
        args=("session-to-close", {"status": "completed"}),
    )
    closer = Thread(target=broker.close_session, args=("session-to-close",))

    publisher.start()
    assert blocking_queue.snapshot_put_started.wait(timeout=1.0)
    closer.start()

    assert closer.is_alive()
    blocking_queue.release_snapshot_put.set()
    publisher.join(timeout=1.0)
    closer.join(timeout=1.0)

    assert not publisher.is_alive()
    assert not closer.is_alive()
    assert blocking_queue.get_nowait() == (
        "runtime.snapshot",
        {"status": "completed"},
    )
    assert blocking_queue.get_nowait() is _STOP_EVENT
    assert broker.get_latest_snapshot("session-to-close") is None


def test_runtime_stream_redacts_sensitive_refs_at_event_boundary() -> None:
    broker = RuntimeSessionStreamBroker()
    _, queue = broker.subscribe("session-sensitive")
    ref = SensitiveValueService().create(
        "test-secret",
        scope_id="session-sensitive",
        source="runtime_input",
    )

    broker.publish_event("session-sensitive", "runtime.node", {"credential": ref})

    assert queue.get_nowait() == (
        "runtime.node",
        {"credential": "<sensitive-ref>"},
    )
