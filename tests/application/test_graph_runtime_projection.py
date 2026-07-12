from weconduct.application.graph_runtime_projection import GraphRuntimeProjectionBuilder


def test_projection_builder_marks_parallel_active_paths() -> None:
    builder = GraphRuntimeProjectionBuilder()
    projection = builder.build_live_projection(
        node_states=[
            {"node_id": "node-a", "node_status": "running"},
            {"node_id": "node-b", "node_status": "waiting"},
        ],
        active_paths=[["node-start", "node-a"], ["node-start", "node-b"]],
        paused_node_id=None,
        record_frame_node_ids=["node-b"],
        skipped_node_ids=["node-c"],
    )
    assert projection["node_status_by_id"]["node-a"] == "running"
    assert len(projection["active_paths"]) == 2
    assert projection["record_frame_node_ids"] == ["node-b"]
    assert projection["skipped_node_ids"] == ["node-c"]


def test_projection_builder_builds_history_projection_snapshot() -> None:
    builder = GraphRuntimeProjectionBuilder()
    projection = builder.build_history_projection(
        keyframe={
            "node_status_by_id": {"node-a": "paused"},
            "active_paths": [["node-start", "node-a"]],
            "record_frame_node_ids": ["node-b"],
            "skipped_node_ids": ["node-c"],
        },
        event_index=3,
        keyframe_id="kf-3",
    )
    assert projection["mode"] == "history"
    assert projection["history_event_index"] == 3
    assert projection["history_keyframe_id"] == "kf-3"
    assert projection["node_status_by_id"]["node-a"] == "paused"
    assert projection["record_frame_node_ids"] == ["node-b"]
    assert projection["skipped_node_ids"] == ["node-c"]


def test_projection_builder_owns_snapshot_and_event_projection_rules() -> None:
    builder = GraphRuntimeProjectionBuilder()
    preview = {
        "executed_node_ids": ["node-done"],
        "queued_node_ids": ["node-wait"],
        "current_node": {"node_id": "node-paused"},
        "active_paths": [["node-done", "node-paused"]],
    }
    events = [
        {"event_index": 1, "event_kind": "record_frame.hit", "node_id": "node-done"},
        {"event_index": 3, "event_kind": "node.skipped", "node_id": "node-future"},
    ]

    projection = builder.build_history_from_snapshot(
        preview=preview,
        events=events,
        paused=True,
        event_index=1,
        keyframe_id="kf-1",
    )

    assert projection["node_status_by_id"] == {
        "node-done": "completed",
        "node-wait": "waiting",
        "node-paused": "paused",
    }
    assert projection["active_paths"] == [["node-done", "node-paused"]]
    assert projection["paused_node_id"] == "node-paused"
    assert projection["record_frame_node_ids"] == ["node-done"]
    assert projection["skipped_node_ids"] == []
