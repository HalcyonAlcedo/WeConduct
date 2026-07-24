from __future__ import annotations

from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.application.network_context_validation import (
    collect_network_context_join_ambiguities,
)
from weconduct.contracts.graph import GraphEdge, GraphModel, GraphNode, GraphPort


def test_join_with_divergent_context_strategies_requires_explicit_selection() -> None:
    graph = _build_divergent_context_join_graph(successor_strategy="inherit")

    ambiguities = collect_network_context_join_ambiguities(graph)
    diagnostics = CompilationWorkbenchService()._collect_graph_validation_diagnostics(graph)

    assert len(ambiguities) == 1
    assert ambiguities[0].join_node_id == "join"
    assert ambiguities[0].context_labels == ("fork:branch-a", "root")
    assert [item["category"] for item in diagnostics].count(
        "network.context_join_ambiguous"
    ) == 1


def test_join_with_explicit_switch_successor_is_not_ambiguous() -> None:
    graph = _build_divergent_context_join_graph(successor_strategy="switch")

    ambiguities = collect_network_context_join_ambiguities(graph)

    assert ambiguities == []


def _build_divergent_context_join_graph(*, successor_strategy: str) -> GraphModel:
    return GraphModel(
        graph_model_id="graph:test-network-context-join",
        compilation_id=None,
        nodes=[
            _network_node("branch-a", strategy="fork"),
            _network_node("branch-b", strategy="inherit"),
            GraphNode(
                node_id="join",
                lowered_kind="control",
                source_anchor_ref="join",
                expansion_role="control:join",
                node_kind="control.join",
                ports=[
                    _control_port("in:one", "input", "in.branch:one"),
                    _control_port("in:two", "input", "in.branch:two"),
                    _control_port("out", "output", "out"),
                ],
            ),
            _network_node("after-join", strategy=successor_strategy, has_control_input=True),
        ],
        edges=[
            GraphEdge(
                edge_id="edge-a",
                relation_layer="control",
                from_node_id="branch-a",
                from_port_id="out",
                to_node_id="join",
                to_port_id="in:one",
            ),
            GraphEdge(
                edge_id="edge-b",
                relation_layer="control",
                from_node_id="branch-b",
                from_port_id="out",
                to_node_id="join",
                to_port_id="in:two",
            ),
            GraphEdge(
                edge_id="edge-after",
                relation_layer="control",
                from_node_id="join",
                from_port_id="out",
                to_node_id="after-join",
                to_port_id="in",
            ),
        ],
    )


def _network_node(
    node_id: str,
    *,
    strategy: str,
    has_control_input: bool = False,
) -> GraphNode:
    ports = [_control_port("out", "output", "out")]
    if has_control_input:
        ports.insert(0, _control_port("in", "input", "in"))
    return GraphNode(
        node_id=node_id,
        lowered_kind="execution",
        source_anchor_ref=node_id,
        expansion_role="node",
        node_kind="network.http_request",
        ports=ports,
        node_config={"context_strategy": strategy, "url": "https://example.test"},
    )


def _control_port(port_id: str, direction: str, semantic_slot: str) -> GraphPort:
    return GraphPort(
        port_id=port_id,
        direction=direction,
        relation_layer="control",
        semantic_slot=semantic_slot,
    )
