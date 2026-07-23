from __future__ import annotations

from weconduct.application import CompilationWorkbenchService
from weconduct.application.graph_upgrades import upgrade_graph_payload
from weconduct.contracts import GraphModel
import pytest


def test_upgrade_062_http_request_to_090_network_node_without_rewriting_ids() -> None:
    payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-http",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-http",
                "expansion_role": "action:request",
                "node_kind": "http.request",
                "ports": [
                    {
                        "port_id": "out-main",
                        "direction": "output",
                        "relation_layer": "data",
                        "semantic_slot": "out.result",
                    }
                ],
                "node_config": {"method": "GET", "url": "https://example.test"},
            }
        ],
        "edges": [
            {
                "edge_id": "edge-http-result",
                "relation_layer": "data",
                "from_node_id": "node-http",
                "to_node_id": "node-next",
                "from_port_id": "out-main",
                "to_port_id": "in-main",
            }
        ],
        "root_metadata": {
            "graph_compatibility": {
                "graph_data_version": "0.6.2",
                "built_with_app_version": "0.8.2",
                "minimum_loader_app_version": "0.5.2",
                "last_upgraded_by_app_version": "0.8.2",
                "upgrade_history": [],
            }
        },
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.6.2", target_version="0.9.0")

    node = upgraded["nodes"][0]
    assert node["node_id"] == "node-http"
    assert node["node_kind"] == "network.http_request"
    assert node["node_config"]["context_strategy"] == "inherit"
    assert node["node_config"]["response_memory_threshold_bytes"] == 4 * 1024 * 1024
    assert {port["port_id"] for port in node["ports"]} >= {
        "out-main",
        "node-http::network::in-url",
        "node-http::network::in-network-context",
        "node-http::network::out-response",
    }
    assert upgraded["edges"][0]["edge_id"] == "edge-http-result"
    assert upgraded["edges"][0]["from_port_id"] == "out-main"


def test_upgrade_090_payload_is_idempotent() -> None:
    payload = {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [],
        "edges": [],
        "root_metadata": {},
    }

    assert upgrade_graph_payload(payload, from_version="0.9.0", target_version="0.9.0") == payload


def test_workbench_exposes_062_to_090_upgrade_path() -> None:
    service = CompilationWorkbenchService()

    assert service._build_graph_upgrade_path("0.6.2") == [
        {
            "from_version": "0.6.2",
            "to_version": "0.9.0",
            "upgrader_id": "p090-http-request-to-network-http-request",
        }
    ]


def test_workbench_upgrade_applies_payload_transform_before_version_metadata() -> None:
    service = CompilationWorkbenchService()
    graph = GraphModel.model_validate(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-http",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-http",
                    "expansion_role": "action:request",
                    "node_kind": "http.request",
                    "ports": [],
                    "node_config": {},
                }
            ],
            "edges": [],
            "root_metadata": {
                "graph_compatibility": {
                    "graph_data_version": "0.6.2",
                    "built_with_app_version": "0.8.2",
                    "minimum_loader_app_version": "0.5.2",
                    "last_upgraded_by_app_version": "0.8.2",
                    "upgrade_history": [],
                }
            },
        }
    )

    upgraded = service._upgrade_graph_model_to_current_data_version(graph)

    assert upgraded.nodes[0].node_kind == "network.http_request"
    assert upgraded.root_metadata["graph_compatibility"]["graph_data_version"] == "0.9.0"
    assert upgraded.root_metadata["graph_compatibility"]["upgrade_history"][-1][
        "upgrader_id"
    ] == "p090-http-request-to-network-http-request"


def test_workbench_rejects_legacy_force_load_bypass() -> None:
    service = CompilationWorkbenchService()

    with pytest.raises(ValueError, match="upgrade_and_load"):
        service.apply_pending_graph_upgrade(decision="force_load")
