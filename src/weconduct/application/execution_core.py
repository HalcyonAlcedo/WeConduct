from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from weconduct.runtime.execution_context import ExecutionTokenContext


@dataclass(frozen=True)
class ExecutionCursor:
    program_counter: int
    repeat_mode: bool
    iteration_stack: list[str]
    token_context: ExecutionTokenContext = ExecutionTokenContext()


@dataclass(frozen=True)
class RestoredSchedulerState:
    pending_node_entries: list[dict[str, object]]
    queued_node_ids: set[str]
    join_state_by_node_id: dict[str, dict[str, object]]
    retry_state_by_node_id: dict[str, dict[str, object]]


class ExecutionCore:
    @staticmethod
    def dispatch_next_token(
        *,
        pending_node_entries: list[dict[str, object]],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> ExecutionCursor:
        next_entry = pending_node_entries.pop(0) if pending_node_entries else None
        if not isinstance(next_entry, dict):
            return ExecutionCursor(program_counter=-1, repeat_mode=False, iteration_stack=[])
        node_index = next_entry.get("node_index")
        if not isinstance(node_index, int) or not (0 <= node_index < len(executable_nodes)):
            return ExecutionCursor(program_counter=-1, repeat_mode=False, iteration_stack=[])
        repeat_mode = bool(next_entry.get("repeat_mode"))
        iteration_stack = (
            list(next_entry.get("iteration_stack"))
            if isinstance(next_entry.get("iteration_stack"), list)
            else []
        )
        token_context = ExecutionTokenContext.from_snapshot(next_entry.get("token_context"))
        if event_log is not None and isinstance(session_id, str):
            node = executable_nodes[node_index]
            recorded_at = datetime.now(timezone.utc).isoformat()
            event_log.extend(
                [
                    {
                        "event_kind": "token.dispatched",
                        "recorded_at": recorded_at,
                        "session_id": session_id,
                        "node_id": node.get("node_id"),
                        "node_kind": node.get("node_kind"),
                        "repeat_mode": repeat_mode,
                        "network_context_id": token_context.network_context_id,
                    },
                    {
                        "event_kind": "node.ready",
                        "recorded_at": recorded_at,
                        "session_id": session_id,
                        "node_id": node.get("node_id"),
                        "node_kind": node.get("node_kind"),
                    },
                ]
            )
        return ExecutionCursor(
            program_counter=node_index,
            repeat_mode=repeat_mode,
            iteration_stack=iteration_stack,
            token_context=token_context,
        )

    @staticmethod
    def queue_control_edges(
        *,
        control_edges_by_source: dict[str, list[dict]],
        source_node_id: str,
        source_port_id: str | None,
        repeat_mode: bool,
        enqueue: Callable[[dict, bool], None],
    ) -> None:
        for edge in control_edges_by_source.get(source_node_id, []):
            if source_port_id is not None and edge.get("from_port_id") not in {
                None,
                source_port_id,
            }:
                continue
            enqueue(edge, repeat_mode)

    @staticmethod
    def execute_node(
        *,
        owner: object,
        executable_node: dict,
        runtime_context: object,
        data_edges_by_target: dict[str, list[dict]],
        executor_registry: object,
    ) -> dict:
        flow_runtime = getattr(runtime_context, "flow_runtime", None)
        previous_active_node = None
        if isinstance(flow_runtime, dict):
            previous_active_node = flow_runtime.get("active_runtime_node")
            flow_runtime["active_runtime_node"] = {
                "node_id": executable_node.get("node_id"),
                "node_kind": executable_node.get("node_kind"),
            }
        try:
            try:
                cancelled_result = _build_cancelled_result(
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                )
                if cancelled_result is not None:
                    return cancelled_result
                owner._inject_runtime_data_edge_inputs(  # type: ignore[attr-defined]
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                    data_edges_by_target=data_edges_by_target,
                )
                cancelled_result = _build_cancelled_result(
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                )
                if cancelled_result is not None:
                    return cancelled_result
                return owner._execute_runtime_plan_node(  # type: ignore[attr-defined]
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                    executor_registry=executor_registry,
                )
            except Exception as exc:
                if _is_cancellation_exception(exc):
                    return _build_cancellation_exception_result(
                        executable_node=executable_node,
                        exc=exc,
                    )
                return owner._build_runtime_executor_exception_output(  # type: ignore[attr-defined]
                    executable_node=executable_node,
                    exc=exc,
                )
        finally:
            if isinstance(flow_runtime, dict):
                if previous_active_node is None:
                    flow_runtime.pop("active_runtime_node", None)
                else:
                    flow_runtime["active_runtime_node"] = previous_active_node

    @staticmethod
    def build_scheduler_snapshot(
        *,
        scheduler_mode: str | None,
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids_in_order: list[str],
        join_state_by_node_id: dict[str, dict[str, object]],
        retry_state_by_node_id: dict[str, dict[str, object]],
        executable_nodes: list[dict],
        current_program_counter: int | None,
        current_repeat_mode: bool,
        current_iteration_stack: list[str] | None = None,
        current_token_context: ExecutionTokenContext | None = None,
    ) -> dict:
        token_queue: list[dict[str, object]] = []
        for entry in pending_node_entries:
            if not isinstance(entry, dict):
                continue
            node_index = entry.get("node_index")
            if not isinstance(node_index, int) or not (0 <= node_index < len(executable_nodes)):
                continue
            node = executable_nodes[node_index]
            token_queue.append(
                {
                    "node_id": node.get("node_id"),
                    "node_kind": node.get("node_kind"),
                    "repeat_mode": bool(entry.get("repeat_mode")),
                    "iteration_stack": (
                        list(entry.get("iteration_stack"))
                        if isinstance(entry.get("iteration_stack"), list)
                        else []
                    ),
                    "token_context": ExecutionTokenContext.from_snapshot(
                        entry.get("token_context")
                    ).to_snapshot(),
                }
            )
        join_buffers: dict[str, dict[str, object]] = {}
        for node_id, join_state in join_state_by_node_id.items():
            if not isinstance(node_id, str) or not isinstance(join_state, dict):
                continue
            arrived_tokens = join_state.get("arrived_tokens")
            if not isinstance(arrived_tokens, set):
                arrived_tokens = join_state.get("arrived_input_ports")
            join_buffers[node_id] = {
                "arrived_tokens": sorted(arrived_tokens) if isinstance(arrived_tokens, set) else [],
                "join_mode": join_state.get("join_mode"),
            }
        retry_states = {
            node_id: {
                "attempts": int(retry_state.get("attempts", 0))
                if isinstance(retry_state.get("attempts"), int)
                else 0
            }
            for node_id, retry_state in retry_state_by_node_id.items()
            if isinstance(node_id, str) and isinstance(retry_state, dict)
        }
        current_node = None
        if (
            isinstance(current_program_counter, int)
            and 0 <= current_program_counter < len(executable_nodes)
        ):
            node = executable_nodes[current_program_counter]
            current_node = {
                "node_id": node.get("node_id"),
                "node_kind": node.get("node_kind"),
                "repeat_mode": current_repeat_mode,
                "iteration_stack": (
                    list(current_iteration_stack)
                    if isinstance(current_iteration_stack, list)
                    else []
                ),
                "token_context": (current_token_context or ExecutionTokenContext()).to_snapshot(),
            }
        return {
            "scheduler_mode": scheduler_mode,
            "token_queue": token_queue,
            "queued_node_ids": sorted(item for item in queued_node_ids if isinstance(item, str)),
            "executed_node_ids": [
                item for item in executed_node_ids_in_order if isinstance(item, str)
            ],
            "join_buffers": join_buffers,
            "retry_states": retry_states,
            "current_node": current_node,
        }

    @staticmethod
    def restore_scheduler_snapshot(
        *,
        snapshot: dict,
        executable_nodes: list[dict],
    ) -> RestoredSchedulerState:
        node_index_by_id = {
            item.get("node_id"): index
            for index, item in enumerate(executable_nodes)
            if isinstance(item, dict) and isinstance(item.get("node_id"), str)
        }
        pending_node_entries: list[dict[str, object]] = []
        queued_node_ids: set[str] = set()
        token_queue = snapshot.get("token_queue")
        if isinstance(token_queue, list):
            for token in token_queue:
                if not isinstance(token, dict):
                    continue
                node_id = token.get("node_id")
                node_index = node_index_by_id.get(node_id)
                if not isinstance(node_id, str) or not isinstance(node_index, int):
                    continue
                pending_node_entries.append(
                    {
                        "node_index": node_index,
                        "repeat_mode": bool(token.get("repeat_mode")),
                        "iteration_stack": (
                            list(token.get("iteration_stack"))
                            if isinstance(token.get("iteration_stack"), list)
                            else []
                        ),
                        "token_context": ExecutionTokenContext.from_snapshot(
                            token.get("token_context")
                        ).to_snapshot(),
                    }
                )
                queued_node_ids.add(node_id)
        join_state_by_node_id: dict[str, dict[str, object]] = {}
        join_buffers = snapshot.get("join_buffers")
        if isinstance(join_buffers, dict):
            for node_id, buffer in join_buffers.items():
                if not isinstance(node_id, str) or not isinstance(buffer, dict):
                    continue
                arrived_tokens = buffer.get("arrived_tokens")
                if not isinstance(arrived_tokens, list):
                    arrived_tokens = buffer.get("arrived_input_ports")
                join_state_by_node_id[node_id] = {
                    "arrived_tokens": {
                        token for token in arrived_tokens if isinstance(token, str)
                    }
                    if isinstance(arrived_tokens, list)
                    else set(),
                    "join_mode": buffer.get("join_mode"),
                }
        retry_state_by_node_id: dict[str, dict[str, object]] = {}
        retry_states = snapshot.get("retry_states")
        if isinstance(retry_states, dict):
            for node_id, retry_state in retry_states.items():
                if not isinstance(node_id, str) or not isinstance(retry_state, dict):
                    continue
                attempts = retry_state.get("attempts")
                retry_state_by_node_id[node_id] = {
                    "attempts": attempts if isinstance(attempts, int) and attempts >= 0 else 0
                }
        return RestoredSchedulerState(
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            join_state_by_node_id=join_state_by_node_id,
            retry_state_by_node_id=retry_state_by_node_id,
        )


def _runtime_cancellation_context(runtime_context: object) -> object | None:
    return getattr(runtime_context, "cancellation_context", None)


def _build_cancelled_result(*, executable_node: dict, runtime_context: object) -> dict | None:
    cancellation_context = _runtime_cancellation_context(runtime_context)
    if cancellation_context is None or not getattr(cancellation_context, "is_cancelled", False):
        return None
    reason = getattr(cancellation_context, "reason", None)
    return {
        "status": "cancelled",
        "node_id": executable_node.get("node_id"),
        "node_kind": executable_node.get("node_kind"),
        "message": reason or "execution cancelled",
        "reason": reason,
    }


def _is_cancellation_exception(exc: Exception) -> bool:
    return bool(getattr(exc, "weconduct_cancelled", False))


def _build_cancellation_exception_result(*, executable_node: dict, exc: Exception) -> dict:
    reason = getattr(exc, "reason", None) or str(exc) or "execution cancelled"
    return {
        "status": "cancelled",
        "node_id": executable_node.get("node_id"),
        "node_kind": executable_node.get("node_kind"),
        "message": reason,
        "reason": reason,
    }
