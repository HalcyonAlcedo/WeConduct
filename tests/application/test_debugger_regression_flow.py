from __future__ import annotations

from threading import Event, Thread, get_ident
from time import monotonic, sleep

import pytest

from tests.application.test_compilation_workbench_service import (
    _build_custom_node_graph_for_debug_step,
    _build_debug_execution_workspace_graph,
    _build_debug_step_workspace_graph,
    _build_minimal_workspace_graph,
    _build_parallel_custom_node_graph_for_debug_history,
    _build_python_only_workspace_graph,
)
from weconduct.application.compilation_workbench_service import (
    CompilationWorkbenchService,
)
from weconduct.application.workspace_state_store import FileWorkspaceStateStore


class _AliveThread:
    def is_alive(self) -> bool:
        return True


def _wait_for_debug_status(
    service: CompilationWorkbenchService,
    session_id: str,
    expected_status: str,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        session_document = service.get_debug_session(session_id=session_id)
        if session_document["debug_session"]["status"] == expected_status:
            return
        sleep(0.01)
    session_document = service.get_debug_session(session_id=session_id)
    raise AssertionError(
        f"debug session did not reach {expected_status!r}: "
        f"{session_document['debug_session']['status']!r}"
    )


def _build_debug_pause_resume_workspace_graph() -> dict:
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=False)
    graph["nodes"][1]["ports"].append(
        {
            "port_id": "control-out",
            "direction": "output",
            "relation_layer": "control",
            "semantic_slot": "control.next",
        }
    )
    graph["nodes"].append(
        {
            "node_id": "node-finish-variable",
            "lowered_kind": "execution",
            "source_anchor_ref": "n-node-finish-variable",
            "expansion_role": "data.set_variable",
            "display_name": "写入最终变量",
            "node_kind": "data.set_variable",
            "position": {"x": 360, "y": 0},
            "ports": [
                {
                    "port_id": "control-in",
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "control.previous",
                }
            ],
            "node_config": {
                "name": "debug_finish_result",
                "value": "done",
            },
        }
    )
    graph["edges"].append(
        {
            "edge_id": "edge-set-variable-finish-variable",
            "from_node_id": "node-set-variable",
            "from_port_id": "control-out",
            "to_node_id": "node-finish-variable",
            "to_port_id": "control-in",
            "relation_layer": "control",
        }
    )
    return graph


