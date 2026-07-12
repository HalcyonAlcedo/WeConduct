from __future__ import annotations

import json
from pathlib import Path
import threading
import uuid

from weconduct.packaging.msgpack_codec import packb
from weconduct.packaging.msgpack_codec import unpackb

class DebugSessionHistoryStore:
    _root_locks: dict[str, threading.RLock] = {}
    _root_locks_guard = threading.Lock()

    def __init__(self, *, project_root: Path, retention_limit: int) -> None:
        self._project_root = project_root
        self._history_root = project_root / "debug-history"
        self._history_root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._history_root / "index.json"
        self._retention_limit = retention_limit
        self._session_payloads: dict[str, dict] = {}
        self._lock = self._get_root_lock()
        with self._lock:
            self._summaries: list[dict] = self._load_index()

    def start_session(self, session_meta: dict) -> None:
        with self._lock:
            session_id = str(session_meta["session_id"])
            self._session_payloads[session_id] = {
                "debug_session": dict(session_meta),
                "events": [],
                "keyframes": [],
            }

    def append_event(self, session_id: str, event: dict) -> None:
        with self._lock:
            self._session_payloads[session_id]["events"].append(dict(event))

    def append_keyframe(self, session_id: str, keyframe: dict) -> None:
        with self._lock:
            self._session_payloads[session_id]["keyframes"].append(dict(keyframe))

    def finalize_session(self, session_id: str, *, final_status: str) -> None:
        with self._lock:
            payload = self._session_payloads[session_id]
            payload["debug_session"]["status"] = final_status
            self._write_payload(
                session_id,
                payload,
                summary=self._build_summary_from_payload(payload, final_status=final_status),
            )

    def persist_session_document(self, session_document: dict) -> None:
        debug_session = (
            session_document.get("debug_session")
            if isinstance(session_document.get("debug_session"), dict)
            else None
        )
        object_index = (
            session_document.get("object_index")
            if isinstance(session_document.get("object_index"), dict)
            else {}
        )
        if not isinstance(debug_session, dict):
            raise ValueError("session_document missing required object: debug_session")
        session_id = debug_session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_document missing required string: debug_session.session_id")
        payload = {
            "debug_session": dict(debug_session),
            "request": dict(session_document.get("request", {}))
            if isinstance(session_document.get("request"), dict)
            else {},
            "stage_timeline": list(session_document.get("stage_timeline", []))
            if isinstance(session_document.get("stage_timeline"), list)
            else [],
            "object_index": dict(object_index),
            "diagnostic_links": list(session_document.get("diagnostic_links", []))
            if isinstance(session_document.get("diagnostic_links"), list)
            else [],
            "runtime_preview": dict(session_document.get("runtime_preview", {}))
            if isinstance(session_document.get("runtime_preview"), dict)
            else {},
            "runtime_preview_summary": dict(session_document.get("runtime_preview_summary", {}))
            if isinstance(session_document.get("runtime_preview_summary"), dict)
            else {},
            "variable_snapshot": dict(session_document.get("variable_snapshot", {}))
            if isinstance(session_document.get("variable_snapshot"), dict)
            else {},
            "variable_descriptors": dict(session_document.get("variable_descriptors", {}))
            if isinstance(session_document.get("variable_descriptors"), dict)
            else {},
            "variable_changes": dict(session_document.get("variable_changes", {}))
            if isinstance(session_document.get("variable_changes"), dict)
            else {},
            "events": list(session_document.get("debug_events", []))
            if isinstance(session_document.get("debug_events"), list)
            else [],
            "keyframes": list(session_document.get("debug_keyframes", []))
            if isinstance(session_document.get("debug_keyframes"), list)
            else [],
            "snapshots": list(session_document.get("debug_snapshots", []))
            if isinstance(session_document.get("debug_snapshots"), list)
            else [],
        }
        self._validate_snapshot_records(payload)
        with self._lock:
            self._session_payloads[session_id] = payload
            self._write_payload(
                session_id,
                payload,
                summary=self._build_summary_from_session_document(session_document),
            )

    @staticmethod
    def _validate_snapshot_records(payload: dict) -> None:
        snapshots = payload.get("snapshots")
        events = payload.get("events") if isinstance(payload.get("events"), list) else []
        if not isinstance(snapshots, list):
            return
        event_ids = {
            item.get("event_id")
            for item in events
            if isinstance(item, dict) and isinstance(item.get("event_id"), str)
        }
        snapshot_ids: set[str] = set()
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                raise ValueError("debug snapshot must be an object")
            for field_name in (
                "snapshot_id",
                "session_id",
                "event_id",
                "keyframe_id",
                "frame_identity",
                "event_kind",
                "recorded_at",
                "graph_model_id",
                "compilation_id",
                "node_id",
            ):
                if not isinstance(snapshot.get(field_name), str) or not snapshot[field_name].strip():
                    raise ValueError(f"debug snapshot missing required string: {field_name}")
            if snapshot["event_id"] not in event_ids:
                raise ValueError("debug snapshot event_id does not reference a persisted event")
            if snapshot["snapshot_id"] in snapshot_ids:
                raise ValueError("debug snapshot_id must be unique within a session")
            snapshot_ids.add(snapshot["snapshot_id"])

    def list_session_summaries(self) -> list[dict]:
        with self._lock:
            self._summaries = self._load_index()
            return [dict(item) for item in self._summaries]

    def load_session_payload(self, session_id: str) -> dict | None:
        with self._lock:
            self._summaries = self._load_index()
            summary = next(
                (
                    item
                    for item in self._summaries
                    if isinstance(item, dict) and item.get("session_id") == session_id
                ),
                None,
            )
            if summary is None:
                return None
            history_file = summary.get("history_file")
            if not isinstance(history_file, str) or not history_file.strip():
                return None
            payload_path = self._history_root / history_file
            if not payload_path.exists():
                return None
            payload = unpackb(payload_path.read_bytes())
            if not isinstance(payload, dict):
                return None
            return self._normalize_session_payload(payload)

    def _build_summary_from_payload(self, payload: dict, *, final_status: str) -> dict:
        return {
            "session_id": payload["debug_session"]["session_id"],
            "started_at": payload["debug_session"]["started_at"],
            "ended_at": payload["debug_session"].get("ended_at"),
            "status": final_status,
            "history_file": f"{payload['debug_session']['session_id']}.msgpack",
            "graph_model_id": payload["debug_session"]["graph_model_id"],
            "breakpoint_hit_count": sum(
                1 for item in payload["events"] if item.get("event_kind") == "breakpoint.hit"
            ),
            "diagnostic_count": sum(
                1 for item in payload["events"] if item.get("event_kind") == "diagnostic.raised"
            ),
            "paused_count": sum(
                1 for item in payload["events"] if item.get("event_kind") == "debug.paused"
            ),
            "last_pause_node_id": next(
                (
                    item.get("node_id")
                    for item in reversed(payload["events"])
                    if item.get("event_kind") == "debug.paused"
                ),
                None,
            ),
            "session_label": None,
        }

    def _build_summary_from_session_document(self, session_document: dict) -> dict:
        debug_session = session_document["debug_session"]
        object_index = (
            session_document.get("object_index")
            if isinstance(session_document.get("object_index"), dict)
            else {}
        )
        session_id = debug_session["session_id"]
        return {
            "session_id": session_id,
            "started_at": debug_session["started_at"],
            "ended_at": debug_session.get("ended_at"),
            "status": debug_session.get("status", "incomplete"),
            "history_file": f"{session_id}.msgpack",
            "graph_model_id": object_index.get("graph_model_id"),
            "breakpoint_hit_count": sum(
                1
                for item in session_document.get("debug_events", [])
                if isinstance(item, dict) and item.get("event_kind") == "breakpoint.hit"
            )
            if isinstance(session_document.get("debug_events"), list)
            else 0,
            "diagnostic_count": len(session_document.get("diagnostic_links", []))
            if isinstance(session_document.get("diagnostic_links"), list)
            else 0,
            "paused_count": sum(
                1
                for item in session_document.get("debug_events", [])
                if isinstance(item, dict) and item.get("event_kind") == "debug.paused"
            )
            if isinstance(session_document.get("debug_events"), list)
            else (1 if debug_session.get("status") == "paused" else 0),
            "last_pause_node_id": self._resolve_last_pause_node_id(session_document),
            "session_label": None,
        }

    def _write_payload(self, session_id: str, payload: dict, *, summary: dict) -> None:
        filename = f"{session_id}.msgpack"
        history_file = self._history_root / filename
        temp_history_file = history_file.with_name(
            f"{history_file.name}.{uuid.uuid4().hex}.tmp"
        )
        temp_history_file.write_bytes(packb(payload))
        temp_history_file.replace(history_file)
        self._upsert_summary({**summary, "history_file": filename})

    def _upsert_summary(self, summary: dict) -> None:
        self._summaries = self._load_index()
        session_id = summary.get("session_id")
        self._summaries = [
            item
            for item in self._summaries
            if not (isinstance(item, dict) and item.get("session_id") == session_id)
        ]
        self._summaries.insert(0, dict(summary))
        trimmed = self._summaries[self._retention_limit :]
        self._summaries = self._summaries[: self._retention_limit]
        self._save_index()
        for entry in trimmed:
            history_file = entry.get("history_file")
            if isinstance(history_file, str) and history_file.strip():
                payload_path = self._history_root / history_file
                if payload_path.exists():
                    try:
                        payload_path.unlink()
                    except PermissionError:
                        # 历史裁剪失败不应阻断当前调试会话持久化；
                        # 下次裁剪或人工清理时再处理遗留文件。
                        continue

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("debug history index must be valid JSON") from exc
        if not isinstance(payload, list):
            raise ValueError("debug history index must be a JSON array")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _normalize_session_payload(self, payload: dict) -> dict:
        debug_session = payload.get("debug_session")
        session_id = (
            debug_session.get("session_id")
            if isinstance(debug_session, dict) and isinstance(debug_session.get("session_id"), str)
            else "debug-session"
        )
        object_index = payload.get("object_index")
        graph_model_id = (
            object_index.get("graph_model_id")
            if isinstance(object_index, dict) and isinstance(object_index.get("graph_model_id"), str)
            else None
        )
        events = payload.get("events")
        if isinstance(events, list):
            normalized_events: list[dict] = []
            for event_index, event in enumerate(events):
                if not isinstance(event, dict):
                    continue
                node_id = event.get("node_id")
                instance_path = event.get("instance_path")
                if not isinstance(instance_path, list):
                    instance_path = [
                        item
                        for item in (graph_model_id, node_id)
                        if isinstance(item, str) and item.strip()
                    ]
                normalized_events.append(
                    {
                        **event,
                        "event_id": event.get("event_id")
                        if isinstance(event.get("event_id"), str) and event.get("event_id").strip()
                        else f"{session_id}:event:{event_index:08d}",
                        "event_index": event_index,
                        "recorded_at": event.get("recorded_at")
                        if isinstance(event.get("recorded_at"), str)
                        and event.get("recorded_at").strip()
                        else (
                            debug_session.get("started_at")
                            if isinstance(debug_session, dict)
                            else None
                        ),
                        "session_id": session_id,
                        "instance_path": list(instance_path),
                        "iteration_stack": list(event.get("iteration_stack"))
                        if isinstance(event.get("iteration_stack"), list)
                        else [],
                    }
                )
            payload["events"] = normalized_events
        keyframes = payload.get("keyframes")
        if isinstance(keyframes, list):
            normalized_keyframes: list[dict] = []
            normalized_events = payload.get("events") if isinstance(payload.get("events"), list) else []
            event_index_by_id = {
                event.get("event_id"): event.get("event_index")
                for event in normalized_events
                if isinstance(event, dict)
                and isinstance(event.get("event_id"), str)
                and isinstance(event.get("event_index"), int)
            }
            for keyframe_index, keyframe in enumerate(keyframes):
                if not isinstance(keyframe, dict):
                    continue
                event_index = keyframe.get("event_index")
                if not isinstance(event_index, int):
                    event_index = event_index_by_id.get(keyframe.get("event_id"))
                if not isinstance(event_index, int):
                    event_index = len(normalized_events) + keyframe_index
                keyframe_id = keyframe.get("keyframe_id")
                if not isinstance(keyframe_id, str) or not keyframe_id.strip():
                    keyframe_id = f"{session_id}:keyframe:{event_index:08d}:{keyframe_index:04d}"
                normalized_keyframes.append(
                    {
                        **keyframe,
                        "keyframe_id": keyframe_id,
                        "event_index": event_index,
                    }
                )
            payload["keyframes"] = normalized_keyframes
        return payload

    def _save_index(self) -> None:
        temp_index_path = self._index_path.with_name(
            f"{self._index_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temp_index_path.write_text(
            json.dumps(self._summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_index_path.replace(self._index_path)

    def _get_root_lock(self) -> threading.RLock:
        root_key = str(self._history_root.resolve())
        with self._root_locks_guard:
            lock = self._root_locks.get(root_key)
            if lock is None:
                lock = threading.RLock()
                self._root_locks[root_key] = lock
        return lock

    def _resolve_last_pause_node_id(self, session_document: dict) -> str | None:
        debug_events = (
            session_document.get("debug_events")
            if isinstance(session_document.get("debug_events"), list)
            else []
        )
        for item in reversed(debug_events):
            if isinstance(item, dict) and item.get("event_kind") == "debug.paused":
                node_id = item.get("node_id")
                if isinstance(node_id, str) and node_id.strip():
                    return node_id
        runtime_preview = (
            session_document.get("runtime_preview")
            if isinstance(session_document.get("runtime_preview"), dict)
            else {}
        )
        current_node = runtime_preview.get("current_node")
        if isinstance(current_node, dict):
            node_id = current_node.get("node_id")
            if isinstance(node_id, str) and node_id.strip():
                return node_id
        return None
