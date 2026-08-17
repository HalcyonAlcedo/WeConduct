from __future__ import annotations

import pytest

from weconduct.application import CompilationWorkbenchService


def _workspace_graph() -> dict:
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
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    }
                ],
                "node_config": {"initial_variables": {}},
            },
            {
                "node_id": "node-target",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-target",
                "expansion_role": "browser.click",
                "display_name": "验证码提交",
                "node_kind": "browser.click",
                "position": {"x": 160, "y": 0},
                "ports": [
                    {
                        "port_id": "control-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "control.previous",
                    },
                    {
                        "port_id": "control-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "control.next",
                    },
                ],
                "node_config": {"selector": "#submit"},
            },
        ],
        "edges": [
            {
                "edge_id": "start-to-target",
                "relation_layer": "control",
                "from_node_id": "node-start",
                "from_port_id": "control-out",
                "to_node_id": "node-target",
                "to_port_id": "control-in",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_graph_context_returns_only_focus_neighborhood_with_port_semantics() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_workspace_graph())

    context = service.get_graph_context(
        node_id="node-target",
        depth=1,
        include_config=True,
        include_ports=True,
        max_nodes=10,
        max_edges=10,
    )

    assert context["revision"] == 1
    assert context["focus_node"]["node_id"] == "node-target"
    assert context["focus_node"]["node_config"] == {"selector": "#submit"}
    assert [node["node_id"] for node in context["neighbors"]] == ["node-start"]
    assert context["incoming_edges"] == [
        {
            "edge_id": "start-to-target",
            "relation_layer": "control",
            "from_node_id": "node-start",
            "to_node_id": "node-target",
            "from_port_id": "control-out",
            "to_port_id": "control-in",
            "edge_state": None,
            "from_port": {
                "port_id": "control-out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "control.next",
                "display_name": None,
                "max_connections": None,
            },
            "to_port": {
                "port_id": "control-in",
                "direction": "input",
                "relation_layer": "control",
                "semantic_slot": "control.previous",
                "display_name": None,
                "max_connections": None,
            },
        }
    ]


def test_graph_patch_preview_does_not_save_and_apply_commits_one_revision() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_workspace_graph())

    patch = [{"op": "node.update", "node_id": "node-target", "changes": {"display_name": "已优化提交"}}]
    preview = service.preview_graph_patch(expected_revision=1, operations=patch)

    assert preview["status"] == "preview"
    assert preview["base_revision"] == 1
    assert service.get_graph_document()["revision"] == 1
    assert service.get_graph_context(node_id="node-target")["focus_node"]["display_name"] == "验证码提交"

    applied = service.apply_graph_patch(expected_revision=1, operations=patch)

    assert applied["status"] == "applied"
    assert applied["new_revision"] == 2
    assert service.get_graph_document()["revision"] == 2
    assert service.get_graph_context(node_id="node-target")["focus_node"]["display_name"] == "已优化提交"


def test_graph_patch_rejects_invalid_edge_without_persisting_any_operation() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_workspace_graph())

    with pytest.raises(ValueError, match="graph patch validation failed"):
        service.apply_graph_patch(
            expected_revision=1,
            operations=[
                {"op": "node.update", "node_id": "node-target", "changes": {"display_name": "不得保存"}},
                {
                    "op": "edge.add",
                    "edge": {
                        "edge_id": "invalid-edge",
                        "relation_layer": "control",
                        "from_node_id": "node-start",
                        "from_port_id": "missing-port",
                        "to_node_id": "node-target",
                        "to_port_id": "control-in",
                    },
                },
            ],
        )

    assert service.get_graph_document()["revision"] == 1
    assert service.get_graph_context(node_id="node-target")["focus_node"]["display_name"] == "验证码提交"


def test_component_catalogue_filters_and_bounds_the_result_set() -> None:
    service = CompilationWorkbenchService()

    catalogue = service.get_component_library_document(query="while", limit=1)

    assert catalogue["total_matched_count"] >= 1
    assert catalogue["summary"]["available_resource_count"] == 1
    assert catalogue["truncated"] == (catalogue["total_matched_count"] > 1)
    assert catalogue["items"][0]["resource_key"] == "control.while"


def test_graph_patch_adds_a_real_node_draft_and_reconnects_control_edges() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_workspace_graph())

    applied = service.apply_graph_patch(
        expected_revision=1,
        operations=[
            {"op": "edge.remove", "edge_id": "start-to-target"},
            {
                "op": "node.add",
                "resource_key": "data.set_variable",
                "node_id": "retry-counter-init",
                "position": {"x": 80, "y": 120},
                "config_changes": {"name": "attempt_count", "value": 0},
            },
            {
                "op": "edge.add",
                "edge": {
                    "edge_id": "start-to-counter",
                    "relation_layer": "control",
                    "from_node_id": "node-start",
                    "from_port_id": "control-out",
                    "to_node_id": "retry-counter-init",
                    "to_port_id": "in",
                },
            },
            {
                "op": "edge.add",
                "edge": {
                    "edge_id": "counter-to-target",
                    "relation_layer": "control",
                    "from_node_id": "retry-counter-init",
                    "from_port_id": "out",
                    "to_node_id": "node-target",
                    "to_port_id": "control-in",
                },
            },
        ],
    )

    assert applied["new_revision"] == 2
    graph = service.get_graph_document()["graph_model"]
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["retry-counter-init"].node_kind == "data.set_variable"
    assert nodes["retry-counter-init"].node_config == {"name": "attempt_count", "value": 0}
    assert {edge.edge_id for edge in graph.edges} == {"start-to-counter", "counter-to-target"}


def test_graph_patch_removes_edges_then_node_without_requiring_full_graph_payload() -> None:
    service = CompilationWorkbenchService()
    service.save_graph_document(_workspace_graph())

    applied = service.apply_graph_patch(
        expected_revision=1,
        operations=[
            {"op": "edge.remove", "edge_id": "start-to-target"},
            {"op": "node.remove", "node_id": "node-target"},
        ],
    )

    assert applied["new_revision"] == 2
    graph = service.get_graph_document()["graph_model"]
    assert [node.node_id for node in graph.nodes] == ["node-start"]
    assert graph.edges == []
