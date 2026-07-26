from __future__ import annotations

from copy import deepcopy

import weconduct.application.graph_upgrades as graph_upgrades
from weconduct.application import CompilationWorkbenchService
from weconduct.application.graph_upgrades import (
    GraphDataUpgrader,
    requires_current_network_http_contract_repair,
    upgrade_graph_payload,
)
from weconduct.builtin_components import get_graph_node_draft_definition
from weconduct.contracts import GraphModel
import pytest


def test_upgrade_062_http_request_to_090_network_node_uses_formal_ports_and_rewrites_edges() -> None:
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
    assert "response_memory_threshold_bytes" not in node["node_config"]
    assert {port["port_id"] for port in node["ports"]} >= {
        "in",
        "out",
        "in:url",
        "out:response",
        "out:network_context_id",
    }
    assert upgraded["edges"][0]["edge_id"] == "edge-http-result"
    assert upgraded["edges"][0]["from_port_id"] == "out:response"


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


def test_upgrade_090_payload_repairs_legacy_http_contract_when_version_was_already_marked_current() -> None:
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "network.http_request",
                "ports": [
                    {
                        "port_id": "in-url",
                        "direction": "input",
                        "relation_layer": "data",
                        "semantic_slot": "network.url",
                    },
                    {
                        "port_id": "out-main",
                        "direction": "output",
                        "relation_layer": "data",
                        "semantic_slot": "out.result",
                    },
                    {
                        "port_id": "out:body",
                        "direction": "output",
                        "relation_layer": "data",
                        "semantic_slot": "out.body",
                    },
                ],
                "node_config": {},
            }
        ],
        "edges": [
            {
                "edge_id": "edge-url-input",
                "relation_layer": "data",
                "from_node_id": "node-source",
                "to_node_id": "node-http",
                "from_port_id": "out-value",
                "to_port_id": "in-url",
            },
            {
                "edge_id": "edge-response-output",
                "relation_layer": "data",
                "from_node_id": "node-http",
                "to_node_id": "node-target",
                "from_port_id": "out-main",
                "to_port_id": "in-value",
            },
        ],
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.9.0", target_version="0.9.0")

    assert {port["port_id"] for port in upgraded["nodes"][0]["ports"]} >= {
        "in:url",
        "out:response",
        "out:body_ref",
    }
    assert upgraded["edges"][0]["to_port_id"] == "in:url"
    assert upgraded["edges"][1]["from_port_id"] == "out:response"


def test_upgrade_090_payload_does_not_repair_formal_http_ports_with_model_default_null_fields() -> None:
    draft = get_graph_node_draft_definition("network.http_request")
    assert isinstance(draft, dict)
    formal_ports = deepcopy(draft["ports"])
    for port in formal_ports:
        port.setdefault("display_name", None)
        port.setdefault("max_connections", None)
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "network.http_request",
                "lowered_kind": draft["lowered_kind"],
                "expansion_role": draft["expansion_role"],
                "ports": formal_ports,
                "node_config": deepcopy(draft["node_config"]),
            }
        ],
        "edges": [],
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.9.0", target_version="0.9.0")

    assert upgraded == payload


def test_upgrade_062_rewrites_legacy_http_body_references_in_nested_node_config() -> None:
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "http.request",
                "ports": [],
                "node_config": {},
            },
            {
                "node_id": "node-consumer",
                "node_kind": "browser.run_js",
                "ports": [],
                "node_config": {
                    "script": "const files = ${node.node-http.body.files};",
                    "source": "${node.node-http.body}",
                    "nested": {
                        "items": [
                            "${node.node-http.body_text}",
                            "unchanged",
                        ]
                    },
                },
            },
        ],
        "edges": [],
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.6.2", target_version="0.9.0")

    consumer_config = upgraded["nodes"][1]["node_config"]
    assert consumer_config["script"] == (
        "const files = ${node.node-http.body_ref.read_json.files};"
    )
    assert consumer_config["source"] == "${node.node-http.body_ref.read_auto}"
    assert consumer_config["nested"]["items"] == [
        "${node.node-http.body_ref.read_text}",
        "unchanged",
    ]
    assert payload["nodes"][1]["node_config"]["script"] == (
        "const files = ${node.node-http.body.files};"
    )


def test_upgrade_090_rewrites_legacy_http_body_references_after_port_contract_was_repaired() -> None:
    draft = get_graph_node_draft_definition("network.http_request")
    assert isinstance(draft, dict)
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "network.http_request",
                "lowered_kind": draft["lowered_kind"],
                "expansion_role": draft["expansion_role"],
                "ports": deepcopy(draft["ports"]),
                "node_config": deepcopy(draft["node_config"]),
            },
            {
                "node_id": "node-consumer",
                "node_kind": "file.write_text_file",
                "ports": [],
                "node_config": {"content": "${node.node-http.body_text}"},
            },
        ],
        "edges": [],
    }

    assert requires_current_network_http_contract_repair(payload) is True

    upgraded = upgrade_graph_payload(payload, from_version="0.9.0", target_version="0.9.0")

    assert upgraded["nodes"][1]["node_config"]["content"] == (
        "${node.node-http.body_ref.read_text}"
    )
    assert requires_current_network_http_contract_repair(upgraded) is False
    assert (
        upgrade_graph_payload(upgraded, from_version="0.9.0", target_version="0.9.0")
        == upgraded
    )


