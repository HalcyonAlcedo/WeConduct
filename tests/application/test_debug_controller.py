import pytest

from weconduct.application.debug_controller import DebugController


def _build_session_snapshot(
    *,
    status: str = "paused",
    paused_reason: str | None = None,
    step_sequence: int | None = None,
    breakpoint_encounter_counts: dict | None = None,
    breakpoint_once_consumed: dict | None = None,
    debug_events: list[dict] | None = None,
    current_node_id: str | None = None,
) -> dict:
    debug_session = {
        "status": status,
        "paused_reason": paused_reason,
    }
    if step_sequence is not None:
        debug_session["step_sequence"] = step_sequence
    if breakpoint_encounter_counts is not None:
        debug_session["breakpoint_encounter_counts"] = breakpoint_encounter_counts
    if breakpoint_once_consumed is not None:
        debug_session["breakpoint_once_consumed"] = breakpoint_once_consumed
    snapshot = {
        "debug_session": debug_session,
        "debug_events": list(debug_events or []),
    }
    if current_node_id is not None:
        snapshot["runtime_preview"] = {"current_node": {"node_id": current_node_id}}
    return snapshot


def test_debug_controller_assigns_distinct_identity_for_same_loop_node_hits() -> None:
    controller = DebugController()
    hit_1 = controller.build_breakpoint_hit_event(
        node_id="node-loop-body",
        instance_path=["graph:workspace", "node-loop-body"],
        pause_timing="before",
        iteration_stack=["while:node-while#1"],
    )
    hit_2 = controller.build_breakpoint_hit_event(
        node_id="node-loop-body",
        instance_path=["graph:workspace", "node-loop-body"],
        pause_timing="before",
        iteration_stack=["while:node-while#2"],
    )

    assert hit_1["frame_identity"] != hit_2["frame_identity"]
    assert hit_1["breakpoint_hit_ordinal_in_session"] == 1
    assert hit_2["breakpoint_hit_ordinal_in_session"] == 2


def test_debug_controller_builds_record_frame_event_without_pause() -> None:
    controller = DebugController()
    event = controller.build_record_frame_event(
        node_id="node-1",
        instance_path=["graph:workspace", "node-1"],
        iteration_stack=[],
    )
    assert event["event_kind"] == "record_frame.hit"
    assert event["pause_requested"] is False


def test_debug_controller_request_action_continue_from_paused_builds_resume_fields() -> None:
    controller = DebugController()
    session = _build_session_snapshot(
        status="paused",
        debug_events=[
            {
                "event_kind": "breakpoint.hit",
                "node_id": "node-1",
                "pause_timing": "before",
                "iteration_stack": ["while:1"],
            },
            {"event_kind": "debug.paused", "node_id": "node-1"},
        ],
    )

    decision = controller.request_action(session, "continue")

    assert decision["next_status"] == "running"
    assert decision["session_patch"]["status"] == "running"
    assert decision["session_patch"]["paused_reason"] is None
    assert decision["session_patch"]["last_control_action"] == "continue"
    assert decision["session_patch"]["step_mode"] is None
    assert decision["session_patch"]["resume_skip_breakpoint_once"] == {
        "node_id": "node-1",
        "pause_timing": "before",
        "iteration_stack": ["while:1"],
    }


def test_debug_controller_rejects_step_out_without_component_pause() -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="paused")

    with pytest.raises(ValueError, match="step_out is only available inside a component"):
        controller.request_action(session, "step_out")


def test_debug_controller_request_action_step_over_increments_sequence() -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="paused", step_sequence=2)

    decision = controller.request_action(session, "step_over")

    assert decision["next_status"] == "stepping"
    assert decision["session_patch"] == {
        "status": "stepping",
        "step_mode": "step_over",
        "paused_reason": "step_requested",
        "last_control_action": "step_over",
        "step_sequence": 3,
    }


@pytest.mark.parametrize(
    ("status", "action"),
    [
        ("running", "continue"),
        ("paused", "pause"),
        ("completed", "abort"),
        ("stepping", "variables_apply"),
    ],
)
def test_debug_controller_request_action_rejects_disallowed_status(
    status: str,
    action: str,
) -> None:
    controller = DebugController()
    session = _build_session_snapshot(status=status)

    with pytest.raises(ValueError, match=f"debug {action} is not allowed"):
        controller.request_action(session, action)


def test_debug_controller_restores_breakpoint_ordinals_from_session_snapshot() -> None:
    controller = DebugController(
        session_snapshot=_build_session_snapshot(
            debug_events=[
                {"event_kind": "breakpoint.hit"},
                {"event_kind": "breakpoint.hit"},
                {"event_kind": "record_frame.hit"},
            ]
        )
    )

    hit_event = controller.build_breakpoint_hit_event(
        node_id="node-2",
        instance_path=["graph:workspace", "node-2"],
        pause_timing="after",
        iteration_stack=[],
    )
    record_event = controller.build_record_frame_event(
        node_id="node-2",
        instance_path=["graph:workspace", "node-2"],
        iteration_stack=[],
    )

    assert hit_event["breakpoint_hit_ordinal_in_session"] == 3
    assert record_event["record_frame_ordinal_in_session"] == 2


