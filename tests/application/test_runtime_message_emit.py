from __future__ import annotations

from weconduct.application import CompilationWorkbenchService


def _build_message_graph() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-start",
                "lowered_kind": "control",
                "source_anchor_ref": "n-node-start",
                "expansion_role": "flow.start",
                "display_name": "流程入口",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    }
                ],
                "node_config": {"initial_variables": {}},
            },
            {
                "node_id": "node-message",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-message",
                "expansion_role": "message:emit",
                "display_name": "消息",
                "node_kind": "message.emit",
                "position": {"x": 160, "y": 0},
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {"message": "任务已完成", "severity": "error"},
            },
        ],
        "edges": [
            {
                "edge_id": "edge-start-message",
                "from_node_id": "node-start",
                "from_port_id": "out",
                "to_node_id": "node-message",
                "to_port_id": "in",
                "relation_layer": "control",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_runtime_message_node_is_published_to_runtime_diagnostics() -> None:
    service = CompilationWorkbenchService()
    started = service.start_runtime_session(_build_message_graph())

    assert started["status"] == "started"
    session_id = started["runtime_session"]["session_id"]
    result = service.run_runtime_session(session_id=session_id)

    assert result["status"] == "completed"
    expected_event = {
        "event_kind": "diagnostic.raised",
        "category": "runtime.message",
        "severity": "error",
        "message": "任务已完成",
        "session_id": session_id,
        "node_id": "node-message",
        "node_kind": "message.emit",
    }
    assert any(
        all(event.get(key) == value for key, value in expected_event.items())
        for event in result["event_log"]
    )
    assert any(
        all(event.get(key) == value for key, value in expected_event.items())
        for event in result["diagnostic_events"]
    )
    stream_events = service._runtime_stream_broker.get_events_since(session_id)["events"]
    assert any(
        item["event_name"] == "runtime.diagnostic"
        and all(item["payload"].get(key) == value for key, value in expected_event.items())
        for item in stream_events
    )


def test_debug_message_node_is_published_to_debug_diagnostics() -> None:
    service = CompilationWorkbenchService()

    result = service.start_debug_session(_build_message_graph())

    assert result["status"] == "started"
    assert result["debug_session"]["status"] == "completed"
    assert any(
        event.get("event_kind") == "diagnostic.raised"
        and event.get("category") == "runtime.message"
        and event.get("severity") == "error"
        and event.get("message") == "任务已完成"
        and event.get("node_id") == "node-message"
        for event in result["debug_events"]
    )
    assert any(
        link.get("category") == "runtime.message"
        and link.get("severity") == "error"
        and link.get("message") == "任务已完成"
        and link.get("graph_ref") == {"node_id": "node-message"}
        for link in result["diagnostic_links"]
    )
