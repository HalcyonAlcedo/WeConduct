from __future__ import annotations

import pytest

from weconduct.contracts.debugger import DEBUG_SESSION_ACTION_ALLOWED_STATUSES
from weconduct.contracts.debugger import DEBUG_SESSION_ACTIVE_STATUSES
from weconduct.contracts.debugger import DEBUG_SESSION_STATUSES
from weconduct.contracts.debugger import DEBUG_SESSION_TERMINAL_STATUSES
from weconduct.contracts.debugger import DebugSnapshotRecord
from weconduct.contracts.debugger import is_debug_action_allowed
from weconduct.contracts.debugger import is_debug_session_status_active
from weconduct.contracts.debugger import is_debug_session_status_terminal


def test_debug_session_status_sets_match_formal_contract() -> None:
    assert DEBUG_SESSION_STATUSES == (
        "preparing",
        "running",
        "paused",
        "stepping",
        "completed",
        "failed",
        "cancelled",
        "aborted",
        "incomplete",
    )
    assert DEBUG_SESSION_ACTIVE_STATUSES == frozenset(
        {"preparing", "running", "paused", "stepping"}
    )
    assert DEBUG_SESSION_TERMINAL_STATUSES == frozenset(
        {"completed", "failed", "cancelled", "aborted", "incomplete"}
    )


@pytest.mark.parametrize(
    ("status", "expected_active", "expected_terminal"),
    [
        ("preparing", True, False),
        ("running", True, False),
        ("paused", True, False),
        ("stepping", True, False),
        ("completed", False, True),
        ("failed", False, True),
        ("cancelled", False, True),
        ("aborted", False, True),
        ("incomplete", False, True),
    ],
)
def test_debug_session_status_helpers_cover_all_formal_statuses(
    status: str,
    expected_active: bool,
    expected_terminal: bool,
) -> None:
    assert is_debug_session_status_active(status) is expected_active
    assert is_debug_session_status_terminal(status) is expected_terminal


def test_debug_session_control_action_matrix_matches_contract() -> None:
    assert DEBUG_SESSION_ACTION_ALLOWED_STATUSES == {
        "pause": frozenset({"running", "stepping"}),
        "continue": frozenset({"paused"}),
        "step_over": frozenset({"paused"}),
        "step_into": frozenset({"paused"}),
        "step_out": frozenset({"paused"}),
        "variables_apply": frozenset({"paused"}),
        "record_frame": frozenset({"paused"}),
        "abort": frozenset({"preparing", "running", "paused", "stepping"}),
    }


@pytest.mark.parametrize(
    ("action", "allowed_statuses"),
    [
        ("pause", {"running", "stepping"}),
        ("continue", {"paused"}),
        ("step_over", {"paused"}),
        ("step_into", {"paused"}),
        ("step_out", {"paused"}),
        ("variables_apply", {"paused"}),
        ("record_frame", {"paused"}),
        ("abort", {"preparing", "running", "paused", "stepping"}),
    ],
)
def test_debug_action_allowed_respects_formal_matrix(
    action: str,
    allowed_statuses: set[str],
) -> None:
    for status in DEBUG_SESSION_STATUSES:
        assert is_debug_action_allowed(status, action) is (status in allowed_statuses)


@pytest.mark.parametrize(
    "terminal_status",
    ["completed", "failed", "cancelled", "aborted", "incomplete"],
)
def test_terminal_statuses_reject_all_control_actions(terminal_status: str) -> None:
    for action in DEBUG_SESSION_ACTION_ALLOWED_STATUSES:
        assert is_debug_action_allowed(terminal_status, action) is False


def test_debug_snapshot_contract_accepts_manual_pause_snapshot() -> None:
    snapshot = DebugSnapshotRecord.model_validate(
        {
            "snapshot_id": "snapshot-1",
            "session_id": "debug-session-1",
            "event_id": "event-1",
            "event_index": 1,
            "keyframe_id": "keyframe-1",
            "frame_identity": "frame-1",
            "event_kind": "debug.paused",
            "reason": "manual_pause",
            "recorded_at": "2026-07-12T00:00:00+00:00",
            "graph_model_id": "graph:workspace",
            "compilation_id": "compilation-1",
            "node_id": "node-1",
            "output_state": "unavailable",
        }
    )

    assert snapshot.event_kind == "debug.paused"
    assert snapshot.reason == "manual_pause"
