from pathlib import Path
import os
from threading import Event, Thread
from time import sleep

from weconduct.application.debug_session_history import DebugSessionHistoryStore
import pytest


def test_debug_history_store_writes_session_file_and_summary_index(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(
        project_root=tmp_path,
        retention_limit=10,
    )

    session_meta = {
        "session_id": "dbg-001",
        "graph_model_id": "graph:workspace",
        "started_at": "2026-07-01T00:00:00+00:00",
        "status": "running",
    }
    store.start_session(session_meta)
    store.append_event("dbg-001", {"event_kind": "breakpoint.hit", "node_id": "node-1"})
    store.append_keyframe(
        "dbg-001",
        {
            "keyframe_id": "kf-001",
            "node_id": "node-1",
            "instance_path": ["graph:workspace", "node-1"],
            "iteration_stack": [],
        },
    )
    store.finalize_session("dbg-001", final_status="completed")

    summary = store.list_session_summaries()
    assert summary[0]["session_id"] == "dbg-001"
    assert summary[0]["status"] == "completed"
    assert summary[0]["history_file"].endswith(".msgpack")
    assert (tmp_path / "debug-history" / summary[0]["history_file"]).exists()


def test_debug_history_store_trims_old_sessions_by_retention_limit(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=2)
    for index in range(3):
        session_id = f"dbg-{index}"
        store.start_session(
            {
                "session_id": session_id,
                "graph_model_id": "graph:workspace",
                "started_at": f"2026-07-01T00:00:0{index}+00:00",
                "status": "running",
            }
        )
        store.finalize_session(session_id, final_status="completed")
    summaries = store.list_session_summaries()
    assert [item["session_id"] for item in summaries] == ["dbg-2", "dbg-1"]


def test_debug_history_store_keeps_latest_summary_when_trim_delete_is_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=2)
    locked_path = tmp_path / "debug-history" / "dbg-0.msgpack"
    original_unlink = Path.unlink

    def failing_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self == locked_path:
            raise PermissionError(os.strerror(5))
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    for index in range(3):
        session_id = f"dbg-{index}"
        store.start_session(
            {
                "session_id": session_id,
                "graph_model_id": "graph:workspace",
                "started_at": f"2026-07-01T00:00:0{index}+00:00",
                "status": "running",
            }
        )
        store.finalize_session(session_id, final_status="completed")

    summaries = store.list_session_summaries()
    assert [item["session_id"] for item in summaries] == ["dbg-2", "dbg-1"]


def test_debug_history_store_reloads_paused_snapshot_without_rewriting_status(tmp_path: Path) -> None:
    store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    session_document = {
        "debug_session": {
            "session_id": "dbg-open-001",
            "graph_model_id": "graph:workspace",
            "started_at": "2026-07-01T00:00:00+00:00",
            "status": "paused",
        },
        "request": {},
        "stage_timeline": [],
        "object_index": {"graph_model_id": "graph:workspace"},
        "diagnostic_links": [],
        "runtime_preview": {
            "scheduler_mode": "static",
            "queued_node_ids": [],
            "executed_node_ids": [],
            "current_node": {"node_id": "node-1"},
        },
        "runtime_preview_summary": {},
        "variable_snapshot": {"username": "history-user"},
        "debug_events": [{"event_kind": "debug.paused", "node_id": "node-1", "reason": "breakpoint_hit"}],
        "debug_keyframes": [],
    }
    store.persist_session_document(session_document)

    reloaded_store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    summaries = reloaded_store.list_session_summaries()
    payload = reloaded_store.load_session_payload("dbg-open-001")

    assert summaries[0]["session_id"] == "dbg-open-001"
    assert summaries[0]["status"] == "paused"
    assert isinstance(payload, dict)
    assert payload["debug_session"]["status"] == "paused"


def test_debug_history_store_never_exposes_partial_msgpack_during_concurrent_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_document = {
        "debug_session": {
            "session_id": "dbg-concurrent-001",
            "graph_model_id": "graph:workspace",
            "started_at": "2026-07-01T00:00:00+00:00",
            "status": "paused",
        },
        "object_index": {"graph_model_id": "graph:workspace"},
        "variable_snapshot": {"value": "before"},
        "debug_events": [],
        "debug_keyframes": [],
    }
    writer_store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    writer_store.persist_session_document(session_document)
    reader_store = DebugSessionHistoryStore(project_root=tmp_path, retention_limit=10)
    original_write_bytes = Path.write_bytes
    half_written = Event()
    release_write = Event()

    def slow_write_bytes(path: Path, data: bytes) -> int:
        if path.name.startswith("dbg-concurrent-001.msgpack"):
            split_index = max(len(data) // 2, 1)
            with path.open("wb") as handle:
                handle.write(data[:split_index])
                handle.flush()
                os.fsync(handle.fileno())
                half_written.set()
                assert release_write.wait(timeout=1.0), "concurrent history write was not released"
                handle.write(data[split_index:])
            return len(data)
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", slow_write_bytes)
    updated_document = {
        **session_document,
        "variable_snapshot": {"value": "after"},
    }
    writer_errors: list[BaseException] = []
    reader_errors: list[BaseException] = []
    reader_payloads: list[dict | None] = []

    def write_updated_document() -> None:
        try:
            writer_store.persist_session_document(updated_document)
        except BaseException as exc:  # pragma: no cover - assertion reports captured error
            writer_errors.append(exc)

    def read_during_write() -> None:
        try:
            reader_payloads.append(reader_store.load_session_payload("dbg-concurrent-001"))
        except BaseException as exc:  # pragma: no cover - assertion reports captured error
            reader_errors.append(exc)

    writer_thread = Thread(target=write_updated_document, daemon=True)
    writer_thread.start()
    assert half_written.wait(timeout=1.0), "history writer did not reach partial payload state"
    reader_thread = Thread(target=read_during_write, daemon=True)
    reader_thread.start()
    sleep(0.05)
    release_write.set()
    writer_thread.join(timeout=1.0)
    reader_thread.join(timeout=1.0)

    assert writer_errors == []
    assert reader_errors == []
    assert reader_payloads[0]["variable_snapshot"]["value"] in {"before", "after"}


def test_debug_history_store_quarantines_corrupted_index_and_recovers_empty(
    tmp_path: Path,
) -> None:
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
