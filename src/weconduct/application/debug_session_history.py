from __future__ import annotations

import json
from pathlib import Path
import threading
import uuid

from weconduct.application.event_storage import migration as legacy_migration
from weconduct.application.event_storage.session_store import EventSessionStore

# Metadata keys carried in the session manifest (everything except the heavy
# append arrays, which live in the event/checkpoint segments).
_METADATA_KEYS = (
    "debug_session",
    "request",
    "stage_timeline",
    "object_index",
    "diagnostic_links",
    "runtime_preview",
    "runtime_preview_summary",
    "variable_snapshot",
    "variable_descriptors",
    "variable_changes",
)


class DebugSessionHistoryStore:
    """Delta-append history store (0.8.2).

    Public API is unchanged from the pre-0.8.2 full-rewrite store, but events
    and keyframes are appended incrementally to per-session segments and large
    checkpoint fields are deduplicated into blobs. ``persist_session_document``
    is called repeatedly with a growing document; only the records beyond what
    is already persisted are appended, making each call O(delta) instead of
    O(total). It preserves replace semantics: a divergent/shorter document
    rewrites the session's segments.
    """

    _root_locks: dict[str, threading.RLock] = {}
    _root_locks_guard = threading.Lock()
    _root_cursor_registry: dict[str, dict[str, tuple[int, str | None, int]]] = {}

    @classmethod
    def _root_cursors(cls, history_root: Path) -> dict[str, tuple[int, str | None, int]]:
        root_key = str(history_root.resolve())
        with cls._root_locks_guard:
            cursors = cls._root_cursor_registry.get(root_key)
            if cursors is None:
                cursors = {}
                cls._root_cursor_registry[root_key] = cursors
        return cursors

    def __init__(self, *, project_root: Path, retention_limit: int) -> None:
        self._project_root = project_root
        self._history_root = project_root / "debug-history"
        self._history_root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._history_root / "index.json"
        self._retention_limit = retention_limit
        self._store = EventSessionStore(self._history_root)
        self._lock = self._get_root_lock()
        # Per-session append cursor: (persisted_event_count, last_event_id,
        # persisted_keyframe_count). Keyed on the shared root so cursors survive
        # the fresh store instance created per service call.
        self._cursors = self._root_cursors(self._history_root)
        with self._lock:
            self._summaries: list[dict] = self._load_index()

    # -- incremental API (tests / lightweight callers) -------------------
    def start_session(self, session_meta: dict) -> None:
        with self._lock:
            session_id = str(session_meta["session_id"])
            self._store.write_metadata(session_id, {"debug_session": dict(session_meta)})

    def append_event(self, session_id: str, event: dict) -> None:
        with self._lock:
            self._store.append_events(session_id, [dict(event)])

    def append_keyframe(self, session_id: str, keyframe: dict) -> None:
        with self._lock:
            self._store.append_checkpoints(session_id, [dict(keyframe)])

    def finalize_session(self, session_id: str, *, final_status: str) -> None:
        with self._lock:
            metadata = self._store.read_metadata(session_id) or {}
            debug_session = dict(metadata.get("debug_session", {}))
            debug_session["status"] = final_status
            metadata["debug_session"] = debug_session
            self._store.write_metadata(session_id, metadata)
            payload = legacy_migration.normalize_payload(
                self._store.load_payload(session_id) or {}
            )
            self._upsert_summary(
                self._build_summary_from_payload(payload, final_status=final_status)
            )

    # -- primary hot-path API --------------------------------------------
    def persist_session_document(self, session_document: dict) -> None:
        debug_session = (
            session_document.get("debug_session")
            if isinstance(session_document.get("debug_session"), dict)
            else None
        )
        if not isinstance(debug_session, dict):
            raise ValueError("session_document missing required object: debug_session")
        session_id = debug_session.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_document missing required string: debug_session.session_id")

        events = self._as_list(session_document.get("debug_events"))
        keyframes = self._as_list(session_document.get("debug_keyframes"))
        snapshots = self._as_list(session_document.get("debug_snapshots"))
        self._validate_snapshot_records(events=events, snapshots=snapshots)

        with self._lock:
            self._store.write_metadata(session_id, self._extract_metadata(session_document))
            self._persist_events_and_keyframes(session_id, events, keyframes)
            self._upsert_summary(self._build_summary_from_session_document(session_document))

    def _persist_events_and_keyframes(
        self, session_id: str, events: list[dict], keyframes: list[dict]
    ) -> None:
        """Append the tail if the document extends what is persisted; else
        rewrite the segments (persist has replace semantics — callers may pass
        a divergent/shorter document, e.g. abort or a re-run).
        """
        cursor = self._cursors.get(session_id)
        can_append = False
        if cursor is not None:
            persisted_count, last_event_id, persisted_kf_count = cursor
            if len(events) >= persisted_count and len(keyframes) >= persisted_kf_count:
                if persisted_count == 0:
                    can_append = True
                else:
                    prev = events[persisted_count - 1] if persisted_count - 1 < len(events) else None
                    can_append = isinstance(prev, dict) and prev.get("event_id") == last_event_id
        if can_append:
            persisted_count, _, persisted_kf_count = cursor
            if len(events) > persisted_count:
                self._store.append_events(session_id, events[persisted_count:])
            if len(keyframes) > persisted_kf_count:
                self._store.append_checkpoints(session_id, keyframes[persisted_kf_count:])
        else:
            self._store.reset_segments(session_id)
            if events:
                self._store.append_events(session_id, events)
            if keyframes:
                self._store.append_checkpoints(session_id, keyframes)
        last_id = events[-1].get("event_id") if events else None
        self._cursors[session_id] = (len(events), last_id, len(keyframes))

    def list_session_summaries(self) -> list[dict]:
        with self._lock:
            self._summaries = self._load_index()
            return [dict(item) for item in self._summaries]

    def load_session_payload(self, session_id: str) -> dict | None:
        with self._lock:
            if self._store.exists(session_id):
                payload = self._store.load_payload(session_id)
                if payload is None:
                    return None
                return legacy_migration.normalize_payload(payload)
            return self._load_or_migrate_legacy(session_id)

    def _load_or_migrate_legacy(self, session_id: str) -> dict | None:
        legacy_path = self._history_root / f"{session_id}.msgpack"
        if not legacy_path.exists():
            return None
        try:
            payload = legacy_migration.migrate_legacy_file(legacy_path, session_id, self._store)
        except (ValueError, TypeError, OSError):
            self._mark_summary_legacy(session_id)
            return legacy_migration.read_legacy_readonly(legacy_path)
        legacy_path.replace(legacy_path.with_suffix(".msgpack.legacy"))
        return legacy_migration.normalize_payload(payload) if payload is not None else None

    @staticmethod
    def _as_list(value: object) -> list[dict]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @staticmethod
    def _extract_metadata(session_document: dict) -> dict:
        metadata: dict = {}
        for key in _METADATA_KEYS:
            value = session_document.get(key)
            if isinstance(value, dict):
                metadata[key] = dict(value)
            elif isinstance(value, list):
                metadata[key] = list(value)
        if "debug_session" not in metadata:
            metadata["debug_session"] = dict(session_document.get("debug_session", {}))
        return metadata

    # -- summaries -------------------------------------------------------
    def _build_summary_from_payload(self, payload: dict, *, final_status: str) -> dict:
        debug_session = payload.get("debug_session", {})
        events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
        return {
            "session_id": debug_session["session_id"],
            "started_at": debug_session["started_at"],
            "ended_at": debug_session.get("ended_at"),
            "status": final_status,
            "history_file": debug_session["session_id"],
            "graph_model_id": debug_session.get("graph_model_id"),
            "breakpoint_hit_count": sum(
                1 for item in events if item.get("event_kind") == "breakpoint.hit"
            ),
            "diagnostic_count": sum(
                1 for item in events if item.get("event_kind") == "diagnostic.raised"
            ),
            "paused_count": sum(
                1 for item in events if item.get("event_kind") == "debug.paused"
            ),
            "last_pause_node_id": next(
                (
                    item.get("node_id")
                    for item in reversed(events)
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
        debug_events = self._as_list(session_document.get("debug_events"))
        return {
            "session_id": session_id,
            "started_at": debug_session["started_at"],
            "ended_at": debug_session.get("ended_at"),
            "status": debug_session.get("status", "incomplete"),
            "history_file": session_id,
            "graph_model_id": object_index.get("graph_model_id"),
            "breakpoint_hit_count": sum(
                1 for item in debug_events if item.get("event_kind") == "breakpoint.hit"
            ),
            "diagnostic_count": len(session_document.get("diagnostic_links", []))
            if isinstance(session_document.get("diagnostic_links"), list)
            else 0,
            "paused_count": sum(
                1 for item in debug_events if item.get("event_kind") == "debug.paused"
            )
            or (1 if debug_session.get("status") == "paused" else 0),
            "last_pause_node_id": self._resolve_last_pause_node_id(session_document, debug_events),
            "session_label": None,
        }

    @staticmethod
    def _resolve_last_pause_node_id(session_document: dict, debug_events: list[dict]) -> str | None:
        for item in reversed(debug_events):
            if item.get("event_kind") == "debug.paused":
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

    @staticmethod
    def _validate_snapshot_records(*, events: list[dict], snapshots: list[dict]) -> None:
        event_ids = {
            item.get("event_id")
            for item in events
            if isinstance(item.get("event_id"), str)
        }
        snapshot_ids: set[str] = set()
        for snapshot in snapshots:
            for field_name in (
                "snapshot_id", "session_id", "event_id", "keyframe_id",
                "frame_identity", "event_kind", "recorded_at", "graph_model_id",
                "compilation_id", "node_id",
            ):
                if not isinstance(snapshot.get(field_name), str) or not snapshot[field_name].strip():
                    raise ValueError(f"debug snapshot missing required string: {field_name}")
            if snapshot["event_id"] not in event_ids:
                raise ValueError("debug snapshot event_id does not reference a persisted event")
            if snapshot["snapshot_id"] in snapshot_ids:
                raise ValueError("debug snapshot_id must be unique within a session")
            snapshot_ids.add(snapshot["snapshot_id"])

    # -- index -----------------------------------------------------------
    def _upsert_summary(self, summary: dict) -> None:
        self._summaries = self._load_index()
        session_id = summary.get("session_id")
        self._summaries = [
            item for item in self._summaries
            if not (isinstance(item, dict) and item.get("session_id") == session_id)
        ]
        self._summaries.insert(0, dict(summary))
        trimmed = self._summaries[self._retention_limit :]
        self._summaries = self._summaries[: self._retention_limit]
        self._save_index()
        for entry in trimmed:
            trimmed_id = entry.get("session_id")
            if isinstance(trimmed_id, str) and trimmed_id.strip():
                try:
                    self._store.delete_session(trimmed_id)
                    self._cursors.pop(trimmed_id, None)
                except PermissionError:
                    # 历史裁剪失败不应阻断当前调试会话持久化；
                    # 下次裁剪或人工清理时再处理遗留目录。
                    continue

    def _mark_summary_legacy(self, session_id: str) -> None:
        self._summaries = self._load_index()
        for item in self._summaries:
            if isinstance(item, dict) and item.get("session_id") == session_id:
                item["status"] = item.get("status", "incomplete")
                item["legacy_readonly"] = True
        self._save_index()

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._quarantine_corrupted_index()
            return []
        if not isinstance(payload, list):
            self._quarantine_corrupted_index()
            return []
        return [dict(item) for item in payload if isinstance(item, dict)]

    def _quarantine_corrupted_index(self) -> Path:
        backup_path = self._index_path.with_name(f"{self._index_path.name}.corrupt")
        if backup_path.exists():
            backup_path = self._index_path.with_name(
                f"{self._index_path.name}.{uuid.uuid4().hex}.corrupt"
            )
        self._index_path.replace(backup_path)
        return backup_path

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
