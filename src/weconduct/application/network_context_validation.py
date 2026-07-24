from __future__ import annotations

from dataclasses import dataclass

from weconduct.contracts import GraphModel


@dataclass(frozen=True)
class NetworkContextJoinAmbiguity:
    join_node_id: str
    context_labels: tuple[str, ...]
    successor_node_ids: tuple[str, ...]


def collect_network_context_join_ambiguities(
    graph_model: GraphModel,
) -> list[NetworkContextJoinAmbiguity]:
    """Find joins whose incoming control paths select different network contexts."""

    node_by_id = {node.node_id: node for node in graph_model.nodes}
    control_edges = [edge for edge in graph_model.edges if edge.relation_layer == "control"]
    incoming_edges_by_node_id: dict[str, list] = {node_id: [] for node_id in node_by_id}
    outgoing_edges_by_node_id: dict[str, list] = {node_id: [] for node_id in node_by_id}
    for edge in control_edges:
        if edge.from_node_id not in node_by_id or edge.to_node_id not in node_by_id:
            continue
        outgoing_edges_by_node_id[edge.from_node_id].append(edge)
        incoming_edges_by_node_id[edge.to_node_id].append(edge)

    labels_by_node_id: dict[str, set[str]] = {
        node_id: {"root"}
        for node_id in node_by_id
        if not incoming_edges_by_node_id[node_id]
    }
    changed = True
    while changed:
        changed = False
        for node_id, source_labels in tuple(labels_by_node_id.items()):
            node = node_by_id[node_id]
            output_labels = {
                _apply_context_strategy_label(node.node_id, node.node_kind, node.node_config, label)
                for label in source_labels
            }
            for edge in outgoing_edges_by_node_id[node_id]:
                target_labels = labels_by_node_id.setdefault(edge.to_node_id, set())
                before_count = len(target_labels)
                target_labels.update(output_labels)
                changed = changed or len(target_labels) != before_count

    ambiguities: list[NetworkContextJoinAmbiguity] = []
    for node in graph_model.nodes:
        if node.node_kind != "control.join":
            continue
        incoming_edges = incoming_edges_by_node_id[node.node_id]
        if len(incoming_edges) < 2:
            continue
        incoming_labels: set[str] = set()
        for edge in incoming_edges:
            source = node_by_id[edge.from_node_id]
            incoming_labels.update(
                _apply_context_strategy_label(
                    source.node_id,
                    source.node_kind,
                    source.node_config,
                    label,
                )
                for label in labels_by_node_id.get(source.node_id, {"root"})
            )
        if len(incoming_labels) < 2:
            continue
        successor_node_ids = tuple(
            sorted({edge.to_node_id for edge in outgoing_edges_by_node_id[node.node_id]})
        )
        if successor_node_ids and all(
            _has_explicit_context_selection(
                graph_model=graph_model,
                node_id=successor_node_id,
            )
            for successor_node_id in successor_node_ids
        ):
            continue
        ambiguities.append(
            NetworkContextJoinAmbiguity(
                join_node_id=node.node_id,
                context_labels=tuple(sorted(incoming_labels)),
                successor_node_ids=successor_node_ids,
            )
        )
    return ambiguities


def _apply_context_strategy_label(
    node_id: str,
    node_kind: str | None,
    node_config: dict[str, object],
    current_label: str,
) -> str:
    if not isinstance(node_kind, str) or not node_kind.startswith("network."):
        return current_label
    strategy = node_config.get("context_strategy") if isinstance(node_config, dict) else None
    if not isinstance(strategy, str):
        return current_label
    normalized_strategy = strategy.strip().lower()
    if normalized_strategy in {"new", "anonymous", "fork"}:
        return f"{normalized_strategy}:{node_id}"
    if normalized_strategy == "switch":
        switch_context_id = node_config.get("switch_context_id")
        if isinstance(switch_context_id, str) and switch_context_id.strip():
            return f"switch:{switch_context_id.strip()}"
        return f"switch:{node_id}"
    return current_label


def _has_explicit_context_selection(*, graph_model: GraphModel, node_id: str) -> bool:
    node = next((item for item in graph_model.nodes if item.node_id == node_id), None)
    if node is None:
        return False
    strategy = node.node_config.get("context_strategy")
    if isinstance(strategy, str) and strategy.strip().lower() == "switch":
        return True
    context_port_ids = {
        port.port_id
        for port in node.ports
        if port.direction == "input"
        and "context" in f"{port.port_id} {port.semantic_slot}".lower()
    }
    if not context_port_ids:
        return False
    return any(
        edge.relation_layer == "data"
        and edge.to_node_id == node_id
        and edge.to_port_id in context_port_ids
        for edge in graph_model.edges
    )
