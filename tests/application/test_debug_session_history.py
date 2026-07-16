from pathlib import Path
import os
from threading import Thread

from weconduct.application.debug_session_history import DebugSessionHistoryStore
from weconduct.packaging.msgpack_codec import packb
import pytest


def _session_document(session_id: str, *, status: str = "paused") -> dict:
    return {
        "debug_session": {
            "session_id": session_id,
            "graph_model_id": "graph:workspace",
            "started_at": "2026-07-01T00:00:00+00:00",
            "status": status,
        },
        "object_index": {"graph_model_id": "graph:workspace"},
        "request": {"compilation_id": "compile-abc"},
        "runtime_preview": {"current_node": {"node_id": "node-1"}},
        "variable_snapshot": {"username": "history-user"},
        "debug_events": [
            {
                "event_id": f"{session_id}:event:00000000",
                "event_index": 0,
                "session_id": session_id,
                "event_kind": "debug.paused",
                "node_id": "node-1",
                "reason": "breakpoint_hit",
                "recorded_at": "2026-07-01T00:00:00+00:00",
                "instance_path": ["graph:workspace", "node-1"],
                "iteration_stack": [],
            }
        ],
        "debug_keyframes": [],
        "debug_snapshots": [],
    }


def test_history_store_writes_summary_index_and_session_dir(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    store.persist_session_document(_session_document("dbg-001"))

    summaries = store.list_session_summaries()
    assert summaries[0]["session_id"] == "dbg-001"
    assert summaries[0]["status"] == "paused"
    assert (tmp_path / "debug-history" / "sessions" / "dbg-001" / "manifest.json").exists()
    assert (tmp_path / "debug-history" / "sessions" / "dbg-001" / "events.seg").exists()


def test_history_store_delta_appends_only_new_events(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    document = _session_document("dbg-delta")
    store.persist_session_document(document)

    events_path = tmp_path / "debug-history" / "sessions" / "dbg-delta" / "events.seg"
    size_after_first = events_path.stat().st_size

    document["debug_events"].append(
        {
            "event_id": "dbg-delta:event:00000001",
            "event_index": 1,
            "session_id": "dbg-delta",
            "event_kind": "node.executed",
            "node_id": "node-2",
            "recorded_at": "2026-07-01T00:00:01+00:00",
            "instance_path": ["graph:workspace", "node-2"],
            "iteration_stack": [],
        }
    )
    store.persist_session_document(document)
    size_after_second = events_path.stat().st_size
    assert size_after_second > size_after_first

    payload = store.load_session_payload("dbg-delta")
    assert [e["event_index"] for e in payload["events"]] == [0, 1]


def test_history_store_rewrites_on_divergent_document(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    document = _session_document("dbg-div")
    document["debug_events"].append(
        {
            "event_id": "dbg-div:event:00000001",
            "event_index": 1,
            "session_id": "dbg-div",
            "event_kind": "node.executed",
            "node_id": "node-2",
            "recorded_at": "2026-07-01T00:00:01+00:00",
            "instance_path": ["graph:workspace", "node-2"],
            "iteration_stack": [],
        }
    )
    store.persist_session_document(document)
    assert len(store.load_session_payload("dbg-div")["events"]) == 2

    diverged = _session_document("dbg-div")  # only the original single event
    store.persist_session_document(diverged)
    assert [e["event_index"] for e in store.load_session_payload("dbg-div")["events"]] == [0]


def test_history_store_dedups_keyframe_and_snapshot_blob(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    document = _session_document("dbg-dedup")
    keyframe = {
        "keyframe_id": "dbg-dedup:event:00000000:keyframe",
        "snapshot_id": "dbg-dedup:event:00000000:snapshot",
        "event_id": "dbg-dedup:event:00000000",
        "event_index": 0,
        "session_id": "dbg-dedup",
        "event_kind": "debug.paused",
        "frame_identity": "dbg-dedup:event:00000000",
        "recorded_at": "2026-07-01T00:00:00+00:00",
        "graph_model_id": "graph:workspace",
        "compilation_id": "compile-abc",
        "node_id": "node-1",
        "variable_snapshot": {"shared": "value" * 100},
        "runtime_preview": {"current_node": {"node_id": "node-1"}},
    }
    document["debug_keyframes"] = [keyframe]
    document["debug_snapshots"] = [dict(keyframe)]
    store.persist_session_document(document)

    blobs = list((tmp_path / "debug-history" / "blobs").rglob("*.blob"))
    assert len(blobs) == 2  # variable_snapshot + runtime_preview, shared kf+snapshot

    payload = store.load_session_payload("dbg-dedup")
    assert payload["keyframes"][0]["variable_snapshot"] == {"shared": "value" * 100}
    assert len(payload["snapshots"]) == 1


def test_history_store_trims_old_sessions_by_retention_limit(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=2)
    for index in range(3):
        store.persist_session_document(_session_document(f"dbg-{index}", status="completed"))
    summaries = store.list_session_summaries()
    assert [item["session_id"] for item in summaries] == ["dbg-2", "dbg-1"]
    assert not (tmp_path / "debug-history" / "sessions" / "dbg-0").exists()


def test_history_store_reloads_paused_snapshot_without_rewriting_status(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    store.persist_session_document(_session_document("dbg-open-001", status="paused"))

    reloaded = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    summaries = reloaded.list_session_summaries()
    payload = reloaded.load_session_payload("dbg-open-001")

    assert summaries[0]["session_id"] == "dbg-open-001"
    assert summaries[0]["status"] == "paused"
    assert payload["debug_session"]["status"] == "paused"


def test_history_store_incremental_api_roundtrip(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    store.start_session(
        {
            "session_id": "dbg-inc",
            "graph_model_id": "graph:workspace",
            "started_at": "2026-07-01T00:00:00+00:00",
            "status": "running",
        }
    )
    store.append_event("dbg-inc", {"event_kind": "breakpoint.hit", "node_id": "node-1"})
    store.append_keyframe("dbg-inc", {"keyframe_id": "kf-1", "node_id": "node-1"})
    store.finalize_session("dbg-inc", final_status="completed")

    summaries = store.list_session_summaries()
    assert summaries[0]["session_id"] == "dbg-inc"
    assert summaries[0]["status"] == "completed"


def test_history_store_concurrent_read_never_sees_partial_frame(tmp_path: Path) -> None:
    writer = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    document = _session_document("dbg-concurrent")
    writer.persist_session_document(document)
    reader = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)

    payloads: list[dict | None] = []
    errors: list[BaseException] = []

    def read_loop() -> None:
        try:
            for _ in range(50):
                payloads.append(reader.load_session_payload("dbg-concurrent"))
        except BaseException as exc:  # pragma: no cover - reports captured error
            errors.append(exc)

    reader_thread = Thread(target=read_loop, daemon=True)
    reader_thread.start()
    for i in range(1, 20):
        document["debug_events"].append(
            {
                "event_id": f"dbg-concurrent:event:{i:08d}",
                "event_index": i,
                "session_id": "dbg-concurrent",
                "event_kind": "node.executed",
                "node_id": f"node-{i}",
                "recorded_at": "2026-07-01T00:00:00+00:00",
                "instance_path": ["graph:workspace", f"node-{i}"],
                "iteration_stack": [],
            }
        )
        writer.persist_session_document(document)
    reader_thread.join(timeout=2.0)

    assert errors == []
    for payload in payloads:
        if payload is None:
            continue
        indices = [e["event_index"] for e in payload["events"]]
        assert indices == list(range(len(indices)))


def test_history_store_migrates_legacy_msgpack_on_read(tmp_path: Path) -> None:
    history_root = tmp_path / "debug-history"
    history_root.mkdir(parents=True)
    legacy_payload = {
        "debug_session": {
            "session_id": "dbg-legacy",
            "graph_model_id": "graph:workspace",
            "started_at": "2026-07-01T00:00:00+00:00",
            "status": "completed",
        },
        "object_index": {"graph_model_id": "graph:workspace"},
        "events": [
            {"event_kind": "debug.paused", "node_id": "node-1", "reason": "breakpoint_hit"}
        ],
        "keyframes": [],
    }
    (history_root / "dbg-legacy.msgpack").write_bytes(packb(legacy_payload))
    (history_root / "index.json").write_text(
        '[{"session_id": "dbg-legacy", "status": "completed", "history_file": "dbg-legacy"}]',
        encoding="utf-8",
    )

    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    payload = store.load_session_payload("dbg-legacy")

    assert payload is not None
    assert payload["debug_session"]["session_id"] == "dbg-legacy"
    assert payload["events"][0]["event_id"] == "dbg-legacy:event:00000000"
    assert (history_root / "dbg-legacy.msgpack.legacy").exists()
    assert (history_root / "sessions" / "dbg-legacy" / "manifest.json").exists()


def test_history_store_quarantines_corrupted_index_and_recovers_empty(tmp_path: Path) -> None:
    history_root = tmp_path / "debug-history"
    history_root.mkdir(parents=True)
    index_path = history_root / "index.json"
    corrupted_payload = b"\x00" * 64
    index_path.write_bytes(corrupted_payload)

    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)

    assert store.list_session_summaries() == []
    assert index_path.exists() is False
    backup_paths = list(history_root.glob("index.json*.corrupt"))
    assert len(backup_paths) == 1
    assert backup_paths[0].read_bytes() == corrupted_payload


def test_history_store_keeps_latest_summary_when_trim_delete_is_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=2)
    import weconduct.application.event_storage.session_store as session_store_mod

    def failing_delete(self, session_id: str) -> None:
        raise PermissionError(os.strerror(5))

    for index in range(2):
        store.persist_session_document(_session_document(f"dbg-{index}", status="completed"))
    monkeypatch.setattr(
        session_store_mod.EventSessionStore, "delete_session", failing_delete
    )
    store.persist_session_document(_session_document("dbg-2", status="completed"))

    summaries = store.list_session_summaries()
    assert [item["session_id"] for item in summaries] == ["dbg-2", "dbg-1"]