def test_upgrade_062_http_request_rewrites_legacy_input_edge_port() -> None:
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "http.request",
                "ports": [
                    {
                        "port_id": "in-url",
                        "direction": "input",
                        "relation_layer": "data",
                        "semantic_slot": "network.url",
                    }
                ],
                "node_config": {},
            }
        ],
        "edges": [
            {
                "edge_id": "edge-url-input",
                "relation_layer": "data",
                "from_node_id": "node-source",
                "to_node_id": "node-http",
                "from_port_id": "out-value",
                "to_port_id": "in-url",
            }
        ],
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.6.2", target_version="0.9.0")

    assert upgraded["edges"][0]["to_port_id"] == "in:url"


def test_upgrade_062_http_request_rewrites_known_edge_alias_when_legacy_port_list_is_empty() -> None:
    payload = {
        "nodes": [
            {
                "node_id": "node-http",
                "node_kind": "http.request",
                "ports": [],
                "node_config": {},
            }
        ],
        "edges": [
            {
                "edge_id": "edge-url-input",
                "relation_layer": "data",
                "from_node_id": "node-source",
                "to_node_id": "node-http",
                "from_port_id": "out-value",
                "to_port_id": "in-url",
            }
        ],
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.6.2", target_version="0.9.0")

    assert upgraded["edges"][0]["to_port_id"] == "in:url"


def test_upgrade_graph_payload_validates_every_migration_stage(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_upgrades,
        "GRAPH_DATA_UPGRADERS",
        (
            GraphDataUpgrader(
                from_version="test-start",
                to_version="test-middle",
                upgrader_id="test-invalid-stage",
                transform=lambda payload: {**payload, "stage": "invalid"},
            ),
            GraphDataUpgrader(
                from_version="test-middle",
                to_version="test-end",
                upgrader_id="test-later-stage",
                transform=lambda payload: {**payload, "stage": "valid"},
            ),
        ),
    )

    def validate_stage(payload: dict) -> None:
        if payload.get("stage") == "invalid":
            raise ValueError("invalid intermediate graph payload")

    with pytest.raises(ValueError, match="invalid intermediate graph payload"):
        upgrade_graph_payload(
            {"stage": "source"},
            from_version="test-start",
            target_version="test-end",
            validate_stage=validate_stage,
        )


def test_workbench_exposes_062_to_090_upgrade_path() -> None:
    service = CompilationWorkbenchService()

    assert service._build_graph_upgrade_path("0.6.2") == [
        {
            "from_version": "0.6.2",
            "to_version": "0.9.0",
            "upgrader_id": "p090-network-and-python-run-schema",
        }
    ]


def test_workbench_marks_current_version_graph_with_legacy_http_contract_for_corrective_upgrade() -> None:
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
                    "node_kind": "network.http_request",
                    "ports": [
                        {
                            "port_id": "in-url",
                            "direction": "input",
                            "relation_layer": "data",
                            "semantic_slot": "network.url",
                        }
                    ],
                    "node_config": {},
                }
            ],
            "edges": [],
            "root_metadata": {
                "graph_compatibility": {
                    "graph_data_version": "0.9.0",
                    "built_with_app_version": "0.9.0",
                    "minimum_loader_app_version": "0.5.2",
                    "last_upgraded_by_app_version": "0.9.0",
                    "upgrade_history": [],
                }
            },
        }
    )

    compatibility = service._evaluate_graph_document_compatibility(
        graph_model=graph,
        document_id="graph:workspace",
        document_role="main_graph",
        display_name="Current-version legacy graph",
    )

    assert compatibility["compatibility"]["status"] == "upgrade_available"
    assert compatibility["compatibility"]["available_upgrade_path"] == [
        {
            "from_version": "0.9.0",
            "to_version": "0.9.0",
            "upgrader_id": "p090-corrective-http-contract",
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
    ] == "p090-network-and-python-run-schema"


def test_workbench_rejects_legacy_force_load_bypass() -> None:
    service = CompilationWorkbenchService()

    with pytest.raises(ValueError, match="upgrade_and_load"):
        service.apply_pending_graph_upgrade(decision="force_load")


def test_upgrade_legacy_python_run_adds_dynamic_schema_defaults_without_changing_ports() -> None:
    payload = {
        "nodes": [
            {
                "node_id": "node-python",
                "node_kind": "python.run",
                "ports": [
                    {
                        "port_id": "legacy-in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "legacy-out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {"code": "result = 1"},
            }
        ]
    }

    upgraded = upgrade_graph_payload(payload, from_version="0.6.2", target_version="0.9.0")

    node = upgraded["nodes"][0]
    assert node["node_kind"] == "python.run"
    assert node["node_config"] == {
        "code": "result = 1",
        "inputs": {},
        "input_schema": {},
        "output_schema": {},
        "metadata": {},
        "metadata_schema": {},
        "data_fields": [],
    }
    assert [port["port_id"] for port in node["ports"]] == ["legacy-in", "legacy-out"]