def _build_debug_retry_workspace_graph() -> dict:
    return {
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
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {
                    "initial_variables": {"retry_done": False},
                    "browser_config": {"headless": True},
                    "execution_defaults": {
                        "default_timeout_ms": 30000,
                        "default_retry_count": 0,
                    },
                },
            },
            {
                "node_id": "node-retry",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-retry",
                "expansion_role": "control.retry",
                "display_name": "重试",
                "node_kind": "control.retry",
                "position": {"x": 180, "y": 0},
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "attempt",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.attempt",
                    },
                    {
                        "port_id": "exhausted",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.exhausted",
                    },
                ],
                "node_config": {"max_attempts": 2},
            },
            {
                "node_id": "node-attempt",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-attempt",
                "expansion_role": "data.set_variable",
                "display_name": "重试体",
                "node_kind": "data.set_variable",
                "position": {"x": 360, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    },
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    },
                ],
                "node_config": {
                    "name": "retry_attempted",
                    "value": True,
                    "debugger": {
                        "breakpoint": {"enabled": True, "pause_timing": "before"}
                    },
                },
            },
            {
                "node_id": "node-done",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-done",
                "expansion_role": "data.set_variable",
                "display_name": "重试完成",
                "node_kind": "data.set_variable",
                "position": {"x": 540, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    }
                ],
                "node_config": {"name": "retry_done", "value": True},
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-retry",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-retry",
                "to_port_id": "in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-retry-attempt",
                "from_node_id": "node-retry",
                "from_port_id": "attempt",
                "to_node_id": "node-attempt",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-attempt-retry",
                "from_node_id": "node-attempt",
                "from_port_id": "control-out",
                "to_node_id": "node-retry",
                "to_port_id": "in",
                "relation_layer": "control",
            },
            {
                "edge_id": "edge-retry-done",
                "from_node_id": "node-retry",
                "from_port_id": "exhausted",
                "to_node_id": "node-done",
                "to_port_id": "control-in",
                "relation_layer": "control",
            },
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_debug_regression_variable_apply_is_persisted_into_history(tmp_path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    graph["nodes"][0]["node_config"]["initial_variables"]["retry_count"] = 0
    service.save_graph_document(graph)
    project_path = tmp_path / "debug-variable-history.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["status"] == "paused"

    service.apply_debug_session_variables(
        session_id=session_id,
        updates={"username": "history-user", "retry_count": 2},
        apply_mode="staged",
    )

    history_payload = service.open_debug_history_session(session_id=session_id)
    history_events = history_payload["session"]["events"]

    assert history_events[-1]["event_kind"] == "debug.variables_applied"
    assert history_events[-1]["apply_mode"] == "staged"
    assert history_events[-1]["updates"] == {
        "username": "history-user",
        "retry_count": 2,
    }


def test_debug_regression_step_action_is_persisted_into_history(tmp_path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(workspace_state_path),
    )
    graph = _build_debug_step_workspace_graph()
    graph["nodes"][0]["node_config"]["debugger"] = {
        "breakpoint": {"enabled": True, "pause_timing": "before"}
    }
    service.save_graph_document(graph)
    project_path = tmp_path / "debug-step-history.weconduct.json"
    service.save_project_as(project_path=str(project_path))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    assert start_result["debug_session"]["status"] == "paused"

    step_result = service.step_over_debug_session(session_id=session_id)
    history_payload = service.open_debug_history_session(session_id=session_id)
    history_events = history_payload["session"]["events"]

    step_events = [
        item
        for item in history_events
        if item.get("event_kind") == "debug.step"
    ]

    assert step_result["debug_session"]["status"] == "paused"
    assert step_events
    assert step_events[-1]["step_mode"] == "step_over"
    assert step_events[-1]["node_id"] == "node-start"
    assert history_events[-1]["event_kind"] == "debug.paused"


def test_debug_regression_exception_continue_completes_and_releases_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_python_only_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    assert start_result["debug_session"]["status"] == "paused"
    assert start_result["debug_session"]["paused_reason"] == "exception_raised"

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "completed"
    assert service.list_debug_sessions()["sessions"] == []


def test_debug_regression_runtime_can_start_after_debug_completion() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    _wait_for_debug_status(service, session_id, "paused")
    # Wait deterministically for the worker to settle. _await_debug_execution_settle
    # returns as soon as the session reaches a terminal status, so a generous
    # timeout adds no latency to the normal case but removes flakiness when the
    # worker is starved of CPU under full-suite parallel load.
    continue_result = service.continue_debug_session_async(
        session_id=session_id,
        settle_timeout_ms=5000,
    )

    assert continue_result["debug_session"]["status"] == "completed"
    runtime_result = service.start_runtime_session(graph_document_payload=None)
    assert runtime_result["runtime_session"]["status"] == "running"


def test_debug_regression_completed_session_rejects_stale_pause_request() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    _wait_for_debug_status(service, session_id, "paused")
    # Generous settle window: returns immediately on terminal status, so this
    # only widens tolerance under CPU-starved parallel runs (see companion test).
    continue_result = service.continue_debug_session_async(
        session_id=session_id,
        settle_timeout_ms=5000,
    )

    assert continue_result["debug_session"]["status"] == "completed"
    assert service.list_debug_sessions()["sessions"] == []

    with pytest.raises(ValueError, match="debug pause is not allowed"):
        service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
        )

    assert service.list_debug_sessions()["sessions"] == []
    runtime_result = service.start_runtime_session(graph_document_payload=None)
    assert runtime_result["runtime_session"]["status"] == "running"


def test_debug_regression_prepare_does_not_create_controllable_session() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_execution_workspace_graph())

    prepare_result = service.prepare_debug_session(graph_document_payload=None)
    assert prepare_result["status"] == "ready"
    assert "debug_session" not in prepare_result

    with pytest.raises(ValueError, match="debug session not found"):
        service.request_debug_pause(
            session_id="debug-session-not-created-by-prepare",
            node_id=None,
            reason="manual_pause",
        )

    assert service.list_debug_sessions()["sessions"] == []


