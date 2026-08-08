from __future__ import annotations

import argparse
import ast
import json
import re
import runpy
import sys
import tomllib
from copy import deepcopy
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
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")


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
    schema = build_graph_schema(source_root=source_root, version=args.version)

    write_json(output_path, components)
    write_json(schema_output_path, schema)
    return 0


def validate_source_version(source_root: Path, expected_version: str) -> None:
    expected_version = expected_version.strip()
    if not SEMVER_RE.fullmatch(expected_version):
        raise SystemExit(
            f"requested version must be a semantic version X.Y.Z, got {expected_version!r}"
        )

    pyproject_version = read_pyproject_version(source_root / "pyproject.toml")
    package_version = read_package_json_version(source_root / "ui" / "package.json")
    compatibility_versions = read_graph_compatibility_versions(
        source_root / "src" / "weconduct" / "contracts" / "graph.py"
    )

    malformed: list[str] = []
    for anchor_name, actual_version in (
        ("pyproject.toml project.version", pyproject_version),
        ("ui/package.json version", package_version),
        ("graph.py built_with_app_version", compatibility_versions["built_with_app_version"]),
        ("graph.py last_upgraded_by_app_version", compatibility_versions["last_upgraded_by_app_version"]),
    ):
        if not SEMVER_RE.fullmatch(actual_version.strip()):
            malformed.append(f"{anchor_name}={actual_version!r}")

    if malformed:
        raise SystemExit(
            "source version must use semantic version X.Y.Z: " + "; ".join(malformed)
        )


def read_pyproject_version(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    version = payload.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f"missing project.version in {path}")
    return version.strip()


def read_package_json_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f"missing version in {path}")
    return version.strip()


def read_graph_compatibility_versions(path: Path) -> dict[str, str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    constants = read_module_string_constants(path.parent.parent / "_version.py")
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "create_empty_graph_model":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
                continue
            for keyword in statement.value.keywords:
                if keyword.arg != "root_metadata":
                    continue
                root_metadata = evaluate_static_value(keyword.value, constants)
                if not isinstance(root_metadata, dict):
                    continue
                graph_compatibility = root_metadata.get("graph_compatibility", {})
                built_with = graph_compatibility.get("built_with_app_version")
                last_upgraded = graph_compatibility.get("last_upgraded_by_app_version")
                if (
                    isinstance(built_with, str)
                    and built_with.strip()
                    and isinstance(last_upgraded, str)
                    and last_upgraded.strip()
                ):
                    return {
                        "built_with_app_version": built_with.strip(),
                        "last_upgraded_by_app_version": last_upgraded.strip(),
                    }
    raise SystemExit("failed to read graph compatibility versions from create_empty_graph_model")


def read_module_string_constants(path: Path) -> dict[str, str]:
    """Read simple string constants used by generated graph metadata."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    constants: dict[str, str] = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            constants[targets[0].id] = value.value
    return constants


def evaluate_static_value(node: ast.AST, constants: dict[str, str]) -> Any:
    """Evaluate the literal mapping while allowing imported string constants."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    if isinstance(node, ast.Dict):
        return {
            evaluate_static_value(key, constants): evaluate_static_value(value, constants)
            for key, value in zip(node.keys, node.values)
            if key is not None
        }
    if isinstance(node, ast.List):
        return [evaluate_static_value(item, constants) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(evaluate_static_value(item, constants) for item in node.elts)
    if isinstance(node, ast.Set):
        return {evaluate_static_value(item, constants) for item in node.elts}
    raise ValueError(f"unsupported static graph metadata expression: {ast.dump(node)}")


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


def build_graph_schema(*, source_root: Path, version: str) -> dict[str, Any]:
    schema = load_graph_contract_schema(source_root)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["description"] = (
        f"WeConduct {version} graph-v1 schema derived from src/weconduct/contracts/graph.py."
    )
    schema["properties"]["graph_schema_version"] = {"const": "graph-v1"}
    return schema


def load_graph_contract_schema(source_root: Path) -> dict[str, Any]:
    original_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(source_root / "src"))
        from weconduct.contracts.graph import GraphModel

        return deepcopy(GraphModel.model_json_schema())
    finally:
        sys.path[:] = original_sys_path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
