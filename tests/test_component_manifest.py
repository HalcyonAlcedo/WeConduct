import json
import runpy
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = (ROOT / ".." / "WeConduct").resolve()
SCRIPT_PATH = ROOT / "tools" / "build_component_manifest.py"
OUTPUT_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
SCHEMA_PATH = ROOT / "data" / "weconduct-0.8.1" / "graph-schema.json"

EXPECTED_DOMAIN_COUNTS = {
    "browser": 67,
    "data": 25,
    "control": 12,
    "excel": 9,
    "file": 5,
    "component": 3,
    "flow": 1,
    "graph": 1,
    "http": 1,
    "python": 1,
    "time": 1,
}
EXPECTED_HIDDEN_KEYS = {
    "control.jump_to_step",
    "control.end_foreach",
    "control.foreach_continue",
    "control.foreach_break",
    "graph.call_subgraph",
    "call_blueprint",
}


def run_builder(*, version: str = "0.8.1") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--source-root",
            str(SOURCE_ROOT),
            "--version",
            version,
            "--output",
            str(OUTPUT_PATH),
            "--schema-output",
            str(SCHEMA_PATH),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_source_resource_keys() -> set[str]:
    registry_module = runpy.run_path(
        str(SOURCE_ROOT / "src" / "weconduct" / "builtin_components" / "registry.py")
    )
    drafts_module = runpy.run_path(
        str(SOURCE_ROOT / "src" / "weconduct" / "builtin_components" / "node_drafts.py")
    )
    registry = registry_module["build_builtin_resource_registry"]()
    draft_keys = set(drafts_module["GRAPH_NODE_DRAFT_DEFINITIONS"])
    registry_keys = {item["resource_key"] for item in registry}
    assert registry_keys == draft_keys
    return registry_keys


def read_contract_schema() -> dict[str, Any]:
    sys.path.insert(0, str(SOURCE_ROOT / "src"))
    try:
        from weconduct.contracts.graph import GraphEdge, GraphModel, GraphNode, GraphPort

        return {
            "GraphModel": GraphModel.model_json_schema(),
            "GraphNode": GraphNode.model_json_schema(),
            "GraphPort": GraphPort.model_json_schema(),
            "GraphEdge": GraphEdge.model_json_schema(),
        }
    finally:
        sys.path.pop(0)


def test_manifest_builder_generates_expected_snapshot() -> None:
    result = run_builder()
    assert result.returncode == 0, result.stderr or result.stdout
    assert OUTPUT_PATH.exists(), f"缺少输出文件: {OUTPUT_PATH}"
    assert SCHEMA_PATH.exists(), f"缺少 schema 文件: {SCHEMA_PATH}"

    components = read_json(OUTPUT_PATH)
    assert isinstance(components, list)
    assert len(components) == 126

    resource_keys = [item["resource_key"] for item in components]
    assert len(set(resource_keys)) == 126
    assert set(resource_keys) == read_source_resource_keys()
    assert sum(1 for item in components if item["enabled"]) == 126
    assert Counter(item["capability_domain"] for item in components) == EXPECTED_DOMAIN_COUNTS
    assert sum(1 for item in components if item["component_library_visible"]) == 120
    assert sum(1 for item in components if item["compatibility_only"]) == 6
    assert {item["resource_key"] for item in components if not item["component_library_visible"]} == EXPECTED_HIDDEN_KEYS
    assert sum(1 for item in components if item["direct_runtime_executor"]) == 115
    assert sum(1 for item in components if item["parameter_schema"]) == 32
    assert sum(len(item["ports"]) for item in components) == 397
    assert all(item["display_name_zh"].strip() for item in components)
    assert all(item["description_zh"].strip() for item in components)


def test_manifest_builder_is_deterministic() -> None:
    first = run_builder()
    assert first.returncode == 0, first.stderr or first.stdout
    first_bytes = OUTPUT_PATH.read_bytes()
    first_schema_bytes = SCHEMA_PATH.read_bytes()

    second = run_builder()
    assert second.returncode == 0, second.stderr or second.stdout
    assert OUTPUT_PATH.read_bytes() == first_bytes
    assert SCHEMA_PATH.read_bytes() == first_schema_bytes


def test_graph_schema_matches_contract() -> None:
    result = run_builder()
    assert result.returncode == 0, result.stderr or result.stdout

    schema = read_json(SCHEMA_PATH)
    contract = read_contract_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["graph_schema_version"]["const"] == "graph-v1"
    assert schema["required"] == contract["GraphModel"]["required"]
    assert schema["required"] == ["graph_model_id", "compilation_id"]
    compilation_id_schema = schema["properties"]["compilation_id"]
    if "type" in compilation_id_schema:
        assert compilation_id_schema["type"] == ["string", "null"]
    else:
        assert compilation_id_schema["anyOf"] == [{"type": "string"}, {"type": "null"}]

    defs = schema["$defs"]
    assert defs["GraphNode"]["required"] == contract["GraphNode"]["required"]
    assert defs["GraphPort"]["required"] == contract["GraphPort"]["required"]
    assert defs["GraphEdge"]["required"] == contract["GraphEdge"]["required"]
    assert schema.get("additionalProperties") == contract["GraphModel"].get("additionalProperties")
    assert defs["GraphNode"].get("additionalProperties") == contract["GraphNode"].get("additionalProperties")
    assert defs["GraphPort"].get("additionalProperties") == contract["GraphPort"].get("additionalProperties")
    assert defs["GraphEdge"].get("additionalProperties") == contract["GraphEdge"].get("additionalProperties")
    assert defs["GraphPort"]["properties"]["relation_layer"]["enum"] == ["control", "data", "observe"]
    assert defs["GraphNode"]["properties"]["lowered_kind"]["enum"] == ["execution", "control", "observe", "bridge"]


def test_manifest_builder_rejects_version_mismatch() -> None:
    for version in ("0.5.2", "0.8.0"):
        result = run_builder(version=version)
        assert result.returncode != 0
        assert "0.8.1" in (result.stderr or result.stdout)