def test_debug_regression_parallel_join_state_survives_breakpoint_resume() -> None:
    service = CompilationWorkbenchService()
    component_graph = _build_custom_node_graph_for_debug_step()
    component_graph["nodes"][1]["node_config"].pop("debugger", None)
    service.save_graph_document(component_graph)
    resource_key = service.save_custom_node_graph_resource(
        resource_name="并行恢复组件"
    )["resource"]["resource_key"]

    graph = _build_parallel_custom_node_graph_for_debug_history(resource_key)
    graph["graph_model_id"] = "graph:workspace"
    graph["nodes"][0]["expansion_role"] = "flow.start"
    graph["nodes"][0]["node_kind"] = "flow.start"
    graph["nodes"][0]["node_config"] = {
        "initial_variables": {},
        "browser_config": {"headless": True},
        "execution_defaults": {
            "default_timeout_ms": 30000,
            "default_retry_count": 0,
        },
    }
    graph["nodes"][3]["node_config"]["debugger"] = {
        "breakpoint": {"enabled": True, "pause_timing": "before"}
    }
    graph["nodes"][5]["expansion_role"] = "data.set_variable"
    graph["nodes"][5]["node_kind"] = "data.set_variable"
    graph["nodes"][5]["node_config"] = {
        "name": "parallel_done",
        "value": True,
    }
    service.save_graph_document(graph)

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    assert start_result["debug_session"]["status"] == "paused"
    assert start_result["runtime_preview"]["current_node"]["node_id"] == "parallel-right-call"
    assert start_result["runtime_preview"]["join_buffers"]["parallel-join"][
        "arrived_tokens"
    ] == ["in:left"]

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "completed"
    assert continue_result["variable_snapshot"]["parallel_done"] is True


def test_debug_regression_retry_attempt_survives_breakpoint_resume() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_retry_workspace_graph())

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]

    assert start_result["debug_session"]["status"] == "paused"
    assert start_result["runtime_preview"]["current_node"]["node_id"] == "node-attempt"
    assert start_result["runtime_preview"]["retry_states"]["node-retry"]["attempts"] == 1

    continue_result = service.continue_debug_session(session_id=session_id)

    assert continue_result["debug_session"]["status"] == "completed"
    assert continue_result["variable_snapshot"]["retry_done"] is True


def test_debug_regression_without_breakpoints_matches_runtime_order_and_variables() -> None:
    graph = _build_debug_execution_workspace_graph(start_breakpoint_before=False)

    runtime_service = CompilationWorkbenchService()
    runtime_service.save_graph_document(graph)
    runtime_start = runtime_service.start_runtime_session(graph_document_payload=None)
    runtime_result = runtime_service.run_runtime_session(
        session_id=runtime_start["runtime_session"]["session_id"]
    )

    debug_service = CompilationWorkbenchService()
    debug_service.save_graph_document(graph)
    debug_result = debug_service.start_debug_session(graph_document_payload=None)

    assert runtime_result["runtime_session"]["status"] == "completed"
    assert debug_result["debug_session"]["status"] == "completed"
    assert debug_result["runtime_preview"]["executed_node_ids"] == runtime_result["result"][
        "completed_node_ids"
    ]
    assert debug_result["variable_snapshot"] == runtime_result["result"]["variables"]


def test_debug_regression_events_have_stable_index_and_context(tmp_path) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json")
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "event-schema.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    events = service.list_debug_session_events(session_id=session_id)["events"]

    assert events
    assert [event["event_index"] for event in events] == list(range(len(events)))
    assert len({event["event_id"] for event in events}) == len(events)
    for event in events:
        assert event["session_id"] == session_id
        assert isinstance(event["recorded_at"], str) and event["recorded_at"]
        assert isinstance(event["instance_path"], list)
        assert isinstance(event["iteration_stack"], list)
    keyframe_events = [event for event in events if event.get("keyframe_id")]
    assert keyframe_events
    assert len({event["keyframe_id"] for event in keyframe_events}) == len(keyframe_events)


