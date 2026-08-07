from __future__ import annotations

import pytest
from threading import Event, Lock, Thread

from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.application.workbench_event_stream import (
    HEARTBEAT_EVENT_NAME,
    WorkbenchEventStreamBroker,
)


def test_workbench_event_broker_replays_events_and_keeps_global_cursor() -> None:
    broker = WorkbenchEventStreamBroker(history_limit=2)

    broker.publish("workspace.graph_changed", {"revision": 1})
    broker.publish("runtime.session_changed", {"session_id": "runtime-1", "status": "running"})

    subscriber_id, queue = broker.subscribe(after_event_id=1)
    event = queue.get(timeout=0.2)
    assert event["event_id"] == 2
    assert event["event_name"] == "runtime.session_changed"
    assert event["payload"]["session_id"] == "runtime-1"
    broker.unsubscribe(subscriber_id)

    broker.publish("workspace.graph_changed", {"revision": 3})
    bounds = broker.get_event_bounds()
    assert bounds == {"oldest_event_id": 2, "latest_event_id": 3}


def test_workbench_event_broker_replays_history_before_initial_snapshot() -> None:
    """首次建流也必须能发现 UI 建流前已经发生的外部操作。"""
    broker = WorkbenchEventStreamBroker()
    broker.publish("runtime.session_changed", {"session_id": "runtime-1", "status": "completed"})

    subscriber_id, queue = broker.subscribe(snapshot={"runtime_sessions": ["runtime-1"]})
    history_event = queue.get(timeout=0.2)
    snapshot_event = queue.get(timeout=0.2)

    assert history_event["event_id"] == 1
    assert history_event["event_name"] == "runtime.session_changed"
    assert snapshot_event["event_name"] == "workbench.snapshot"
    assert snapshot_event["event_id"] == 1
    broker.unsubscribe(subscriber_id)


def test_workbench_event_broker_rejects_expired_cursor() -> None:
    broker = WorkbenchEventStreamBroker(history_limit=1)
    broker.publish("workspace.graph_changed", {"revision": 1})
    broker.publish("workspace.graph_changed", {"revision": 2})

    with pytest.raises(ValueError, match="workbench.event_cursor_expired"):
        broker.subscribe(after_event_id=0)


def test_workbench_event_broker_iterates_heartbeat_without_recording_it() -> None:
    broker = WorkbenchEventStreamBroker()
    subscriber_id, queue = broker.subscribe()

    event = next(broker.iter_events(queue, heartbeat_seconds=0.01))
    assert event["event_name"] == HEARTBEAT_EVENT_NAME
    assert event["payload"] == {}
    assert broker.get_event_bounds() == {"oldest_event_id": None, "latest_event_id": None}

    broker.unsubscribe(subscriber_id)


def test_workbench_event_broker_keeps_snapshot_and_concurrent_event_ordered() -> None:
    broker = WorkbenchEventStreamBroker()
    snapshot_started = Event()
    release_snapshot = Event()
    state = {"revision": 0}

    def snapshot_factory() -> dict[str, int]:
        snapshot_started.set()
        assert release_snapshot.wait(timeout=1.0)
        return dict(state)

    subscription_result: dict[str, object] = {}

    def subscribe() -> None:
        subscription_result["value"] = broker.subscribe(snapshot_factory=snapshot_factory)

    subscription_thread = Thread(target=subscribe, daemon=True)
    subscription_thread.start()
    assert snapshot_started.wait(timeout=1.0)

    state["revision"] = 1
    publish_thread = Thread(
        target=broker.publish,
        kwargs={"event_name": "workspace.graph_changed", "payload": {"revision": 1}},
    )
    publish_thread.start()
    release_snapshot.set()

    subscription_thread.join(timeout=1.0)
    publish_thread.join(timeout=1.0)
    assert not subscription_thread.is_alive()
    assert not publish_thread.is_alive()

    subscriber_id, queue = subscription_result["value"]
    snapshot_event = queue.get(timeout=0.2)
    change_event = queue.get(timeout=0.2)
    assert snapshot_event["event_name"] == "workbench.snapshot"
    assert snapshot_event["payload"]["revision"] == 1
    assert change_event["event_name"] == "workspace.graph_changed"
    assert change_event["event_id"] == snapshot_event["event_id"] + 1
    broker.unsubscribe(subscriber_id)


