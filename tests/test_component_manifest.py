import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "tools" / "build_component_manifest.py"
COMMITTED_OUTPUT_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
COMMITTED_SCHEMA_PATH = ROOT / "data" / "weconduct-0.8.1" / "graph-schema.json"

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
SOURCE_ROOT_MARKERS = (
    "pyproject.toml",
    "ui/package.json",
    "ui/src/config/fieldTemplates.ts",
    "src/weconduct/builtin_components/registry.py",
    "src/weconduct/builtin_components/node_drafts.py",
    "src/weconduct/contracts/graph.py",
    "src/weconduct/runtime/engine.py",
)


def is_weconduct_source_root(path: Path) -> bool:
    return all((path / marker).is_file() for marker in SOURCE_ROOT_MARKERS)


def test_docs_checkout_is_not_a_weconduct_source_root() -> None:
    assert not is_weconduct_source_root(ROOT)


@pytest.fixture(scope="session")
def source_root() -> Path | None:
    env_value = os.environ.get("WECONDUCT_SOURCE_ROOT", "").strip()
    candidates: list[Path] = []
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.append(ROOT.parent / "WeConduct")
    for candidate in candidates:
        resolved = candidate.resolve()
        if is_weconduct_source_root(resolved):
            return resolved
    return None


def require_source_root(source_root: Path | None) -> Path:
    if source_root is None:
        pytest.skip(
            "缺少真实源码目录：请设置 WECONDUCT_SOURCE_ROOT 或提供兄弟目录 ../WeConduct。"
        )
    return source_root


@pytest.fixture()
def committed_components() -> list[dict[str, Any]]:
    payload = read_json(COMMITTED_OUTPUT_PATH)
    assert isinstance(payload, list)
    return payload


@pytest.fixture()
def committed_schema() -> dict[str, Any]:
    payload = read_json(COMMITTED_SCHEMA_PATH)
    assert isinstance(payload, dict)
    return payload


