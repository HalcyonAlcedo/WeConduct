from __future__ import annotations

from weconduct.network_runtime.resources import ResponseBodyStore
from weconduct.application import CompilationWorkbenchService
from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_response_assert_validates_status_headers_text_json_duration_and_size(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    context = RuntimeContext(
        variables={
            "last_network_response": {
                "status_code": 201,
                "headers": {"Content-Type": "application/json"},
                "body_ref": store.create(b'{"result":{"id":7}}', content_type="application/json"),
                "duration_ms": 12,
                "final_url": "https://example.test/final",
            }
        }
    )
    node = {
        "node_id": "assert-response",
        "node_kind": "network.response_assert",
        "node_config": {
            "expected_status_codes": [200, 201],
            "required_headers": {"content-type": "application/json"},
            "body_contains": '"id":7',
            "json_path_equals": {"$.result.id": 7},
            "max_duration_ms": 20,
            "max_size_bytes": 1024,
        },
    }

    output = RuntimeExecutorRegistry().execute("network.response_assert", node, context)

    assert output["status"] == "succeeded"
    assert output["passed"] is True
    assert output["failed"] is False
    assert output["assertion_report"] == []


def test_response_assert_returns_structured_failure_report(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    context = RuntimeContext(
        variables={
            "last_network_response": {
                "status_code": 500,
                "headers": {"X-Trace": "actual"},
                "body_ref": store.create(b"unavailable", content_type="text/plain"),
                "duration_ms": 150,
            }
        }
    )
    node = {
        "node_id": "assert-response",
        "node_kind": "network.response_assert",
        "node_config": {
            "expected_status_codes": [200],
            "required_headers": {"x-trace": "expected"},
            "body_contains": "healthy",
            "max_duration_ms": 100,
            "max_size_bytes": 1,
        },
    }

    output = RuntimeExecutorRegistry().execute("network.response_assert", node, context)

    assert output["status"] == "failed"
    assert output["error_code"] == "network.response_assertion_failed"
    assert output["passed"] is False
    assert output["failed"] is True
    assert {item["kind"] for item in output["assertion_report"]} == {
        "status_code",
        "header",
        "body_contains",
        "duration",
        "size",
    }


def test_response_assert_reports_json_schema_validation_failure(tmp_path) -> None:
    store = ResponseBodyStore(session_id="session-1", root_directory=tmp_path)
    context = RuntimeContext(
        variables={
            "last_network_response": {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "body_ref": store.create(b'{"result":{"id":7}}', content_type="application/json"),
                "duration_ms": 12,
            }
        }
    )
    node = {
        "node_id": "assert-response",
        "node_kind": "network.response_assert",
        "node_config": {
            "json_schema": {
                "type": "object",
                "required": ["healthy"],
                "properties": {"healthy": {"type": "boolean"}},
            }
        },
    }

    output = RuntimeExecutorRegistry().execute("network.response_assert", node, context)

    assert output["status"] == "failed"
    assert output["error_code"] == "network.response_assertion_failed"
    assert output["assertion_report"] == [
        {"kind": "json_schema", "path": "$", "message": "'healthy' is a required property"}
    ]


def test_response_assert_failure_routes_only_to_connected_failed_port(
    monkeypatch,
) -> None:
    service = CompilationWorkbenchService()
    graph = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "start",
                "lowered_kind": "control",
                "source_anchor_ref": "start",
                "expansion_role": "flow:start",
                "display_name": "Start",
                "node_kind": "flow.start",
                "position": {"x": 0, "y": 0},
                "ports": [
                    {"port_id": "out", "direction": "output", "relation_layer": "control", "semantic_slot": "out.control"},
                ],
                "node_config": {"initial_variables": {}},
            },
            {
                "node_id": "assertion",
                "lowered_kind": "execution",
                "source_anchor_ref": "assertion",
                "expansion_role": "network:response_assert",
                "display_name": "Assert",
                "node_kind": "network.response_assert",
                "position": {"x": 100, "y": 0},
                "ports": [
                    {"port_id": "in", "direction": "input", "relation_layer": "control", "semantic_slot": "in.control"},
                    {"port_id": "passed", "direction": "output", "relation_layer": "control", "semantic_slot": "out.passed"},
                    {"port_id": "failed", "direction": "output", "relation_layer": "control", "semantic_slot": "out.failed"},
                ],
                "node_config": {},
            },
            {
                "node_id": "passed-target",
                "lowered_kind": "execution",
                "source_anchor_ref": "passed-target",
                "expansion_role": "action:navigate",
                "display_name": "Passed",
                "node_kind": "browser.navigate",
                "position": {"x": 200, "y": -50},
                "ports": [{"port_id": "in", "direction": "input", "relation_layer": "control", "semantic_slot": "in.control"}],
                "node_config": {"url": "https://example.test/passed"},
            },
            {
                "node_id": "failed-target",
                "lowered_kind": "execution",
                "source_anchor_ref": "failed-target",
                "expansion_role": "action:navigate",
                "display_name": "Failed",
                "node_kind": "browser.navigate",
                "position": {"x": 200, "y": 50},
                "ports": [{"port_id": "in", "direction": "input", "relation_layer": "control", "semantic_slot": "in.control"}],
                "node_config": {"url": "https://example.test/failed"},
            },
        ],
        "edges": [
            {"edge_id": "start-to-assertion", "relation_layer": "control", "from_node_id": "start", "to_node_id": "assertion", "from_port_id": "out", "to_port_id": "in", "edge_state": "draft"},
            {"edge_id": "assertion-to-passed", "relation_layer": "control", "from_node_id": "assertion", "to_node_id": "passed-target", "from_port_id": "passed", "to_port_id": "in", "edge_state": "draft"},
            {"edge_id": "assertion-to-failed", "relation_layer": "control", "from_node_id": "assertion", "to_node_id": "failed-target", "from_port_id": "failed", "to_port_id": "in", "edge_state": "draft"},
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }
    executed_node_ids: list[str] = []

    def execute_node(*, executable_node, **_kwargs):
        node_id = executable_node["node_id"]
        executed_node_ids.append(node_id)
        if node_id == "assertion":
            return {
                "status": "failed",
                "node_id": node_id,
                "error_code": "network.response_assertion_failed",
                "message": "assertion failed",
                "port_id": "failed",
            }
        return {"status": "succeeded", "node_id": node_id}

    monkeypatch.setattr(service, "_execute_runtime_plan_node", execute_node)
    session_id = service.start_runtime_session(graph_document_payload=graph)["runtime_session"]["session_id"]

    result = service.run_runtime_session(session_id=session_id)

    assert result["status"] == "completed"
    assert executed_node_ids == ["start", "assertion", "failed-target"]
