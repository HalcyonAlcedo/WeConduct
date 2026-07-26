from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from weconduct.builtin_components import get_graph_node_draft_definition


GRAPH_COMPATIBILITY_BASELINE_VERSION = "0.5.2"
CURRENT_GRAPH_DATA_VERSION = "0.9.0"
CORRECTIVE_HTTP_CONTRACT_UPGRADER_ID = "p090-corrective-http-contract"
_LEGACY_HTTP_PORT_ID_ALIASES = {
    "in-url": "in:url",
    "in-headers": "in:headers",
    "in-query": "in:query",
    "in-auth": "in:auth",
    "in-tls": "in:tls",
    "in-proxy": "in:proxy",
    "in-timeout": "in:timeout",
    "in-network-context": "in:context_strategy",
    "out-main": "out:response",
    "out-response": "out:response",
    "out:body": "out:body_ref",
    "out-network-context": "out:network_context",
}
_LEGACY_HTTP_SEMANTIC_SLOT_ALIASES = {
    "network.url": "in.url",
    "network.headers": "in.headers",
    "network.query": "in.query",
    "network.auth": "in.auth",
    "network.tls": "in.tls",
    "network.proxy": "in.proxy",
    "network.timeout": "in.timeout",
    "network.response": "out.response",
    "network.context": "in.context_strategy",
    "out.result": "out.response",
    "out.body": "out.body_ref",
}


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
    validate_stage: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Apply the complete graph-data upgrade path without changing metadata."""
    current_version = from_version.strip()
    if current_version == target_version:
        if (
            target_version == CURRENT_GRAPH_DATA_VERSION
            and requires_current_network_http_contract_repair(payload)
        ):
            return _repair_current_network_http_contract(payload)
        return deepcopy(payload)

    upgraded_payload = deepcopy(payload)
    for upgrader in build_graph_upgrade_path(current_version, target_version):
        upgraded_payload = upgrader.transform(upgraded_payload)
        if validate_stage is not None:
            validate_stage(deepcopy(upgraded_payload))
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

    port_rewrites: dict[tuple[str, str], str] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            continue
        if raw_node.get("node_kind") == "python.run":
            _upgrade_legacy_python_run_node(raw_node)
            continue
        if raw_node.get("node_kind") != "http.request":
            continue
        node_port_rewrites = _normalize_network_http_request_node(raw_node)
        node_id = raw_node["node_id"]
        for source_port_id, target_port_id in node_port_rewrites.items():
            port_rewrites[(node_id, source_port_id)] = target_port_id
    _rewrite_upgraded_http_edges(
        raw_edges=upgraded_payload.get("edges"),
        port_rewrites=port_rewrites,
    )
    return upgraded_payload


def requires_current_network_http_contract_repair(payload: dict[str, Any]) -> bool:
    """Return whether a current-version graph still contains old HTTP ports."""
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        return False
    formal_draft = get_graph_node_draft_definition("network.http_request")
    if not isinstance(formal_draft, dict):
        raise RuntimeError("network.http_request node draft is unavailable")
    formal_ports = formal_draft.get("ports")
    formal_config = formal_draft.get("node_config")
    if not isinstance(formal_ports, list) or not isinstance(formal_config, dict):
        raise RuntimeError("network.http_request formal contract is unavailable")
    formal_port_contract = [_http_port_contract(port) for port in formal_ports]
    if any(contract is None for contract in formal_port_contract):
        raise RuntimeError("network.http_request formal ports are invalid")
    formal_port_ids = {
        port["port_id"]
        for port in formal_ports
        if isinstance(port, dict) and isinstance(port.get("port_id"), str)
    }
    http_node_ids: set[str] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or raw_node.get("node_kind") != "network.http_request":
            continue
        node_id = raw_node.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            return True
        http_node_ids.add(node_id)
        if raw_node.get("lowered_kind") != formal_draft.get("lowered_kind"):
            return True
        if raw_node.get("expansion_role") != formal_draft.get("expansion_role"):
            return True
        raw_config = raw_node.get("node_config")
        if not isinstance(raw_config, Mapping):
            return True
        if "response_memory_threshold_bytes" in raw_config:
            return True
        if any(field_name not in raw_config for field_name in formal_config):
            return True
        raw_ports = raw_node.get("ports")
        if not isinstance(raw_ports, list):
            return True
        if [_http_port_contract(port) for port in raw_ports] != formal_port_contract:
            return True

    raw_edges = payload.get("edges")
    if raw_edges is None:
        return False
    if not isinstance(raw_edges, list):
        return True
    for edge in raw_edges:
        if not isinstance(edge, dict):
            return True
        if (
            edge.get("from_node_id") in http_node_ids
            and edge.get("from_port_id") not in formal_port_ids
        ):
            return True
        if (
            edge.get("to_node_id") in http_node_ids
            and edge.get("to_port_id") not in formal_port_ids
        ):
            return True
    return False


def _http_port_contract(port: object) -> tuple[str, str, str, str] | None:
    if not isinstance(port, Mapping):
        return None
    port_id = port.get("port_id")
    direction = port.get("direction")
    relation_layer = port.get("relation_layer")
    semantic_slot = port.get("semantic_slot")
    if not all(isinstance(value, str) for value in (port_id, direction, relation_layer, semantic_slot)):
        return None
    return port_id, direction, relation_layer, semantic_slot


def _repair_current_network_http_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Repair graphs previously marked 0.9.0 by the pre-contract migration."""
    upgraded_payload = deepcopy(payload)
    raw_nodes = upgraded_payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("graph nodes must be a list before 0.9.0 corrective upgrade")

    port_rewrites: dict[tuple[str, str], str] = {}
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or raw_node.get("node_kind") != "network.http_request":
            continue
        node_port_rewrites = _normalize_network_http_request_node(raw_node)
        node_id = raw_node["node_id"]
        for source_port_id, target_port_id in node_port_rewrites.items():
            port_rewrites[(node_id, source_port_id)] = target_port_id
    _rewrite_upgraded_http_edges(
        raw_edges=upgraded_payload.get("edges"),
        port_rewrites=port_rewrites,
    )
    return upgraded_payload