def test_debug_regression_history_projection_selects_keyframe_by_event_index(tmp_path) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json")
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "event-projection.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.apply_debug_session_variables(
        session_id=session_id,
        updates={"username": "first"},
        apply_mode="immediate",
    )
    first_event = service.list_debug_session_events(session_id=session_id)["events"][-1]
    service.apply_debug_session_variables(
        session_id=session_id,
        updates={"username": "second"},
        apply_mode="immediate",
    )
    second_event = service.list_debug_session_events(session_id=session_id)["events"][-1]

    first_projection = service.get_debug_history_projection(
        session_id=session_id,
        event_index=first_event["event_index"],
    )
    second_projection = service.get_debug_history_projection(
        session_id=session_id,
        event_index=second_event["event_index"],
    )

    assert first_projection["projection"]["history_event_index"] == first_event["event_index"]
    assert second_projection["projection"]["history_event_index"] == second_event["event_index"]
    assert first_projection["variable_snapshot"]["username"] == "first"
    assert second_projection["variable_snapshot"]["username"] == "second"


def test_debug_regression_history_projection_selects_stable_keyframe_id(tmp_path) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json")
    )
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )
    service.save_project_as(project_path=str(tmp_path / "keyframe-projection.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    service.apply_debug_session_variables(
        session_id=session_id,
        updates={"username": "selected-by-keyframe"},
        apply_mode="immediate",
    )
    history_payload = service.open_debug_history_session(session_id=session_id)["session"]
    keyframe = history_payload["keyframes"][-1]

    projection = service.get_debug_history_projection(
        session_id=session_id,
        keyframe_id=keyframe["keyframe_id"],
    )

    assert keyframe["keyframe_id"]
    assert projection["projection"]["history_keyframe_id"] == keyframe["keyframe_id"]
    assert projection["projection"]["history_event_index"] == keyframe["event_index"]
    assert projection["variable_snapshot"]["username"] == "selected-by-keyframe"


def test_debug_regression_history_projection_stops_markers_at_requested_event(tmp_path) -> None:
    service = CompilationWorkbenchService(
        state_store=FileWorkspaceStateStore(tmp_path / "runtime" / "workspace-state.json")
    )
    service.save_graph_document(_build_minimal_workspace_graph())
    service.save_project_as(project_path=str(tmp_path / "event-marker-boundary.weconduct.json"))

    start_result = service.start_debug_session(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    first_event = {
        "event_id": f"{session_id}:event:00000000",
        "event_index": 0,
        "event_kind": "debug.paused",
        "session_id": session_id,
        "node_id": "node-start",
        "instance_path": ["graph:workspace", "node-start"],
        "iteration_stack": [],
    }
    second_event = {
        "event_id": f"{session_id}:event:00000001",
        "event_index": 1,
        "event_kind": "record_frame.hit",
        "session_id": session_id,
        "node_id": "node-later",
        "instance_path": ["graph:workspace", "node-later"],
        "iteration_stack": [],
    }
    service._replace_debug_session_document({  # type: ignore[attr-defined]
        **start_result,
        "debug_session": {**start_result["debug_session"], "status": "paused"},
        "debug_events": [first_event, second_event],
        "debug_keyframes": [
            {
                "keyframe_id": f"{first_event['event_id']}:keyframe",
                "event_id": first_event["event_id"],
                "event_index": 0,
                "event_kind": first_event["event_kind"],
                "node_id": "node-start",
                "runtime_preview": start_result["runtime_preview"],
                "variable_snapshot": start_result["variable_snapshot"],
            }
        ],
    })

    projection = service.get_debug_history_projection(
        session_id=session_id,
        event_index=0,
    )

    assert projection["projection"]["history_event_index"] == 0
    assert projection["projection"]["record_frame_node_ids"] == []


def test_debug_regression_pause_request_waits_for_settle_when_thread_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    captured: dict[str, object] = {}

    def fake_await_debug_execution_settle(
        *,
        session_id: str,
        settle_timeout_ms: int = 75,
        accepted_status: str = "accepted",
        terminal_only: bool = False,
    ) -> dict:
        captured["session_id"] = session_id
        captured["settle_timeout_ms"] = settle_timeout_ms
        captured["accepted_status"] = accepted_status
        captured["terminal_only"] = terminal_only
        return {
            "status": "paused",
            "debug_session": {
                "session_id": session_id,
                "status": "paused",
            },
        }

    monkeypatch.setattr(service, "_await_debug_execution_settle", fake_await_debug_execution_settle)

    result = service.request_debug_pause(
        session_id=session_id,
        node_id=None,
        reason="manual_pause",
        settle_timeout_ms=250,
    )

    assert result["status"] == "paused"
    assert captured == {
        "session_id": session_id,
        "settle_timeout_ms": 250,
        "accepted_status": "accepted",
        "terminal_only": False,
    }


def test_debug_regression_abort_waits_for_settle_when_thread_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(
        _build_debug_execution_workspace_graph(start_breakpoint_before=True)
    )

    start_result = service.start_debug_session_async(graph_document_payload=None)
    session_id = start_result["debug_session"]["session_id"]
    session_document = service.get_debug_session(session_id=session_id)
    session_document["debug_session"] = {
        **session_document["debug_session"],
        "status": "running",
        "paused_reason": None,
    }
    service._replace_debug_session_document(session_document)  # type: ignore[attr-defined]
    service._debug_execution_threads[session_id] = _AliveThread()  # type: ignore[attr-defined]

    captured: dict[str, object] = {}

    def fake_await_debug_execution_settle(
        *,
        session_id: str,
        settle_timeout_ms: int = 75,
        accepted_status: str = "accepted",
        terminal_only: bool = False,
    ) -> dict:
        captured["session_id"] = session_id
        captured["settle_timeout_ms"] = settle_timeout_ms
        captured["accepted_status"] = accepted_status
        captured["terminal_only"] = terminal_only
        return {
            "status": "aborted",
            "debug_session": {
                "session_id": session_id,
                "status": "aborted",
            },
        }

    monkeypatch.setattr(service, "_await_debug_execution_settle", fake_await_debug_execution_settle)

    result = service.abort_debug_session(
        session_id=session_id,
        reason="user_abort",
        settle_timeout_ms=250,
    )

    assert result["status"] == "aborted"
    assert captured == {
        "session_id": session_id,
        "settle_timeout_ms": 250,
        "accepted_status": "accepted",
        "terminal_only": True,
    }


@pytest.mark.parametrize("use_async_continue", [False, True])
def test_debug_regression_manual_pause_resume_continues_to_successor(
    monkeypatch: pytest.MonkeyPatch,
    use_async_continue: bool,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_pause_resume_workspace_graph())

    entered_mid_node = Event()
    release_mid_node = Event()
    execution_thread_ids: list[int] = []
    original_execute = service._execute_runtime_plan_node

    def fake_execute_runtime_plan_node(*, executable_node, runtime_context, executor_registry):
        execution_thread_ids.append(get_ident())
        if executable_node.get("node_id") == "node-set-variable":
            entered_mid_node.set()
            assert release_mid_node.wait(timeout=1.5), "mid node release wait timed out"
        return original_execute(
            executable_node=executable_node,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
        )

    monkeypatch.setattr(service, "_execute_runtime_plan_node", fake_execute_runtime_plan_node)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=10,
    )
    session_id = start_result["debug_session"]["session_id"]
    execution_thread = service._debug_execution_threads[session_id]  # type: ignore[attr-defined]

    assert entered_mid_node.wait(timeout=1.5), "mid node was never entered"
    pause_result_holder: dict[str, dict] = {}

    def run_pause_request() -> None:
        pause_result_holder["value"] = service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
            settle_timeout_ms=500,
        )

    pause_thread = Thread(target=run_pause_request, daemon=True)
    pause_thread.start()
    release_mid_node.set()
    pause_thread.join(timeout=1.5)
    assert "value" in pause_result_holder, "pause request did not settle in time"
    pause_result = pause_result_holder["value"]

    assert pause_result["debug_session"]["status"] == "paused"
    assert pause_result["debug_session"]["paused_reason"] == "manual_pause"
    assert pause_result["debug_snapshots"][-1]["event_kind"] == "debug.paused"
    assert pause_result["debug_snapshots"][-1]["reason"] == "manual_pause"
    assert pause_result["debug_snapshots"][-1]["snapshot_id"]
    assert execution_thread.is_alive()

    continue_result = (
        service.continue_debug_session_async(
            session_id=session_id,
            settle_timeout_ms=500,
        )
        if use_async_continue
        else service.continue_debug_session(session_id=session_id)
    )

    assert continue_result["debug_session"]["status"] == "completed"
    assert continue_result["runtime_preview"]["executed_node_ids"] == [
        "node-start",
        "node-set-variable",
        "node-finish-variable",
    ]
    assert continue_result["variable_snapshot"]["debug_result"] == "done"
    assert continue_result["variable_snapshot"]["debug_finish_result"] == "done"
    assert len(set(execution_thread_ids)) == 1


