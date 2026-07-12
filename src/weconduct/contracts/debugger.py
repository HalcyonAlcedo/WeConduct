from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DEBUG_SESSION_STATUSES = (
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

DEBUG_SESSION_ACTIVE_STATUSES = frozenset(
    {
        "preparing",
        "running",
        "paused",
        "stepping",
    }
)

DEBUG_SESSION_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        "aborted",
        "incomplete",
    }
)

DEBUG_SESSION_ACTION_ALLOWED_STATUSES = {
    "pause": frozenset({"running", "stepping"}),
    "continue": frozenset({"paused"}),
    "step_over": frozenset({"paused"}),
    "step_into": frozenset({"paused"}),
    "step_out": frozenset({"paused"}),
    "variables_apply": frozenset({"paused"}),
    "record_frame": frozenset({"paused"}),
    "abort": DEBUG_SESSION_ACTIVE_STATUSES,
}

DebugPauseTiming = Literal["before", "after", "both"]
DebugSessionStatus = Literal[
    "preparing",
    "running",
    "paused",
    "stepping",
    "completed",
    "failed",
    "cancelled",
    "aborted",
    "incomplete",
]
DebugControlAction = Literal[
    "pause",
    "continue",
    "step_over",
    "step_into",
    "step_out",
    "variables_apply",
    "record_frame",
    "abort",
]
DebugVariableValueType = Literal["null", "boolean", "integer", "number", "string", "array", "object"]
DebugVariableScope = Literal["global", "graph", "subgraph", "node", "component_input", "component_output", "dynamic"]


class VariableDescriptor(BaseModel):
    name: str
    value_type: DebugVariableValueType
    scope: DebugVariableScope = "global"
    editable: bool = True
    origin: str
    nullable: bool = False


class VariableChangeRecord(BaseModel):
    original_value: Any = None
    current_value: Any = None
    apply_mode: Literal["immediate", "staged"]
    changed_at: str
    event_id: str
    pending: bool = False


class DebugSnapshotRecord(BaseModel):
    snapshot_id: str
    session_id: str
    event_id: str
    event_index: int
    keyframe_id: str
    frame_identity: str
    event_kind: Literal["breakpoint.hit", "record_frame.hit", "debug.paused"]
    reason: str | None = None
    recorded_at: str
    graph_model_id: str
    graph_revision: int | None = None
    compilation_id: str
    node_id: str
    node_kind: str | None = None
    pause_timing: str | None = None
    breakpoint_ordinal: int | None = None
    record_frame_ordinal: int | None = None
    instance_path: list[str] = Field(default_factory=list)
    iteration_stack: list[str] = Field(default_factory=list)
    variable_snapshot: dict[str, Any] = Field(default_factory=dict)
    variable_descriptors: dict[str, VariableDescriptor] = Field(default_factory=dict)
    node_input_snapshot: Any = None
    node_output_snapshot: Any = None
    output_state: Literal["not_executed", "captured", "unavailable"]
    runtime_preview: dict[str, Any] = Field(default_factory=dict)
    runtime_preview_summary: dict[str, Any] = Field(default_factory=dict)


def is_debug_session_status_active(status: str) -> bool:
    return status in DEBUG_SESSION_ACTIVE_STATUSES


def is_debug_session_status_terminal(status: str) -> bool:
    return status in DEBUG_SESSION_TERMINAL_STATUSES


def is_debug_action_allowed(status: str, action: str) -> bool:
    allowed_statuses = DEBUG_SESSION_ACTION_ALLOWED_STATUSES.get(action)
    if allowed_statuses is None:
        return False
    return status in allowed_statuses


class DebugIterationIdentity(BaseModel):
    loop_node_id: str | None = None
    loop_kind: str | None = None
    iteration_index: int | None = None
    iteration_stack: list[str] = Field(default_factory=list)


class DebugSessionSummaryIndex(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None = None
    status: DebugSessionStatus
    history_file: str
    graph_model_id: str
    breakpoint_hit_count: int = 0
    diagnostic_count: int = 0
    paused_count: int = 0
    last_pause_node_id: str | None = None
    session_label: str | None = None