def _normalize_network_http_request_node(raw_node: dict[str, Any]) -> dict[str, str]:
    node_id = raw_node.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("legacy http.request node_id must be a non-empty string")
    draft = get_graph_node_draft_definition("network.http_request")
    if not isinstance(draft, dict):
        raise RuntimeError("network.http_request node draft is unavailable")
    raw_node["node_kind"] = "network.http_request"
    raw_node["lowered_kind"] = draft["lowered_kind"]
    raw_node["expansion_role"] = draft["expansion_role"]
    node_config = raw_node.get("node_config")
    if not isinstance(node_config, dict):
        node_config = {}
        raw_node["node_config"] = node_config
    draft_config = draft.get("node_config")
    if isinstance(draft_config, dict):
        for field_name, default_value in draft_config.items():
            node_config.setdefault(field_name, deepcopy(default_value))
    node_config.pop("response_memory_threshold_bytes", None)
    ports, port_rewrites = _upgrade_network_http_ports(
        node_id=node_id,
        raw_ports=raw_node.get("ports"),
        formal_ports=draft.get("ports"),
    )
    raw_node["ports"] = ports
    return port_rewrites


def _upgrade_legacy_python_run_node(raw_node: dict[str, Any]) -> None:
    """Give legacy built-in Python nodes the explicit 0.9 dynamic schema shape."""
    node_config = raw_node.get("node_config")
    if not isinstance(node_config, dict):
        node_config = {}
        raw_node["node_config"] = node_config
    node_config.setdefault("inputs", {})
    node_config.setdefault("input_schema", {})
    node_config.setdefault("output_schema", {})
    node_config.setdefault("metadata", {})
    node_config.setdefault("metadata_schema", {})
    node_config.setdefault("data_fields", [])