def run_builder(
    *,
    source_root: Path,
    output_path: Path,
    schema_path: Path,
    version: str = "0.8.1",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--source-root",
            str(source_root),
            "--version",
            version,
            "--output",
            str(output_path),
            "--schema-output",
            str(schema_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_contract_schema(source_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(source_root / "src"))
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


def test_committed_component_snapshot_statistics(
    committed_components: list[dict[str, Any]],
) -> None:
    assert len(committed_components) == 126

    resource_keys = [item["resource_key"] for item in committed_components]
    assert len(set(resource_keys)) == 126
    assert sum(1 for item in committed_components if item["enabled"]) == 126
    assert Counter(item["capability_domain"] for item in committed_components) == EXPECTED_DOMAIN_COUNTS
    assert sum(1 for item in committed_components if item["component_library_visible"]) == 120
    assert sum(1 for item in committed_components if item["compatibility_only"]) == 6
    assert {
        item["resource_key"]
        for item in committed_components
        if not item["component_library_visible"]
    } == EXPECTED_HIDDEN_KEYS
    assert sum(1 for item in committed_components if item["direct_runtime_executor"]) == 115
    assert sum(1 for item in committed_components if item["parameter_schema"]) == 32
    assert sum(len(item["ports"]) for item in committed_components) == 397
    assert all(item["display_name_zh"].strip() for item in committed_components)
    assert all(item["description_zh"].strip() for item in committed_components)


def test_committed_component_snapshot_shape(
    committed_components: list[dict[str, Any]],
) -> None:
    expected_keys = {
        "resource_id",
        "resource_key",
        "display_name",
        "display_name_zh",
        "description",
        "description_zh",
        "capability_domain",
        "resource_type",
        "enabled",
        "origin",
        "implementation_kind",
        "compatibility_aliases",
        "component_library_visible",
        "compatibility_only",
        "direct_runtime_executor",
        "lowered_kind",
        "expansion_role",
        "ports",
        "node_config",
        "parameter_schema",
        "ui_field_templates",
    }
    assert all(set(item) == expected_keys for item in committed_components)


def test_committed_graph_schema_key_values(committed_schema: dict[str, Any]) -> None:
    assert committed_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert committed_schema["properties"]["graph_schema_version"]["const"] == "graph-v1"
    assert committed_schema["required"] == ["graph_model_id", "compilation_id"]

    defs = committed_schema["$defs"]
    assert defs["GraphPort"]["properties"]["relation_layer"]["enum"] == ["control", "data", "observe"]
    assert defs["GraphNode"]["properties"]["lowered_kind"]["enum"] == [
        "execution",
        "control",
        "observe",
        "bridge",
    ]


def test_committed_snapshots_do_not_embed_absolute_paths() -> None:
    for path in (COMMITTED_OUTPUT_PATH, COMMITTED_SCHEMA_PATH):
        text = path.read_text(encoding="utf-8")
        assert "I:\\" not in text
        assert "C:\\" not in text
        assert "Users\\" not in text
        assert "WeConduct Object" not in text


def test_generated_snapshot_matches_committed_bytes(
    source_root: Path | None,
    tmp_path: Path,
) -> None:
    resolved_source_root = require_source_root(source_root)
    first_dir = tmp_path / "first"
    first_dir.mkdir()
    first_output = first_dir / "components.json"
    first_schema = first_dir / "graph-schema.json"

    result = run_builder(
        source_root=resolved_source_root,
        output_path=first_output,
        schema_path=first_schema,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert first_output.read_bytes() == COMMITTED_OUTPUT_PATH.read_bytes()
    assert first_schema.read_bytes() == COMMITTED_SCHEMA_PATH.read_bytes()

    second_dir = tmp_path / "second"
    second_dir.mkdir()
    second_output = second_dir / "components.json"
    second_schema = second_dir / "graph-schema.json"
    second_result = run_builder(
        source_root=resolved_source_root,
        output_path=second_output,
        schema_path=second_schema,
    )
    assert second_result.returncode == 0, second_result.stderr or second_result.stdout
    assert second_output.read_bytes() == first_output.read_bytes()
    assert second_schema.read_bytes() == first_schema.read_bytes()


def test_generated_graph_schema_matches_pydantic_contract(
    source_root: Path | None,
    tmp_path: Path,
) -> None:
    resolved_source_root = require_source_root(source_root)
    output_path = tmp_path / "components.json"
    schema_path = tmp_path / "graph-schema.json"
    result = run_builder(
        source_root=resolved_source_root,
        output_path=output_path,
        schema_path=schema_path,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    schema = read_json(schema_path)
    contract = read_contract_schema(resolved_source_root)
    assert schema["required"] == contract["GraphModel"]["required"]

    defs = schema["$defs"]
    assert defs["GraphNode"]["required"] == contract["GraphNode"]["required"]
    assert defs["GraphPort"]["required"] == contract["GraphPort"]["required"]
    assert defs["GraphEdge"]["required"] == contract["GraphEdge"]["required"]
    assert schema.get("additionalProperties") == contract["GraphModel"].get("additionalProperties")
    assert defs["GraphNode"].get("additionalProperties") == contract["GraphNode"].get("additionalProperties")
    assert defs["GraphPort"].get("additionalProperties") == contract["GraphPort"].get("additionalProperties")
    assert defs["GraphEdge"].get("additionalProperties") == contract["GraphEdge"].get("additionalProperties")


def test_manifest_builder_rejects_version_mismatch(
    source_root: Path | None,
    tmp_path: Path,
) -> None:
    resolved_source_root = require_source_root(source_root)
    for version in ("0.5.2", "0.8.0"):
        output_path = tmp_path / version / "components.json"
        schema_path = tmp_path / version / "graph-schema.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = run_builder(
            source_root=resolved_source_root,
            output_path=output_path,
            schema_path=schema_path,
            version=version,
        )
        assert result.returncode != 0
        assert "0.8.1" in (result.stderr or result.stdout)
