from __future__ import annotations

import argparse
import ast
import json
import re
import runpy
from pathlib import Path
from typing import Any


COMPATIBILITY_ONLY_KEYS = {
    "control.jump_to_step",
    "control.end_foreach",
    "control.foreach_continue",
    "control.foreach_break",
    "graph.call_subgraph",
    "call_blueprint",
}

PARAM_TEMPLATE_LINE_RE = re.compile(
    r"^\s*'(?P<resource_key>[^']+)':\s*\[(?P<items>.*)\],\s*$"
)
PARAM_TEMPLATE_ITEM_RE = re.compile(
    r"\{\s*key:\s*'(?P<key>[^']+)'\s*,\s*type:\s*'(?P<type>[^']+)'"
    r"(?:\s*,\s*options:\s*\[(?P<options>[^\]]*)\])?\s*\}"
)
OPTION_RE = re.compile(r"'([^']+)'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--schema-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_path = Path(args.output).resolve()
    schema_output_path = (
        Path(args.schema_output).resolve()
        if args.schema_output
        else output_path.with_name("graph-schema.json")
    )

    validate_source_version(source_root, args.version)
    registry = load_registry(source_root)
    drafts = load_drafts(source_root)
    validate_registry_and_drafts(registry, drafts)
    executor_keys = extract_executor_keys(source_root)
    ui_templates = parse_param_templates(
        source_root / "ui" / "src" / "config" / "fieldTemplates.ts"
    )

    components = build_components(
        registry=registry,
        drafts=drafts,
        executor_keys=executor_keys,
        ui_templates=ui_templates,
    )
    schema = build_graph_schema(version=args.version)

    write_json(output_path, components)
    write_json(schema_output_path, schema)
    return 0


def validate_source_version(source_root: Path, expected_version: str) -> None:
    graph_contract_path = source_root / "src" / "weconduct" / "contracts" / "graph.py"
    module = ast.parse(graph_contract_path.read_text(encoding="utf-8"))
    compatibility_versions: set[str] = set()

    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "create_empty_graph_model":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Return):
                continue
            if not isinstance(statement.value, ast.Call):
                continue
            for keyword in statement.value.keywords:
                if keyword.arg != "root_metadata":
                    continue
                root_metadata = ast.literal_eval(keyword.value)
                graph_compatibility = root_metadata.get("graph_compatibility", {})
                for key in (
                    "built_with_app_version",
                    "minimum_loader_app_version",
                    "last_upgraded_by_app_version",
                ):
                    value = graph_compatibility.get(key)
                    if isinstance(value, str) and value.strip():
                        compatibility_versions.add(value.strip())

    if expected_version not in compatibility_versions:
        raise SystemExit(
            f"source version mismatch: expected {expected_version}, found {sorted(compatibility_versions)!r}"
        )


def load_registry(source_root: Path) -> list[dict[str, Any]]:
    registry_module = runpy.run_path(
        str(source_root / "src" / "weconduct" / "builtin_components" / "registry.py")
    )
    build_registry = registry_module["build_builtin_resource_registry"]
    registry = build_registry()
    if not isinstance(registry, list):
        raise SystemExit("builtin registry loader did not return a list")
    return registry


def load_drafts(source_root: Path) -> dict[str, dict[str, Any]]:
    drafts_module = runpy.run_path(
        str(source_root / "src" / "weconduct" / "builtin_components" / "node_drafts.py")
    )
    drafts = drafts_module["GRAPH_NODE_DRAFT_DEFINITIONS"]
    if not isinstance(drafts, dict):
        raise SystemExit("graph node drafts loader did not return a dict")
    return drafts


