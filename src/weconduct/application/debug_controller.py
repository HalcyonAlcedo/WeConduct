from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from datetime import timezone

from weconduct.contracts.debugger import is_debug_action_allowed
from weconduct.runtime.engine import _safe_eval_expression


class DebugVariableValidationError(ValueError):
    def __init__(self, message: str, *, variable_name: str, expected_type: str, actual_type: str) -> None:
        super().__init__(message)
        self.details = {
            "field": variable_name,
            "expected_type": expected_type,
            "actual_type": actual_type,
            "error_code": "debug.variable_type_mismatch",
        }


class DebugController:
    def __init__(self, *, session_snapshot: dict | None = None) -> None:
        self._session_snapshot = deepcopy(session_snapshot) if isinstance(session_snapshot, dict) else {}
        debug_events = self._extract_debug_events(self._session_snapshot)
        self._hit_ordinal = sum(
            1
            for item in debug_events
            if isinstance(item, dict) and item.get("event_kind") == "breakpoint.hit"
        )
        self._record_frame_ordinal = sum(
            1
            for item in debug_events
            if isinstance(item, dict) and item.get("event_kind") == "record_frame.hit"
        )

    def build_breakpoint_hit_event(
        self,
        *,
        node_id: str,
        instance_path: list[str],
        pause_timing: str,
        iteration_stack: list[str],
    ) -> dict:
        self._hit_ordinal += 1
        identity_source = "|".join(
            [node_id, *instance_path, pause_timing, *iteration_stack, str(self._hit_ordinal)]
        )
        frame_identity = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:16]
        return {
            "event_kind": "breakpoint.hit",
            "node_id": node_id,
            "instance_path": list(instance_path),
            "pause_timing": pause_timing,
            "iteration_stack": list(iteration_stack),
            "breakpoint_hit_ordinal_in_session": self._hit_ordinal,
            "frame_identity": frame_identity,
        }

    def build_record_frame_event(
        self,
        *,
        node_id: str,
        instance_path: list[str],
        iteration_stack: list[str],
    ) -> dict:
        self._record_frame_ordinal += 1
        identity_source = "|".join(
            [node_id, *instance_path, *iteration_stack, str(self._record_frame_ordinal)]
        )
        frame_identity = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:16]
        return {
            "event_kind": "record_frame.hit",
            "node_id": node_id,
            "instance_path": list(instance_path),
            "iteration_stack": list(iteration_stack),
            "record_frame_ordinal_in_session": self._record_frame_ordinal,
            "frame_identity": frame_identity,
            "pause_requested": False,
        }

    def request_action(self, session: dict, action: str) -> dict:
        debug_session = self._extract_debug_session(session)
        status = debug_session.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("debug session status is required")
        if not is_debug_action_allowed(status, action):
            raise ValueError(f"debug {action} is not allowed for status {status}")
        if action == "continue":
            session_patch = {
                "status": "running",
                "step_mode": None,
                "paused_reason": None,
                "last_control_action": "continue",
                "resume_skip_breakpoint_once": self._build_resume_skip_breakpoint_once(session),
                "exception_skip_node_once": self._build_exception_skip_node_once(session),
            }
            return {
                "action": action,
                "status": status,
                "next_status": "running",
                "session_patch": session_patch,
            }
        if action == "step_out" and not isinstance(
            debug_session.get("pending_component_pause"),
            dict,
        ):
            raise ValueError("debug step_out is only available inside a component")
        if action in {"step_over", "step_into", "step_out"}:
            previous_step_sequence = debug_session.get("step_sequence", 0)
            step_sequence = previous_step_sequence + 1 if isinstance(previous_step_sequence, int) else 1
            session_patch = {
                "status": "stepping",
                "step_mode": action,
                "paused_reason": "step_requested",
                "last_control_action": action,
                "step_sequence": step_sequence,
            }
            return {
                "action": action,
                "status": status,
                "next_status": "stepping",
                "session_patch": session_patch,
            }
        if action == "pause":
            session_patch = {
                "status": "paused",
                "paused_reason": "manual_pause",
                "last_control_action": "pause",
            }
            return {
                "action": action,
                "status": status,
                "next_status": "paused",
                "session_patch": session_patch,
            }
        if action == "abort":
            session_patch = {
                "status": "aborted",
                "paused_reason": "user_abort",
                "last_control_action": "abort",
                "pending_component_pause": None,
            }
            return {
                "action": action,
                "status": status,
                "next_status": "aborted",
                "session_patch": session_patch,
            }
        session_patch = {
            "status": status,
            "last_control_action": action,
        }
        return {
            "action": action,
            "status": status,
            "next_status": status,
            "session_patch": session_patch,
        }

    def apply_event(self, *, session: dict, event: dict) -> dict:
        debug_session = self._extract_debug_session(session)
        event_kind = event.get("event_kind")
        if event_kind == "breakpoint.hit":
            return {
                "paused_reason": "breakpoint_hit",
                "last_control_action": "breakpoint_hit",
                "last_breakpoint_frame_identity": event.get("frame_identity"),
            }
        if event_kind == "record_frame.hit":
            return {
                "last_control_action": "record_frame",
                "last_record_frame_identity": event.get("frame_identity"),
            }
        if event_kind == "debug.paused":
            previous_action = debug_session.get("last_control_action")
            return {
                "status": "paused",
                "paused_reason": event.get("reason"),
                "last_control_action": previous_action or "paused",
            }
        return {}

    def apply_variable_updates(
        self,
        *,
        session: dict,
        updates: dict,
        apply_mode: str,
    ) -> dict:
        if not isinstance(updates, dict):
            raise ValueError("field must be a JSON object: updates")
        normalized_apply_mode = apply_mode.strip() if isinstance(apply_mode, str) else ""
        if normalized_apply_mode not in {"staged", "immediate"}:
            raise ValueError("field must be one of {'staged', 'immediate'}: apply_mode")
        debug_session = self._extract_debug_session(session)
        status = debug_session.get("status")
        if not isinstance(status, str) or not is_debug_action_allowed(status, "variables_apply"):
            raise ValueError(f"debug variables_apply is not allowed for status {status}")
        current_snapshot = (
            session.get("variable_snapshot")
            if isinstance(session.get("variable_snapshot"), dict)
            else {}
        )
        descriptors = session.get("variable_descriptors") if isinstance(session.get("variable_descriptors"), dict) else {}
        for variable_name, next_value in updates.items():
            if not isinstance(variable_name, str) or not variable_name.strip():
                raise ValueError("debug variable name must be a non-empty string")
            if variable_name not in current_snapshot:
                raise ValueError(f"debug variable does not exist: {variable_name}")
            current_value = current_snapshot[variable_name]
            expected_type = (
                descriptors.get(variable_name, {}).get("value_type")
                if isinstance(descriptors.get(variable_name), dict)
                else self._describe_variable_type(current_value)
            )
            if not self._is_variable_value_compatible(
                current_value=current_value,
                next_value=next_value,
            ):
                raise DebugVariableValidationError(
                    f"debug variable type mismatch for {variable_name}: "
                    f"expected {expected_type}",
                    variable_name=variable_name,
                    expected_type=str(expected_type),
                    actual_type=self._describe_variable_type(next_value),
                )
        existing_pending = debug_session.get("pending_variable_overrides")
        pending_overrides = dict(existing_pending) if isinstance(existing_pending, dict) else {}
        next_snapshot = dict(current_snapshot)
        if normalized_apply_mode == "immediate":
            next_snapshot.update(deepcopy(updates))
            for variable_name in updates:
                pending_overrides.pop(variable_name, None)
        else:
            pending_overrides.update(deepcopy(updates))
        changed_at = datetime.now(timezone.utc).isoformat()
        existing_changes = session.get("variable_changes") if isinstance(session.get("variable_changes"), dict) else {}
        variable_changes = deepcopy(existing_changes)
        for variable_name, next_value in updates.items():
            original_change = existing_changes.get(variable_name)
            original_value = (
                original_change.get("original_value")
                if isinstance(original_change, dict) and "original_value" in original_change
                else current_snapshot[variable_name]
            )
            variable_changes[variable_name] = {
                "original_value": deepcopy(original_value),
                "current_value": deepcopy(next_value),
                "apply_mode": normalized_apply_mode,
                "changed_at": changed_at,
                "event_id": f"debug-variable-{hashlib.sha256(f'{variable_name}|{changed_at}'.encode('utf-8')).hexdigest()[:12]}",
                "pending": normalized_apply_mode == "staged",
            }
        return {
            "variable_snapshot": next_snapshot,
            "variable_changes": variable_changes,
            "session_patch": {
                "variable_apply_mode": normalized_apply_mode,
                "pending_variable_overrides": pending_overrides,
            },
        }

    def evaluate_breakpoint_gate(
        self,
        *,
        session: dict,
        breakpoint_config: dict,
        runtime_variables: dict,
        node_id: str,
        node_kind: str | None,
        session_id: str,
        instance_path: list[str],
        pause_timing: str,
    ) -> dict:
        key = self.build_breakpoint_state_key(
            instance_path=instance_path,
            pause_timing=pause_timing,
        )
        encounter_counts = self._restore_mapping(
            session=session,
            field_name="breakpoint_encounter_counts",
        )
        current_encounter_count = int(encounter_counts.get(key, 0)) + 1
        encounter_counts[key] = current_encounter_count

        once_consumed = self._restore_mapping(
            session=session,
            field_name="breakpoint_once_consumed",
        )
        session_patch = {
            "breakpoint_encounter_counts": encounter_counts,
            "breakpoint_once_consumed": once_consumed,
        }

        if bool(breakpoint_config.get("once")) and bool(once_consumed.get(key)):
            return {
                "should_pause": False,
                "reason": None,
                "diagnostic_event": None,
                "diagnostic_link": None,
                "emit_breakpoint_hit": False,
                "session_patch": session_patch,
            }

        raw_hit_count = breakpoint_config.get("hit_count", 1)
        try:
            hit_count = max(1, int(raw_hit_count))
        except (TypeError, ValueError):
            hit_count = 1
        if current_encounter_count < hit_count:
            return {
                "should_pause": False,
                "reason": None,
                "diagnostic_event": None,
                "diagnostic_link": None,
                "emit_breakpoint_hit": False,
                "session_patch": session_patch,
            }

        expression = breakpoint_config.get("expression")
        normalized_expression = self._normalize_expression(expression)
        if normalized_expression is not None:
            try:
                if not bool(_safe_eval_expression(normalized_expression, runtime_variables)):
                    return {
                        "should_pause": False,
                        "reason": None,
                        "diagnostic_event": None,
                        "diagnostic_link": None,
                        "emit_breakpoint_hit": False,
                        "session_patch": session_patch,
                    }
            except Exception as exc:
                diagnostic_event = {
                    "event_kind": "diagnostic.raised",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": node_id,
                    "node_kind": node_kind,
                    "severity": "error",
                    "message": f"breakpoint condition evaluation failed: {exc}",
                    "error_code": "debug.breakpoint_condition_error",
                }
                diagnostic_link = {
                    "diagnostic_id": f"debug:{session_id}:{node_id}:breakpoint-condition-error",
                    "category": "debug.breakpoint_condition_error",
                    "severity": "error",
                    "message": diagnostic_event["message"],
                    "graph_ref": {"node_id": node_id},
                }
                return {
                    "should_pause": True,
                    "reason": "breakpoint_condition_error",
                    "diagnostic_event": diagnostic_event,
                    "diagnostic_link": diagnostic_link,
                    "emit_breakpoint_hit": False,
                    "session_patch": session_patch,
                }

        if bool(breakpoint_config.get("once")):
            once_consumed[key] = True
            session_patch["breakpoint_once_consumed"] = once_consumed
        return {
            "should_pause": True,
            "reason": "breakpoint_hit",
            "diagnostic_event": None,
            "diagnostic_link": None,
            "emit_breakpoint_hit": True,
            "session_patch": session_patch,
        }

    @staticmethod
    def build_breakpoint_state_key(*, instance_path: list[str], pause_timing: str) -> str:
        return json.dumps(
            {
                "instance_path": list(instance_path),
                "pause_timing": pause_timing,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _extract_debug_session(session: dict | None) -> dict:
        if not isinstance(session, dict):
            return {}
        debug_session = session.get("debug_session")
        if isinstance(debug_session, dict):
            return debug_session
        return session

    @staticmethod
    def _extract_debug_events(session: dict | None) -> list[dict]:
        if not isinstance(session, dict):
            return []
        debug_events = session.get("debug_events")
        if not isinstance(debug_events, list):
            return []
        return [item for item in debug_events if isinstance(item, dict)]

    def _restore_mapping(self, *, session: dict, field_name: str) -> dict:
        debug_session = self._extract_debug_session(session)
        if isinstance(debug_session.get(field_name), dict):
            return deepcopy(debug_session.get(field_name))
        snapshot_debug_session = self._extract_debug_session(self._session_snapshot)
        if isinstance(snapshot_debug_session.get(field_name), dict):
            return deepcopy(snapshot_debug_session.get(field_name))
        return {}

    @staticmethod
    def _is_variable_value_compatible(*, current_value: object, next_value: object) -> bool:
        if current_value is None:
            return True
        if isinstance(current_value, bool):
            return isinstance(next_value, bool)
        if isinstance(current_value, int):
            return isinstance(next_value, int) and not isinstance(next_value, bool)
        if isinstance(current_value, float):
            return isinstance(next_value, (int, float)) and not isinstance(next_value, bool)
        return isinstance(next_value, type(current_value))

    @staticmethod
    def _describe_variable_type(value: object) -> str:
        if value is None:
            return "any"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return type(value).__name__

    @staticmethod
    def _normalize_expression(expression: object) -> str | None:
        if not isinstance(expression, str) or not expression.strip():
            return None
        normalized_expression = expression.strip()
        if (
            normalized_expression.startswith("${")
            and normalized_expression.endswith("}")
            and len(normalized_expression) > 3
        ):
            normalized_expression = normalized_expression[2:-1].strip()
        return normalized_expression or None

    def _build_resume_skip_breakpoint_once(self, session: dict) -> dict | None:
        debug_events = self._extract_debug_events(session)
        resumed_node_id = None
        for item in reversed(debug_events):
            if item.get("event_kind") != "debug.paused":
                continue
            node_id = item.get("node_id")
            if isinstance(node_id, str) and node_id.strip():
                resumed_node_id = node_id
            break
        if not isinstance(resumed_node_id, str) or not resumed_node_id.strip():
            return None
        for item in reversed(debug_events):
            if item.get("event_kind") != "breakpoint.hit":
                continue
            if item.get("node_id") != resumed_node_id:
                continue
            if item.get("pause_timing") != "before":
                return None
            return {
                "node_id": resumed_node_id,
                "pause_timing": "before",
                "iteration_stack": (
                    list(item.get("iteration_stack"))
                    if isinstance(item.get("iteration_stack"), list)
                    else []
                ),
            }
        return None

    def _build_exception_skip_node_once(self, session: dict) -> str | None:
        debug_session = self._extract_debug_session(session)
        if debug_session.get("paused_reason") != "exception_raised":
            return None
        runtime_preview = session.get("runtime_preview") if isinstance(session.get("runtime_preview"), dict) else {}
        current_node = runtime_preview.get("current_node") if isinstance(runtime_preview.get("current_node"), dict) else {}
        current_node_id = current_node.get("node_id")
        if isinstance(current_node_id, str) and current_node_id.strip():
            return current_node_id
        return None
