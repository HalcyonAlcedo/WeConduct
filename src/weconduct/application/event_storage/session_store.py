"""Per-session append store: manifest + event segment + checkpoint segment.

Replaces the monolithic ``{session_id}.msgpack`` full-document rewrite. Events
and checkpoints are appended (O(1) per record); the small manifest is
atomically rewritten only on metadata change (start / status / finalize).
Large checkpoint fields are externalized to the shared blob store and rehydrated
on read, so ``load_payload`` reproduces the legacy payload shape for existing
API/UI consumers (design doc §4, §7).
"""
from __future__ import annotations

import json
from pathlib import Path
import uuid

from weconduct.application.event_storage.blob_store import BlobStore
from weconduct.application.event_storage.frame import (
    RECORD_KIND_CHECKPOINT,
    RECORD_KIND_EVENT,
)
from weconduct.application.event_storage.segment import Segment

MANIFEST_VERSION = 1

# Checkpoint fields moved to blobs to avoid repeated full payloads.
_BLOB_FIELDS = (
    "variable_snapshot",
    "variable_descriptors",
    "runtime_preview",
    "runtime_preview_summary",
    "node_input_snapshot",
    "node_output_snapshot",
)


class EventSessionStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._sessions_dir = self._root / "sessions"
        self._blobs = BlobStore(self._root / "blobs")
        # Segments whose tail has been recovered in this process. Recovery
        # scans the whole segment (O(n)); doing it once per segment keeps
        # append O(1). Keyed by resolved segment path.
        self._recovered: set[str] = set()

    def _recover_once(self, seg: Segment) -> None:
        key = str(seg.path.resolve())
        if key in self._recovered:
            return
        seg.recover_tail()
        self._recovered.add(key)

    # -- layout ----------------------------------------------------------
    def session_dir(self, session_id: str) -> Path:
        return self._sessions_dir / session_id

    def _manifest_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "manifest.json"

    def _events(self, session_id: str) -> Segment:
        return Segment(self.session_dir(session_id) / "events.seg", record_kind=RECORD_KIND_EVENT)

    def _checkpoints(self, session_id: str) -> Segment:
        return Segment(
            self.session_dir(session_id) / "checkpoints.seg",
            record_kind=RECORD_KIND_CHECKPOINT,
        )

    def exists(self, session_id: str) -> bool:
        return self._manifest_path(session_id).exists()

    # -- writes ----------------------------------------------------------
    def write_metadata(self, session_id: str, metadata: dict) -> None:
        """Atomically (re)write the small session manifest."""
        path = self._manifest_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {"manifest_version": MANIFEST_VERSION, **metadata}
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def event_count(self, session_id: str) -> int:
        seg = self._events(session_id)
        if not seg.path.exists():
            return 0
        return len(seg.read_all())

    def checkpoint_count(self, session_id: str) -> int:
        seg = self._checkpoints(session_id)
        if not seg.path.exists():
            return 0
        return len(seg.read_all())

    def append_events(self, session_id: str, events: list[dict]) -> int:
        seg = self._events(session_id)
        seg.ensure_initialized()
        self._recover_once(seg)
        appended = 0
        for event in events:
            seg.append(event)
            appended += 1
        return appended

    def append_checkpoints(self, session_id: str, checkpoints: list[dict]) -> int:
        """Externalize large fields to blobs, then append checkpoint records."""
        seg = self._checkpoints(session_id)
        seg.ensure_initialized()
        self._recover_once(seg)
        appended = 0
        for checkpoint in checkpoints:
            seg.append(self._externalize(checkpoint))
            appended += 1
        return appended

    def _externalize(self, checkpoint: dict) -> dict:
        record = dict(checkpoint)
        for field in _BLOB_FIELDS:
            if field in record:
                record[f"{field}_blob"] = self._blobs.put(record[field])
                del record[field]
        return record

    def _rehydrate(self, record: dict) -> dict:
        checkpoint = dict(record)
        for field in _BLOB_FIELDS:
            blob_key = f"{field}_blob"
            if blob_key in checkpoint:
                value = self._blobs.try_get(checkpoint.get(blob_key))
                checkpoint[field] = value if value is not None else None
                del checkpoint[blob_key]
        return checkpoint

    # -- reads -----------------------------------------------------------
    def read_metadata(self, session_id: str) -> dict | None:
        path = self._manifest_path(session_id)
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        document.pop("manifest_version", None)
        return document

    def read_events(self, session_id: str, start: int = 0, end: int | None = None) -> list[dict]:
        seg = self._events(session_id)
        if not seg.path.exists():
            return []
        return list(seg.read_range(start, end))

    def read_checkpoints(self, session_id: str) -> list[dict]:
        seg = self._checkpoints(session_id)
        if not seg.path.exists():
            return []
        return [self._rehydrate(record) for record in seg.read_all()]

    def load_payload(self, session_id: str) -> dict | None:
        """Reconstruct the legacy full-document payload shape."""
        metadata = self.read_metadata(session_id)
        if metadata is None:
            return None
        keyframes = self.read_checkpoints(session_id)
        snapshots = [
            kf for kf in keyframes
            if isinstance(kf.get("snapshot_id"), str) and kf["snapshot_id"].strip()
        ]
        payload = dict(metadata)
        payload["events"] = self.read_events(session_id)
        payload["keyframes"] = keyframes
        payload["snapshots"] = snapshots
        return payload

    def reset_segments(self, session_id: str) -> None:
        """Drop the event/checkpoint segments so they can be rewritten.

        Used when an incoming full document diverges from what is persisted
        (replace semantics). Blobs are global and left for GC.
        """
        for seg_name in ("events.seg", "checkpoints.seg"):
            seg_path = self.session_dir(session_id) / seg_name
            if seg_path.exists():
                seg_path.unlink()

    def delete_session(self, session_id: str) -> None:
        import shutil

        target = self.session_dir(session_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