def test_debug_regression_manual_pause_resume_preserves_repeat_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    graph = _build_debug_retry_workspace_graph()
    graph["nodes"][2]["node_config"].pop("debugger", None)
    graph["edges"] = [
        graph["edges"][0],
        graph["edges"][1],
        {
            "edge_id": "edge-attempt-done",
            "from_node_id": "node-attempt",
            "from_port_id": "control-out",
            "to_node_id": "node-done",
            "to_port_id": "control-in",
            "relation_layer": "control",
        },
    ]
    service.save_graph_document(graph)

    entered_attempt = Event()
    release_attempt = Event()
    original_execute = service._execute_runtime_plan_node

    def fake_execute_runtime_plan_node(*, executable_node, runtime_context, executor_registry):
        if executable_node.get("node_id") == "node-attempt" and not entered_attempt.is_set():
            entered_attempt.set()
            assert release_attempt.wait(timeout=1.5), "retry attempt release wait timed out"
        return original_execute(
            executable_node=executable_node,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
        )

    monkeypatch.setattr(service, "_execute_runtime_plan_node", fake_execute_runtime_plan_node)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=10,
    )
    session_id = start_result["debug_session"]["session_id"]
    assert entered_attempt.wait(timeout=1.5), "retry attempt was never entered"

    pause_result_holder: dict[str, dict] = {}

    def run_pause_request() -> None:
        pause_result_holder["value"] = service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
            settle_timeout_ms=500,
        )

    pause_thread = Thread(target=run_pause_request, daemon=True)
    pause_thread.start()
    pause_deadline = monotonic() + 1.0
    while not service._debug_control_flags.get(session_id, {}).get("pause_requested"):  # type: ignore[attr-defined]
        assert monotonic() < pause_deadline, "pause request flag was not set in time"
        sleep(0.005)
    release_attempt.set()
    pause_thread.join(timeout=1.5)
    assert "value" in pause_result_holder, "pause request did not settle in time"
    pause_result = pause_result_holder["value"]

    assert pause_result["debug_session"]["status"] == "paused"
    assert pause_result["debug_session"]["resume_from_pending_queue"] is True
    assert pause_result["runtime_preview"]["current_node"]["node_id"] == "node-attempt"
    assert pause_result["runtime_preview"]["current_node"]["repeat_mode"] is True
    assert pause_result["runtime_preview"]["token_queue"] == []

    continue_result = service.continue_debug_session_async(
        session_id=session_id,
        settle_timeout_ms=500,
    )

    assert continue_result["debug_session"]["status"] == "completed"
    assert continue_result["variable_snapshot"]["retry_done"] is True


