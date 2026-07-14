from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPHS_ROOT = ROOT / "docs" / "assets" / "graphs"
DEFAULT_COMPONENTS_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
SUPPORTED_EDGE_LAYERS = {"control", "data"}
SUPPORTED_GRAPH_SCHEMA_VERSION = "graph-v1"
SUPPORTED_BUILT_WITH_VERSION = "0.8.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphs-root", default=str(DEFAULT_GRAPHS_ROOT))
    parser.add_argument("--components", default=str(DEFAULT_COMPONENTS_PATH))
    parser.add_argument("--family")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graphs_root = Path(args.graphs_root).resolve()
    components_path = Path(args.components).resolve()
    families = parse_family_selectors(args.family)

    manifest = load_manifest(components_path)
    graph_paths = collect_graph_paths(graphs_root, families)
    errors: list[str] = []

    for graph_path in graph_paths:
        relative_path = describe_graph_path(graph_path, graphs_root)
        try:
            payload = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{relative_path}: invalid JSON at line {exc.lineno} column {exc.colno}")
            continue
        graph_errors = validate_graph_payload(payload, manifest=manifest, relative_path=relative_path)
        if graph_errors:
            errors.extend(graph_errors)
        else:
            print(f"OK {relative_path}")

    for message in errors:
        print(f"ERROR {message}", file=sys.stderr)

    print(f"files={len(graph_paths)} errors={len(errors)}")
    return 1 if errors else 0


def parse_family_selectors(raw_value: str | None) -> set[str]:
    if raw_value is None or not raw_value.strip():
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def load_manifest(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"components manifest must be a list: {path}")

    manifest: dict[str, dict[str, dict[str, str]]] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise SystemExit(f"components manifest contains non-object entry: {path}")
        resource_key = item.get("resource_key")
        ports = item.get("ports")
        if not isinstance(resource_key, str) or not resource_key.strip():
            raise SystemExit(f"components manifest contains invalid resource_key: {path}")
        if not isinstance(ports, list):
            raise SystemExit(f"components manifest entry {resource_key!r} missing ports list")
        manifest[resource_key] = {}
        for port in ports:
            if not isinstance(port, dict):
                raise SystemExit(f"components manifest entry {resource_key!r} has non-object port")
            port_id = port.get("port_id")
            direction = port.get("direction")
            relation_layer = port.get("relation_layer")
            if not all(isinstance(value, str) and value.strip() for value in (port_id, direction, relation_layer)):
                raise SystemExit(f"components manifest entry {resource_key!r} has invalid port contract")
            manifest[resource_key][port_id] = {
                "direction": direction,
                "relation_layer": relation_layer,
            }
    return manifest


def collect_graph_paths(graphs_root: Path, families: set[str]) -> list[Path]:
    if not graphs_root.is_dir():
        raise SystemExit(f"graphs root does not exist: {graphs_root}")

    graph_paths = sorted(graphs_root.rglob("*.json"))
    if not families:
        return graph_paths

    filtered = []
    for path in graph_paths:
        relative_parts = path.relative_to(graphs_root).parts
        family = relative_parts[0] if relative_parts else ""
        if family in families:
            filtered.append(path)
    if not filtered:
        raise SystemExit(
            f"no graph fixtures matched --family {', '.join(sorted(families))} under {graphs_root}"
        )
    return filtered


def describe_graph_path(graph_path: Path, graphs_root: Path) -> str:
    try:
        return graph_path.relative_to(ROOT).as_posix()
    except ValueError:
        return graph_path.relative_to(graphs_root).as_posix()