def _upgrade_network_http_ports(
    *,
    node_id: str,
    raw_ports: object,
    formal_ports: object,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if raw_ports is None:
        ports: list[dict[str, Any]] = []
    elif isinstance(raw_ports, list) and all(isinstance(port, dict) for port in raw_ports):
        ports = [dict(port) for port in raw_ports]
    else:
        raise ValueError(f"legacy http.request ports are invalid for node {node_id}")
    if not isinstance(formal_ports, list) or not all(isinstance(port, dict) for port in formal_ports):
        raise RuntimeError("network.http_request formal ports are unavailable")

    formal_by_id = {
        port["port_id"]: dict(port)
        for port in formal_ports
        if isinstance(port.get("port_id"), str)
    }
    formal_by_semantic_slot = {
        port["semantic_slot"]: port["port_id"]
        for port in formal_ports
        if isinstance(port.get("port_id"), str) and isinstance(port.get("semantic_slot"), str)
    }
    rewrites = {
        source_port_id: target_port_id
        for source_port_id, target_port_id in _LEGACY_HTTP_PORT_ID_ALIASES.items()
        if target_port_id in formal_by_id
    }
    rewrites.update(
        {
            source_semantic_slot: target_port_id
            for source_semantic_slot, target_semantic_slot in _LEGACY_HTTP_SEMANTIC_SLOT_ALIASES.items()
            if (target_port_id := formal_by_semantic_slot.get(target_semantic_slot)) is not None
        }
    )
    for port in ports:
        source_port_id = port.get("port_id")
        if not isinstance(source_port_id, str) or not source_port_id.strip():
            raise ValueError(f"legacy http.request port_id is invalid for node {node_id}")
        target_port_id = _resolve_formal_http_port_id(
            source_port_id=source_port_id,
            semantic_slot=port.get("semantic_slot"),
            formal_by_id=formal_by_id,
            formal_by_semantic_slot=formal_by_semantic_slot,
        )
        if target_port_id is None:
            raise ValueError(
                f"legacy http.request port cannot be mapped to the 0.9.0 contract: "
                f"{node_id}:{source_port_id}"
            )
        rewrites[source_port_id] = target_port_id
    return [dict(port) for port in formal_ports], rewrites


def _resolve_formal_http_port_id(
    *,
    source_port_id: str,
    semantic_slot: object,
    formal_by_id: dict[str, dict[str, Any]],
    formal_by_semantic_slot: dict[str, str],
) -> str | None:
    if source_port_id in formal_by_id:
        return source_port_id
    if isinstance(semantic_slot, str):
        if semantic_slot in formal_by_semantic_slot:
            return formal_by_semantic_slot[semantic_slot]
        alias = _LEGACY_HTTP_SEMANTIC_SLOT_ALIASES.get(semantic_slot)
        if alias is not None:
            return formal_by_semantic_slot.get(alias)
    alias = _LEGACY_HTTP_PORT_ID_ALIASES.get(source_port_id)
    if alias in formal_by_id:
        return alias
    return None


def _rewrite_upgraded_http_edges(
    *,
    raw_edges: object,
    port_rewrites: dict[tuple[str, str], str],
) -> None:
    if raw_edges is None:
        return
    if not isinstance(raw_edges, list) or not all(isinstance(edge, dict) for edge in raw_edges):
        raise ValueError("graph edges must be a list before 0.9.0 upgrade")
    for edge in raw_edges:
        source_node_id = edge.get("from_node_id")
        source_port_id = edge.get("from_port_id")
        if isinstance(source_node_id, str) and isinstance(source_port_id, str):
            edge["from_port_id"] = port_rewrites.get(
                (source_node_id, source_port_id),
                source_port_id,
            )
        target_node_id = edge.get("to_node_id")
        target_port_id = edge.get("to_port_id")
        if isinstance(target_node_id, str) and isinstance(target_port_id, str):
            edge["to_port_id"] = port_rewrites.get(
                (target_node_id, target_port_id),
                target_port_id,
            )


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
        upgrader_id="p090-network-and-python-run-schema",
        transform=_upgrade_062_to_090,
    ),
)