def test_debug_regression_abort_paused_session_closes_runtime_on_owner_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_pause_resume_workspace_graph())

    entered_mid_node = Event()
    release_mid_node = Event()
    owner_thread_id: int | None = None
    close_thread_ids: list[int] = []
    original_execute = service._execute_runtime_plan_node

    class ThreadBoundBrowser:
        def close(self) -> None:
            close_thread_ids.append(get_ident())
            assert get_ident() == owner_thread_id

    def fake_execute_runtime_plan_node(*, executable_node, runtime_context, executor_registry):
        nonlocal owner_thread_id
        if owner_thread_id is None:
            owner_thread_id = get_ident()
            runtime_context.browser_runtime["browser"] = ThreadBoundBrowser()
        if executable_node.get("node_id") == "node-set-variable":
            entered_mid_node.set()
            assert release_mid_node.wait(timeout=1.5), "mid node release wait timed out"
        return original_execute(
            executable_node=executable_node,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
        )

    monkeypatch.setattr(service, "_execute_runtime_plan_node", fake_execute_runtime_plan_node)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=10,
    )
    session_id = start_result["debug_session"]["session_id"]
    assert entered_mid_node.wait(timeout=1.5), "mid node was never entered"

    pause_result_holder: dict[str, dict] = {}

    def run_pause_request() -> None:
        pause_result_holder["value"] = service.request_debug_pause(
            session_id=session_id,
            node_id=None,
            reason="manual_pause",
            settle_timeout_ms=500,
        )

    pause_thread = Thread(target=run_pause_request, daemon=True)
    pause_thread.start()
    release_mid_node.set()
    pause_thread.join(timeout=1.5)
    assert pause_result_holder["value"]["debug_session"]["status"] == "paused"
    assert service._debug_execution_threads[session_id].is_alive()  # type: ignore[attr-defined]
    runtime_context = service._debug_runtime_contexts[session_id]  # type: ignore[attr-defined]
    assert runtime_context.browser_runtime["browser"].__class__ is ThreadBoundBrowser

    abort_result = service.abort_debug_session(
        session_id=session_id,
        reason="user_abort",
        settle_timeout_ms=500,
    )

    assert abort_result["debug_session"]["status"] == "aborted"
    assert close_thread_ids == [owner_thread_id]
    assert session_id not in service._debug_runtime_contexts  # type: ignore[attr-defined]