def test_debug_controller_evaluate_breakpoint_gate_restores_hit_count_and_once_state() -> None:
    instance_path = ["graph:workspace", "node-1"]
    controller_key = DebugController.build_breakpoint_state_key(
        instance_path=instance_path,
        pause_timing="before",
    )
    controller = DebugController(
        session_snapshot=_build_session_snapshot(
            breakpoint_encounter_counts={controller_key: 2},
            breakpoint_once_consumed={controller_key: True},
        )
    )

    gate = controller.evaluate_breakpoint_gate(
        session=_build_session_snapshot(status="running"),
        breakpoint_config={"enabled": True, "once": True, "hit_count": 2},
        runtime_variables={"loop_counter": 3},
        node_id="node-1",
        node_kind="builtin:test",
        session_id="dbg-001",
        instance_path=instance_path,
        pause_timing="before",
    )

    assert gate["should_pause"] is False
    assert gate["emit_breakpoint_hit"] is False
    assert gate["session_patch"]["breakpoint_encounter_counts"][controller_key] == 3
    assert gate["session_patch"]["breakpoint_once_consumed"][controller_key] is True


def test_debug_controller_evaluate_breakpoint_gate_honors_hit_count_and_expression() -> None:
    controller = DebugController()
    instance_path = ["graph:workspace", "node-1"]

    skipped = controller.evaluate_breakpoint_gate(
        session=_build_session_snapshot(status="running"),
        breakpoint_config={"enabled": True, "hit_count": 2, "expression": "${loop_counter > 2}"},
        runtime_variables={"loop_counter": 1},
        node_id="node-1",
        node_kind="builtin:test",
        session_id="dbg-001",
        instance_path=instance_path,
        pause_timing="before",
    )
    paused = controller.evaluate_breakpoint_gate(
        session=_build_session_snapshot(
            status="running",
            breakpoint_encounter_counts=skipped["session_patch"]["breakpoint_encounter_counts"],
            breakpoint_once_consumed=skipped["session_patch"]["breakpoint_once_consumed"],
        ),
        breakpoint_config={"enabled": True, "hit_count": 2, "expression": "${loop_counter > 2}"},
        runtime_variables={"loop_counter": 3},
        node_id="node-1",
        node_kind="builtin:test",
        session_id="dbg-001",
        instance_path=instance_path,
        pause_timing="before",
    )

    assert skipped["should_pause"] is False
    assert paused["should_pause"] is True
    assert paused["reason"] == "breakpoint_hit"


@pytest.mark.parametrize(
    ("event", "expected_patch"),
    [
        (
            {"event_kind": "breakpoint.hit", "frame_identity": "bp-1"},
            {
                "paused_reason": "breakpoint_hit",
                "last_control_action": "breakpoint_hit",
                "last_breakpoint_frame_identity": "bp-1",
            },
        ),
        (
            {"event_kind": "record_frame.hit", "frame_identity": "rf-1"},
            {
                "last_control_action": "record_frame",
                "last_record_frame_identity": "rf-1",
            },
        ),
        (
            {"event_kind": "debug.paused", "reason": "manual_pause"},
            {
                "status": "paused",
                "paused_reason": "manual_pause",
                "last_control_action": "pause",
            },
        ),
    ],
)
def test_debug_controller_applies_event_state_patch(event: dict, expected_patch: dict) -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="running")
    session["debug_session"]["last_control_action"] = "pause"

    patch = controller.apply_event(session=session, event=event)

    assert patch == expected_patch


def test_debug_controller_builds_variable_update_decision() -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="paused")
    session["variable_snapshot"] = {"username": "original", "retry_count": 1}

    decision = controller.apply_variable_updates(
        session=session,
        updates={"username": "updated", "retry_count": 2},
        apply_mode="immediate",
    )

    assert decision["variable_snapshot"] == {"username": "updated", "retry_count": 2}
    assert decision["session_patch"] == {
        "variable_apply_mode": "immediate",
        "pending_variable_overrides": {},
    }
    assert decision["variable_changes"]["username"]["pending"] is False
    assert decision["variable_changes"]["username"]["original_value"] == "original"


def test_debug_controller_stages_variable_without_mutating_snapshot() -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="paused")
    session["variable_snapshot"] = {"username": "original"}

    decision = controller.apply_variable_updates(
        session=session,
        updates={"username": "pending"},
        apply_mode="staged",
    )

    assert decision["variable_snapshot"] == {"username": "original"}
    assert decision["session_patch"]["pending_variable_overrides"] == {
        "username": "pending"
    }
    assert decision["variable_changes"]["username"]["pending"] is True


def test_debug_controller_rejects_unknown_or_mismatched_variable() -> None:
    controller = DebugController()
    session = _build_session_snapshot(status="paused")
    session["variable_snapshot"] = {"retry_count": 1}

    with pytest.raises(ValueError, match="debug variable does not exist: missing"):
        controller.apply_variable_updates(
            session=session,
            updates={"missing": 1},
            apply_mode="staged",
        )
    with pytest.raises(ValueError, match="expected integer"):
        controller.apply_variable_updates(
            session=session,
            updates={"retry_count": "1"},
            apply_mode="staged",
        )