def validate_registry_and_drafts(
    registry: list[dict[str, Any]],
    drafts: dict[str, dict[str, Any]],
) -> None:
    registry_keys = [item.get("resource_key") for item in registry]
    if any(not isinstance(key, str) or not key.strip() for key in registry_keys):
        raise SystemExit("registry contains invalid resource_key entries")
    if len(set(registry_keys)) != len(registry_keys):
        duplicates = [key for key in registry_keys if registry_keys.count(key) > 1]
        raise SystemExit(f"duplicate registry keys detected: {sorted(set(duplicates))}")

    draft_keys = list(drafts)
    missing_in_drafts = [key for key in registry_keys if key not in drafts]
    missing_in_registry = [key for key in draft_keys if key not in registry_keys]
    if missing_in_drafts or missing_in_registry:
        details: list[str] = []
        if missing_in_drafts:
            details.append(f"missing_in_drafts={missing_in_drafts}")
        if missing_in_registry:
            details.append(f"missing_in_registry={missing_in_registry}")
        raise SystemExit("registry/draft key mismatch: " + "; ".join(details))


def extract_executor_keys(source_root: Path) -> set[str]:
    engine_path = source_root / "src" / "weconduct" / "runtime" / "engine.py"
    module = ast.parse(engine_path.read_text(encoding="utf-8"))

    for node in module.body:
        if not isinstance(node, ast.ClassDef) or node.name != "RuntimeExecutorRegistry":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
                continue
            for statement in item.body:
                if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Dict):
                    continue
                for target in statement.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        and target.attr == "_executors"
                    ):
                        keys: set[str] = set()
                        for key_node in statement.value.keys:
                            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                                raise SystemExit("executor registry contains non-string key")
                            keys.add(key_node.value)
                        return keys
    raise SystemExit("failed to locate RuntimeExecutorRegistry._executors assignment")


def parse_param_templates(path: Path) -> dict[str, list[dict[str, Any]]]:
    templates: dict[str, list[dict[str, Any]]] = {}
    inside_block = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not inside_block:
            if line.strip() == "export const PARAM_TEMPLATES: Record<string, FieldTemplate[]> = {":
                inside_block = True
            continue
        if line.strip() == "}":
            return templates
        match = PARAM_TEMPLATE_LINE_RE.match(line)
        if not match:
            raise SystemExit(f"failed to parse PARAM_TEMPLATES line: {line}")
        resource_key = match.group("resource_key")
        items_blob = match.group("items")
        templates[resource_key] = parse_param_template_items(resource_key, items_blob)
    raise SystemExit("PARAM_TEMPLATES block was not terminated")