def test_debug_regression_start_worker_failure_marks_session_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_pause_resume_workspace_graph())
    monkeypatch.setattr(service, "_launch_debug_execution_thread", lambda **_: False)

    result = service.start_debug_session_async(graph_document_payload=None)

    assert result["status"] == "failed"
    assert result["debug_session"]["status"] == "failed"
    assert result["debug_session"]["paused_reason"] == "debug_worker_start_failed"
    assert service.list_debug_sessions()["sessions"] == []


def test_debug_regression_running_session_persists_live_preview_during_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_pause_resume_workspace_graph())

    entered_mid_node = Event()
    release_mid_node = Event()
    original_execute = service._execute_runtime_plan_node

    def fake_execute_runtime_plan_node(*, executable_node, runtime_context, executor_registry):
        if executable_node.get("node_id") == "node-set-variable":
            entered_mid_node.set()
            assert release_mid_node.wait(timeout=1.5), "mid node release wait timed out"
        return original_execute(
            executable_node=executable_node,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
        )

    monkeypatch.setattr(service, "_execute_runtime_plan_node", fake_execute_runtime_plan_node)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=10,
    )
    session_id = start_result["debug_session"]["session_id"]

    assert entered_mid_node.wait(timeout=1.5), "mid node was never entered"
    session_document = service.get_debug_session(session_id=session_id)
    release_mid_node.set()

    assert session_document["debug_session"]["status"] == "running"
    assert session_document["runtime_preview"]["current_node"]["node_id"] == "node-set-variable"


def test_debug_regression_abort_releases_runtime_context_during_active_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_build_debug_pause_resume_workspace_graph())

    entered_mid_node = Event()
    release_mid_node = Event()
    original_execute = service._execute_runtime_plan_node

    def fake_execute_runtime_plan_node(*, executable_node, runtime_context, executor_registry):
        if executable_node.get("node_id") == "node-set-variable":
            entered_mid_node.set()
            assert release_mid_node.wait(timeout=1.5), "mid node release wait timed out"
        return original_execute(
            executable_node=executable_node,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
        )

    monkeypatch.setattr(service, "_execute_runtime_plan_node", fake_execute_runtime_plan_node)

    start_result = service.start_debug_session_async(
        graph_document_payload=None,
        settle_timeout_ms=10,
    )
    session_id = start_result["debug_session"]["session_id"]

    assert entered_mid_node.wait(timeout=1.5), "mid node was never entered"
    abort_result_holder: dict[str, dict] = {}

    def run_abort_request() -> None:
        abort_result_holder["value"] = service.abort_debug_session(
            session_id=session_id,
            reason="user_abort",
            settle_timeout_ms=500,
        )

    abort_thread = Thread(target=run_abort_request, daemon=True)
    abort_thread.start()
    release_mid_node.set()
    abort_thread.join(timeout=1.5)

    assert "value" in abort_result_holder, "abort request did not settle in time"
    abort_result = abort_result_holder["value"]
    assert abort_result["debug_session"]["status"] == "aborted"
    assert session_id not in service._debug_runtime_contexts  # type: ignore[attr-defined]
