"""Blob dedup + session store tests (test plan §5, design §7)."""
from pathlib import Path

from weconduct.application.event_storage.blob_store import BlobError, BlobStore
from weconduct.application.event_storage.session_store import EventSessionStore
import pytest


def test_blob_dedups_identical_content(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    id_a = store.put({"big": "value" * 100})
    id_b = store.put({"big": "value" * 100})
    assert id_a == id_b
    assert len(list((tmp_path / "blobs").rglob("*.blob"))) == 1
    assert store.get(id_a) == {"big": "value" * 100}


def test_blob_missing_returns_none_via_try_get(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    assert store.try_get("deadbeef" * 8) is None
    with pytest.raises(BlobError):
        store.get("deadbeef" * 8)


def test_blob_corruption_detected(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    blob_id = store.put({"v": 1})
    path = (tmp_path / "blobs" / blob_id[:2] / f"{blob_id}.blob")
    path.write_bytes(b"tampered")
    assert store.try_get(blob_id) is None  # degrades, does not crash


def test_session_store_delta_and_reconstruct(tmp_path: Path) -> None:
    store = EventSessionStore(tmp_path)
    store.write_metadata("s", {"debug_session": {"session_id": "s", "status": "paused"}})
    store.append_events("s", [{"event_index": 0}, {"event_index": 1}])
    store.append_events("s", [{"event_index": 2}])
    store.append_checkpoints(
        "s",
        [
            {
                "keyframe_id": "kf-0",
                "snapshot_id": "snap-0",
                "variable_snapshot": {"x": 1},
                "runtime_preview": {"current_node": {"node_id": "n0"}},
            }
        ],
    )
    payload = store.load_payload("s")
    assert [e["event_index"] for e in payload["events"]] == [0, 1, 2]
    assert payload["keyframes"][0]["variable_snapshot"] == {"x": 1}
    assert len(payload["snapshots"]) == 1  # derived from snapshot_id


def test_session_store_reset_segments_rewrites(tmp_path: Path) -> None:
    store = EventSessionStore(tmp_path)
    store.write_metadata("s", {"debug_session": {"session_id": "s"}})
    store.append_events("s", [{"event_index": 0}, {"event_index": 1}])
    store.reset_segments("s")
    store.append_events("s", [{"event_index": 99}])
    payload = store.load_payload("s")
    assert [e["event_index"] for e in payload["events"]] == [99]


def test_session_store_recovers_tail_once_then_appends(tmp_path: Path) -> None:
    store = EventSessionStore(tmp_path)
    store.write_metadata("s", {"debug_session": {"session_id": "s"}})
    store.append_events("s", [{"event_index": 0}])
    # Simulate a torn tail from a prior crashed process.
    seg_path = tmp_path / "sessions" / "s" / "events.seg"
    with open(seg_path, "ab") as h:
        h.write(b"\x00\x00\x00\x20torn")
    # A fresh store (new process) recovers the tail on first append.
    fresh = EventSessionStore(tmp_path)
    fresh.append_events("s", [{"event_index": 1}])
    payload = fresh.load_payload("s")
    assert [e["event_index"] for e in payload["events"]] == [0, 1]