def test_workbench_snapshot_factory_does_not_hold_broker_lock_while_reading_state() -> None:
    """快照读取等待外部状态锁时，发布线程不能反向等待 Broker 锁。"""
    broker = WorkbenchEventStreamBroker()
    state_lock = Lock()
    snapshot_started = Event()
    publisher_has_state = Event()

    def snapshot_factory() -> dict[str, int]:
        snapshot_started.set()
        assert publisher_has_state.wait(timeout=1.0)
        with state_lock:
            return {"revision": 1}

    subscription_result: dict[str, object] = {}

    def subscribe() -> None:
        subscription_result["value"] = broker.subscribe(snapshot_factory=snapshot_factory)

    def publish_while_holding_state() -> None:
        with state_lock:
            publisher_has_state.set()
            broker.publish(
                "workspace.graph_changed",
                {"revision": 1},
            )

    subscription_thread = Thread(target=subscribe, daemon=True)
    subscription_thread.start()
    assert snapshot_started.wait(timeout=1.0)

    publisher_thread = Thread(target=publish_while_holding_state, daemon=True)
    publisher_thread.start()
    subscription_thread.join(timeout=1.0)
    publisher_thread.join(timeout=1.0)

    assert not subscription_thread.is_alive()
    assert not publisher_thread.is_alive()
    subscriber_id, queue = subscription_result["value"]
    snapshot_event = queue.get(timeout=0.2)
    change_event = queue.get(timeout=0.2)
    assert snapshot_event["event_name"] == "workbench.snapshot"
    assert change_event["event_name"] == "workspace.graph_changed"
    broker.unsubscribe(subscriber_id)


def test_service_publishes_runtime_session_change_for_external_discovery() -> None:
    broker = WorkbenchEventStreamBroker()
    service = CompilationWorkbenchService(workbench_event_broker=broker)
    _, queue = broker.subscribe(snapshot=service.get_workbench_snapshot())

    result = service.start_runtime_session(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-start",
                    "lowered_kind": "control",
                    "source_anchor_ref": "n-node-start",
                    "expansion_role": "flow.start",
                    "display_name": "流程入口",
                    "node_kind": "flow.start",
                    "position": {"x": 0, "y": 0},
                    "ports": [
                        {
                            "port_id": "out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "out.control",
                        }
                    ],
                    "node_config": {"initial_variables": {}},
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    session_id = result["runtime_session"]["session_id"]

    event = queue.get(timeout=0.2)
    assert event["event_name"] == "workbench.snapshot"
    event = queue.get(timeout=0.2)
    assert event["event_name"] == "runtime.session_changed"
    assert event["payload"] == {
        "session_id": session_id,
        "status": "running",
        "reason": "started",
    }


def test_service_publishes_workbench_change_after_external_graph_compile() -> None:
    broker = WorkbenchEventStreamBroker()
    service = CompilationWorkbenchService(workbench_event_broker=broker)
    subscriber_id, queue = broker.subscribe(snapshot=service.get_workbench_snapshot())

    service.compile_graph_document(None)

    queue.get(timeout=0.2)  # initial workbench.snapshot
    event = queue.get(timeout=0.2)
    assert event["event_name"] == "workspace.project_changed"
    assert event["payload"]["reason"] == "compiled"
    broker.unsubscribe(subscriber_id)


def test_service_publishes_runtime_session_change_after_abort_without_worker() -> None:
    broker = WorkbenchEventStreamBroker()
    service = CompilationWorkbenchService(workbench_event_broker=broker)
    subscriber_id, queue = broker.subscribe(snapshot=service.get_workbench_snapshot())
    started = service.start_runtime_session(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-start",
                    "lowered_kind": "control",
                    "source_anchor_ref": "n-node-start",
                    "expansion_role": "flow.start",
                    "display_name": "流程入口",
                    "node_kind": "flow.start",
                    "position": {"x": 0, "y": 0},
                    "ports": [
                        {
                            "port_id": "out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "out.control",
                        }
                    ],
                    "node_config": {"initial_variables": {}},
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )
    session_id = started["runtime_session"]["session_id"]
    queue.get(timeout=0.2)  # initial workbench.snapshot
    queue.get(timeout=0.2)  # runtime.session_changed: started

    service.abort_runtime_session(session_id=session_id, reason="user_abort")

    event = queue.get(timeout=0.2)
    assert event["event_name"] == "runtime.session_changed"
    assert event["payload"] == {
        "session_id": session_id,
        "status": "aborted",
        "reason": "execution_aborted",
    }
    broker.unsubscribe(subscriber_id)