def parse_param_template_items(resource_key: str, items_blob: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    position = 0
    while position < len(items_blob):
        match = PARAM_TEMPLATE_ITEM_RE.match(items_blob, position)
        if not match:
            raise SystemExit(
                f"failed to parse PARAM_TEMPLATES entry for {resource_key}: {items_blob[position:]}"
            )
        options_blob = match.group("options")
        item = {
            "key": match.group("key"),
            "type": match.group("type"),
            "options": OPTION_RE.findall(options_blob) if options_blob else [],
        }
        items.append(item)
        position = match.end()
        if position == len(items_blob):
            break
        if not items_blob.startswith(", ", position):
            raise SystemExit(
                f"failed to parse PARAM_TEMPLATES separators for {resource_key}: {items_blob[position:]}"
            )
        position += 2
    return items


def build_components(
    *,
    registry: list[dict[str, Any]],
    drafts: dict[str, dict[str, Any]],
    executor_keys: set[str],
    ui_templates: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for registry_item in registry:
        resource_key = registry_item["resource_key"]
        draft = drafts[resource_key]
        compatibility_only = resource_key in COMPATIBILITY_ONLY_KEYS
        component = {
            "resource_id": registry_item["resource_id"],
            "resource_key": resource_key,
            "display_name": registry_item["display_name"],
            "display_name_zh": registry_item.get("display_name_i18n", {}).get("zh-CN", ""),
            "description": registry_item["description"],
            "description_zh": registry_item.get("description_i18n", {}).get("zh-CN", ""),
            "capability_domain": registry_item["capability_domain"],
            "resource_type": registry_item["resource_type"],
            "enabled": registry_item["enabled"],
            "origin": registry_item["origin"],
            "implementation_kind": registry_item.get("implementation_kind"),
            "compatibility_aliases": list(registry_item.get("compatibility_aliases", [])),
            "component_library_visible": not compatibility_only,
            "compatibility_only": compatibility_only,
            "direct_runtime_executor": resource_key in executor_keys,
            "lowered_kind": draft["lowered_kind"],
            "expansion_role": draft["expansion_role"],
            "ports": draft.get("ports", []),
            "node_config": draft.get("node_config", {}),
            "parameter_schema": draft.get("parameter_schema", {}),
            "ui_field_templates": ui_templates.get(resource_key, []),
        }
        components.append(component)
    return components


def build_graph_schema(*, version: str) -> dict[str, Any]:
    relation_layer_enum = ["control", "data", "observe"]
    lowered_kind_enum = ["execution", "control", "observe", "bridge"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "WeConduct GraphModel",
        "description": f"WeConduct {version} graph-v1 schema derived from src/weconduct/contracts/graph.py.",
        "type": "object",
        "additionalProperties": False,
        "required": ["graph_model_id", "nodes", "edges"],
        "properties": {
            "graph_model_id": {"type": "string"},
            "compilation_id": {"type": ["string", "null"]},
            "graph_schema_version": {"const": "graph-v1"},
            "nodes": {
                "type": "array",
                "items": {"$ref": "#/$defs/GraphNode"},
            },
            "edges": {
                "type": "array",
                "items": {"$ref": "#/$defs/GraphEdge"},
            },
            "viewport": {
                "anyOf": [{"$ref": "#/$defs/GraphViewport"}, {"type": "null"}],
            },
            "root_metadata": {
                "type": "object",
                "default": {},
                "additionalProperties": True,
            },
            "graph_effective_diagnostic_anchor_refs": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
        },
        "$defs": {
            "GraphPosition": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x", "y"],
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
            },
            "GraphViewport": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x", "y", "zoom"],
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "zoom": {"type": "number"},
                },
            },
            "GraphPort": {
                "type": "object",
                "additionalProperties": False,
                "required": ["port_id", "direction", "relation_layer", "semantic_slot"],
                "properties": {
                    "port_id": {"type": "string"},
                    "direction": {"enum": ["input", "output"]},
                    "relation_layer": {"enum": relation_layer_enum},
                    "semantic_slot": {"type": "string"},
                    "display_name": {"type": ["string", "null"]},
                    "max_connections": {"type": ["integer", "null"]},
                },
            },
            "GraphNode": {
                "type": "object",
                "additionalProperties": False,
                "required": ["node_id", "lowered_kind", "source_anchor_ref", "expansion_role"],
                "properties": {
                    "node_id": {"type": "string"},
                    "lowered_kind": {"enum": lowered_kind_enum},
                    "source_anchor_ref": {"type": "string"},
                    "expansion_role": {"type": "string"},
                    "display_name": {"type": ["string", "null"]},
                    "node_kind": {"type": ["string", "null"]},
                    "position": {
                        "anyOf": [{"$ref": "#/$defs/GraphPosition"}, {"type": "null"}],
                    },
                    "ports": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/GraphPort"},
                        "default": [],
                    },
                    "node_config": {
                        "type": "object",
                        "default": {},
                        "additionalProperties": True,
                    },
                },
            },
            "GraphEdge": {
                "type": "object",
                "additionalProperties": False,
                "required": ["edge_id", "relation_layer", "from_node_id", "to_node_id"],
                "properties": {
                    "edge_id": {"type": "string"},
                    "relation_layer": {"enum": relation_layer_enum},
                    "from_node_id": {"type": "string"},
                    "to_node_id": {"type": "string"},
                    "from_port_id": {"type": ["string", "null"]},
                    "to_port_id": {"type": ["string", "null"]},
                    "edge_state": {"type": ["string", "null"]},
                },
            },
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