def validate_graph_payload(
    payload: Any,
    *,
    manifest: dict[str, dict[str, dict[str, str]]],
    relative_path: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{relative_path}: root must be an object"]

    require_string_field(payload, "graph_model_id", relative_path, errors)
    if payload.get("compilation_id") is not None and not isinstance(payload.get("compilation_id"), str):
        errors.append(f"{relative_path}: compilation_id must be string or null")

    graph_schema_version = payload.get("graph_schema_version")
    if graph_schema_version != SUPPORTED_GRAPH_SCHEMA_VERSION:
        errors.append(
            f"{relative_path}: graph_schema_version expected {SUPPORTED_GRAPH_SCHEMA_VERSION!r} got {graph_schema_version!r}"
        )

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    root_metadata = payload.get("root_metadata")
    if not isinstance(nodes, list):
        errors.append(f"{relative_path}: nodes must be a list")
        nodes = []
    elif len(nodes) == 0:
        errors.append(f"{relative_path}: nodes must contain at least one node")
    if not isinstance(edges, list):
        errors.append(f"{relative_path}: edges must be a list")
        edges = []
    if not isinstance(root_metadata, dict):
        errors.append(f"{relative_path}: root_metadata must be an object")
        root_metadata = {}

    compatibility = root_metadata.get("graph_compatibility")
    if not isinstance(compatibility, dict):
        errors.append(f"{relative_path}: root_metadata.graph_compatibility must be an object")
        compatibility = {}
    built_with = compatibility.get("built_with_app_version")
    if built_with != SUPPORTED_BUILT_WITH_VERSION:
        errors.append(
            f"{relative_path}: root_metadata.graph_compatibility.built_with_app_version expected {SUPPORTED_BUILT_WITH_VERSION!r} got {built_with!r}"
        )

    node_lookup: dict[str, dict[str, Any]] = {}
    ports_by_node_id: dict[str, dict[str, dict[str, str]]] = {}
    duplicate_node_ids: set[str] = set()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"{relative_path}: nodes[{index}] must be an object")
            continue
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"{relative_path}: nodes[{index}].node_id must be a non-empty string")
            continue
        if node_id in node_lookup:
            duplicate_node_ids.add(node_id)
        node_lookup[node_id] = node

        node_kind = node.get("node_kind")
        if not isinstance(node_kind, str) or not node_kind.strip():
            errors.append(f"{relative_path}: nodes[{index}].node_kind must be a non-empty string")
            continue
        if node_kind not in manifest:
            errors.append(
                f"{relative_path}: nodes[{index}].node_kind unknown node_kind {node_kind!r}"
            )
            continue

        validate_position(node, relative_path, index, errors)
        ports = node.get("ports")
        if not isinstance(ports, list):
            errors.append(f"{relative_path}: nodes[{index}].ports must be a list")
            continue

        manifest_ports = manifest[node_kind]
        actual_ports: dict[str, dict[str, str]] = {}
        for port_index, port in enumerate(ports):
            if not isinstance(port, dict):
                errors.append(f"{relative_path}: nodes[{index}].ports[{port_index}] must be an object")
                continue
            port_id = port.get("port_id")
            direction = port.get("direction")
            relation_layer = port.get("relation_layer")
            if not isinstance(port_id, str) or not port_id.strip():
                errors.append(
                    f"{relative_path}: nodes[{index}].ports[{port_index}].port_id must be a non-empty string"
                )
                continue
            actual_ports[port_id] = {
                "direction": direction,
                "relation_layer": relation_layer,
            }
            manifest_contract = manifest_ports.get(port_id)
            if manifest_contract is None:
                errors.append(
                    f"{relative_path}: nodes[{index}].ports[{port_index}].port_id {port_id!r} is not declared by manifest for {node_kind!r}"
                )
                continue
            if direction != manifest_contract["direction"]:
                errors.append(
                    f"{relative_path}: nodes[{index}].ports[{port_index}].direction expected {manifest_contract['direction']!r} got {direction!r}"
                )
            if relation_layer != manifest_contract["relation_layer"]:
                errors.append(
                    f"{relative_path}: nodes[{index}].ports[{port_index}].relation_layer expected {manifest_contract['relation_layer']!r} got {relation_layer!r}"
                )
        if set(actual_ports) != set(manifest_ports):
            errors.append(
                f"{relative_path}: nodes[{index}].ports manifest mismatch for {node_kind!r}; expected {sorted(manifest_ports)} got {sorted(actual_ports)}"
            )
        ports_by_node_id[node_id] = actual_ports

    for duplicate_node_id in sorted(duplicate_node_ids):
        errors.append(f"{relative_path}: duplicate node_id {duplicate_node_id!r} in nodes[1].node_id")

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"{relative_path}: edges[{index}] must be an object")
            continue
        relation_layer = edge.get("relation_layer")
        if relation_layer not in SUPPORTED_EDGE_LAYERS:
            errors.append(
                f"{relative_path}: edges[{index}].relation_layer expected one of {sorted(SUPPORTED_EDGE_LAYERS)} got {relation_layer!r}"
            )
            continue

        from_node_id = edge.get("from_node_id")
        to_node_id = edge.get("to_node_id")
        from_port_id = edge.get("from_port_id")
        to_port_id = edge.get("to_port_id")

        if from_node_id not in node_lookup:
            errors.append(
                f"{relative_path}: edges[{index}].from_node_id references missing node {from_node_id!r}"
            )
            continue
        if to_node_id not in node_lookup:
            errors.append(
                f"{relative_path}: edges[{index}].to_node_id references missing node {to_node_id!r}"
            )
            continue

        source_ports = ports_by_node_id.get(from_node_id, {})
        target_ports = ports_by_node_id.get(to_node_id, {})
        source_contract = source_ports.get(from_port_id)
        target_contract = target_ports.get(to_port_id)
        if source_contract is None:
            errors.append(
                f"{relative_path}: edges[{index}].from_port_id references missing port {from_port_id!r} on node {from_node_id!r}"
            )
            continue
        if target_contract is None:
            errors.append(
                f"{relative_path}: edges[{index}].to_port_id references missing port {to_port_id!r} on node {to_node_id!r}"
            )
            continue
        if source_contract["relation_layer"] != relation_layer:
            errors.append(
                f"{relative_path}: edges[{index}].from_port_id layer mismatch expected {relation_layer!r} got {source_contract['relation_layer']!r}"
            )
        if target_contract["relation_layer"] != relation_layer:
            errors.append(
                f"{relative_path}: edges[{index}].to_port_id layer mismatch expected {relation_layer!r} got {target_contract['relation_layer']!r}"
            )

    return errors


def validate_position(
    node: dict[str, Any],
    relative_path: str,
    index: int,
    errors: list[str],
) -> None:
    position = node.get("position")
    if not isinstance(position, dict):
        errors.append(f"{relative_path}: nodes[{index}].position must be an object")
        return
    for axis in ("x", "y"):
        value = position.get(axis)
        if not isinstance(value, (int, float)):
            errors.append(f"{relative_path}: nodes[{index}].position.{axis} must be numeric")


def require_string_field(
    payload: dict[str, Any],
    field_name: str,
    relative_path: str,
    errors: list[str],
) -> None:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{relative_path}: {field_name} must be a non-empty string")


if __name__ == "__main__":
    raise SystemExit(main())
