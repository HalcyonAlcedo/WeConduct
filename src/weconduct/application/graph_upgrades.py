from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


GRAPH_COMPATIBILITY_BASELINE_VERSION = "0.5.2"
CURRENT_GRAPH_DATA_VERSION = "0.9.0"
NETWORK_RESPONSE_MEMORY_THRESHOLD_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class GraphDataUpgrader:
    from_version: str
    to_version: str
    upgrader_id: str
    transform: Callable[[dict[str, Any]], dict[str, Any]]


def upgrade_graph_payload(
    payload: dict[str, Any],
    *,
    from_version: str,
    target_version: str = CURRENT_GRAPH_DATA_VERSION,
) -> dict[str, Any]:
    """Apply the complete graph-data upgrade path without changing metadata."""
    current_version = from_version.strip()
    if current_version == target_version:
        return deepcopy(payload)

    upgraded_payload = deepcopy(payload)
    for upgrader in build_graph_upgrade_path(current_version, target_version):
        upgraded_payload = upgrader.transform(upgraded_payload)
        current_version = upgrader.to_version
    if current_version != target_version:
        raise ValueError(
            f"no graph data upgrade path from {from_version!r} to {target_version!r}"
        )
    return upgraded_payload


def build_graph_upgrade_path(
    from_version: str,
    target_version: str = CURRENT_GRAPH_DATA_VERSION,
) -> list[GraphDataUpgrader]:
    current_version = from_version.strip() or GRAPH_COMPATIBILITY_BASELINE_VERSION
    path: list[GraphDataUpgrader] = []
    visited_versions: set[str] = set()
    while current_version != target_version:
        if current_version in visited_versions:
            return []
        visited_versions.add(current_version)
        upgrader = next(
            (item for item in GRAPH_DATA_UPGRADERS if item.from_version == current_version),
            None,
        )
        if upgrader is None:
            return []
        path.append(upgrader)
        current_version = upgrader.to_version
    return path


def _identity_upgrade(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)


def _upgrade_062_to_090(payload: dict[str, Any]) -> dict[str, Any]:
    upgraded_payload = deepcopy(payload)
    raw_nodes = upgraded_payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("graph nodes must be a list before 0.9.0 upgrade")

    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or raw_node.get("node_kind") != "http.request":
            continue
        node_id = raw_node.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("legacy http.request node_id must be a non-empty string")
        raw_node["node_kind"] = "network.http_request"
        node_config = raw_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
            raw_node["node_config"] = node_config
        node_config.setdefault("context_strategy", "inherit")
        node_config.setdefault(
            "response_memory_threshold_bytes",
            NETWORK_RESPONSE_MEMORY_THRESHOLD_BYTES,
        )
        raw_node["ports"] = _add_network_http_ports(
            node_id=node_id,
            raw_ports=raw_node.get("ports"),
        )
    return upgraded_payload


def _add_network_http_ports(*, node_id: str, raw_ports: object) -> list[dict[str, Any]]:
    if raw_ports is None:
        ports: list[dict[str, Any]] = []
    elif isinstance(raw_ports, list) and all(isinstance(port, dict) for port in raw_ports):
        ports = [dict(port) for port in raw_ports]
    else:
        raise ValueError(f"legacy http.request ports are invalid for node {node_id}")

    existing_port_ids = {
        port.get("port_id")
        for port in ports
        if isinstance(port.get("port_id"), str) and port["port_id"].strip()
    }
    specifications = (
        ("in-url", "input", "data", "network.url"),
        ("in-headers", "input", "data", "network.headers"),
        ("in-query", "input", "data", "network.query"),
        ("in-auth", "input", "data", "network.auth"),
        ("in-tls", "input", "data", "network.tls"),
        ("in-proxy", "input", "data", "network.proxy"),
        ("in-timeout", "input", "data", "network.timeout"),
        ("in-network-context", "input", "data", "network.context"),
        ("out-response", "output", "data", "network.response"),
        ("out-network-context", "output", "data", "network.context"),
    )
    for suffix, direction, relation_layer, semantic_slot in specifications:
        port_id = f"{node_id}::network::{suffix}"
        if port_id in existing_port_ids:
            continue
        ports.append(
            {
                "port_id": port_id,
                "direction": direction,
                "relation_layer": relation_layer,
                "semantic_slot": semantic_slot,
            }
        )
    return ports


GRAPH_DATA_UPGRADERS = (
    GraphDataUpgrader(
        from_version=GRAPH_COMPATIBILITY_BASELINE_VERSION,
        to_version="0.6.2",
        upgrader_id="p18d-baseline-052-to-062",
        transform=_identity_upgrade,
    ),
    GraphDataUpgrader(
        from_version="0.6.2",
        to_version=CURRENT_GRAPH_DATA_VERSION,
        upgrader_id="p090-http-request-to-network-http-request",
        transform=_upgrade_062_to_090,
    ),
)
