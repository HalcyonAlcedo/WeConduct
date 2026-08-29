from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "tools" / "validate_graph_examples.py"
SMOKE_PATH = ROOT / "docs" / "assets" / "graphs" / "smoke" / "flow-start.json"
PACKAGE_PATH = ROOT / "package.json"
MKDOCS_PATH = ROOT / "mkdocs.yml"
GRAPH_RUNTIME_ROOT = ROOT / "graph-runtime" / "src"
JS_PATH = ROOT / "docs" / "assets" / "graph-runtime" / "weconduct-graph.js"
CSS_PATH = ROOT / "docs" / "assets" / "graph-runtime" / "weconduct-graph.css"
DOC_PATH = ROOT / "docs" / "weconduct" / "reference" / "embedded-graphs.md"


def run_validate_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def run_node_script(script: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", script],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_graph_fixture() -> dict[str, Any]:
    return copy.deepcopy(read_json(SMOKE_PATH))


def test_required_files_exist_for_embedded_graphs_task() -> None:
    assert SMOKE_PATH.is_file(), f"missing smoke fixture: {SMOKE_PATH}"
    assert SCRIPT_PATH.is_file(), f"missing validator script: {SCRIPT_PATH}"
    assert DOC_PATH.is_file(), f"missing embedded graph doc page: {DOC_PATH}"


def test_smoke_fixture_matches_graph_v1_contract() -> None:
    graph = read_json(SMOKE_PATH)
    assert graph["graph_schema_version"] == "graph-v1"
    assert graph["edges"] == []
    assert len(graph["nodes"]) == 1

    node = graph["nodes"][0]
    assert node["node_kind"] == "flow.start"
    assert node["position"] == {"x": 80, "y": 96}
    assert [port["port_id"] for port in node["ports"]] == ["out", "out:variables"]
    assert [port["relation_layer"] for port in node["ports"]] == ["control", "data"]

    compatibility = graph["root_metadata"]["graph_compatibility"]
    assert compatibility["graph_data_version"] == "0.9.0"
    assert compatibility["built_with_app_version"] == "0.9.1"
    assert compatibility["minimum_loader_app_version"] == "0.5.2"
    assert compatibility["last_upgraded_by_app_version"] == "0.9.1"


def test_validate_graph_examples_accepts_smoke_fixture() -> None:
    result = run_validate_cli()
    assert result.returncode == 0, result.stderr or result.stdout
    assert "docs/assets/graphs/smoke/flow-start.json" in result.stdout
    assert "errors=0" in result.stdout

    family_result = run_validate_cli("--family", "smoke")
    assert family_result.returncode == 0, family_result.stderr or family_result.stdout
    assert "files=1" in family_result.stdout


def test_validate_graph_examples_rejects_invalid_graphs(tmp_path: Path) -> None:
    graphs_root = tmp_path / "docs" / "assets" / "graphs"
    smoke_dir = graphs_root / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    valid_graph = build_graph_fixture()
    write_json(smoke_dir / "flow-start.json", valid_graph)

    duplicate = build_graph_fixture()
    duplicate["nodes"].append(copy.deepcopy(duplicate["nodes"][0]))
    duplicate["nodes"][1]["position"] = {"x": 220, "y": 96}
    write_json(graphs_root / "duplicate" / "duplicate-node.json", duplicate)

    unknown_kind = build_graph_fixture()
    unknown_kind["nodes"][0]["node_kind"] = "unknown.start"
    write_json(graphs_root / "invalid" / "unknown-kind.json", unknown_kind)

    missing_position = build_graph_fixture()
    missing_position["nodes"][0].pop("position")
    write_json(graphs_root / "invalid" / "missing-position.json", missing_position)

    bad_built = build_graph_fixture()
    bad_built["root_metadata"]["graph_compatibility"]["built_with_app_version"] = "not-a-version"
    write_json(graphs_root / "invalid" / "bad-built-version.json", bad_built)

    bad_edge_reference = build_graph_fixture()
    bad_edge_reference["edges"] = [
        {
            "edge_id": "edge-missing-node",
            "relation_layer": "control",
            "from_node_id": "node-start",
            "to_node_id": "node-missing",
            "from_port_id": "out",
            "to_port_id": "in"
        }
    ]
    write_json(graphs_root / "invalid" / "missing-node.json", bad_edge_reference)

    bad_relation_layer = build_graph_fixture()
    bad_relation_layer["edges"] = [
        {
            "edge_id": "edge-observe",
            "relation_layer": "observe",
            "from_node_id": "node-start",
            "to_node_id": "node-start",
            "from_port_id": "out",
            "to_port_id": "out"
        }
    ]
    write_json(graphs_root / "invalid" / "observe-edge.json", bad_relation_layer)

    bad_port_contract = build_graph_fixture()
    bad_port_contract["nodes"][0]["ports"][0]["port_id"] = "wrong-port"
    write_json(graphs_root / "invalid" / "bad-port-contract.json", bad_port_contract)

    bad_port_layer = build_graph_fixture()
    bad_port_layer["nodes"].append(
        {
            "node_id": "node-next",
            "lowered_kind": "execution",
            "source_anchor_ref": "smoke:next",
            "expansion_role": "action:set_variables_batch",
            "display_name": "下一步",
            "node_kind": "data.set_variables_batch",
            "position": {"x": 240, "y": 96},
            "ports": [
                {
                    "port_id": "in",
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "in.control"
                }
            ],
            "node_config": {}
        }
    )
    bad_port_layer["edges"] = [
        {
            "edge_id": "edge-layer-mismatch",
            "relation_layer": "data",
            "from_node_id": "node-start",
            "to_node_id": "node-next",
            "from_port_id": "out",
            "to_port_id": "in"
        }
    ]
    write_json(graphs_root / "invalid" / "port-layer-mismatch.json", bad_port_layer)

    result = run_validate_cli("--graphs-root", str(graphs_root))
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "duplicate/duplicate-node.json" in combined
    assert "nodes[1].node_id" in combined
    assert "invalid/unknown-kind.json" in combined
    assert "node_kind" in combined
    assert "invalid/missing-position.json" in combined
    assert "position" in combined
    assert "invalid/bad-built-version.json" in combined
    assert "built_with_app_version" in combined
    assert "invalid/missing-node.json" in combined
    assert "to_node_id" in combined
    assert "invalid/observe-edge.json" in combined
    assert "relation_layer" in combined
    assert "invalid/bad-port-contract.json" in combined
    assert "ports[0].port_id" in combined
    assert "invalid/port-layer-mismatch.json" in combined
    assert "from_port_id" in combined or "to_port_id" in combined


def test_validate_graph_examples_rejects_empty_node_list(tmp_path: Path) -> None:
    graphs_root = tmp_path / "docs" / "assets" / "graphs"
    empty_graph = build_graph_fixture()
    empty_graph["nodes"] = []
    write_json(graphs_root / "invalid" / "empty-graph.json", empty_graph)

    result = run_validate_cli("--graphs-root", str(graphs_root))
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "invalid/empty-graph.json" in combined
    assert "at least one node" in combined


def test_embedded_graph_uses_version_locked_vue_flow_runtime() -> None:
    package = read_json(PACKAGE_PATH)
    assert package["dependencies"]["vue"] == "3.5.34"
    assert package["dependencies"]["@vue-flow/core"] == "1.48.2"
    assert package["dependencies"]["@vue-flow/background"] == "1.3.2"
    assert package["dependencies"]["@vue-flow/controls"] == "1.1.3"
    assert package["dependencies"]["@vue-flow/minimap"] == "1.5.4"

    entrypoint = read_text(GRAPH_RUNTIME_ROOT / "index.ts")
    assert "@vue-flow/core/dist/style.css" in entrypoint
    assert "@vue-flow/controls/dist/style.css" in entrypoint
    assert "@vue-flow/minimap/dist/style.css" in entrypoint
    assert "registerWeConductGraph" in entrypoint


def test_embedded_graph_source_contains_required_vue_flow_surface() -> None:
    graph_embed = read_text(GRAPH_RUNTIME_ROOT / "GraphEmbed.vue")
    node = read_text(GRAPH_RUNTIME_ROOT / "DocsBaseNode.vue")
    custom_element = read_text(GRAPH_RUNTIME_ROOT / "custom-element.ts")

    for component in ("VueFlow", "Background", "MiniMap", "Controls"):
        assert component in graph_embed
    assert "fit-view-on-init" in graph_embed
    assert "toggleFullscreen" in graph_embed
    assert "vf-node" in node
    assert "vf-handle" in node
    assert "vf-config" in node
    assert "customElements.define" in custom_element
    assert "resolveGraphSource" in custom_element
    assert "AbortController" in custom_element


def test_embedded_graph_stylesheet_contains_visual_and_responsive_contracts() -> None:
    stylesheet = read_text(GRAPH_RUNTIME_ROOT / "runtime.css")
    assert "weconduct-graph" in stylesheet
    assert "[data-md-color-scheme=\"slate\"]" in stylesheet
    assert ".node-execution" in stylesheet
    assert ".node-control" in stylesheet
    assert ".node-observe" in stylesheet
    assert ".node-bridge" in stylesheet
    assert ".vf-handle" in stylesheet
    assert "--edge-control" in stylesheet
    assert "vector-effect: non-scaling-stroke" in stylesheet
    assert ".wc-metadata-panel" in stylesheet
    assert ".wc-meta-tree-group" in stylesheet
    assert ".wc-graph-viewport.has-metadata" in stylesheet
    assert ".metadata-collapsed" in stylesheet
    assert "@media (max-width: 720px)" in stylesheet
    assert "prefers-reduced-motion" in stylesheet


def test_embedded_graph_build_outputs_and_mkdocs_assets_are_vue_flow_only() -> None:
    assert JS_PATH.is_file() and JS_PATH.stat().st_size > 0
    assert CSS_PATH.is_file() and CSS_PATH.stat().st_size > 0
    assert "process.env.NODE_ENV" not in read_text(JS_PATH)

    mkdocs = read_text(MKDOCS_PATH)
    graph_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in GRAPH_RUNTIME_ROOT.rglob("*")
        if path.is_file()
    )
    assert "assets/graph-runtime/weconduct-graph.js" in mkdocs
    assert "assets/graph-runtime/weconduct-graph.css" in mkdocs
    assert "mermaid" not in mkdocs.lower()
    assert "mermaid" not in graph_sources.lower()


def test_embedded_graph_doc_contains_front_matter_and_live_example() -> None:
    content = read_text(DOC_PATH)
    parts = content.split("---", 2)
    assert len(parts) == 3, "front matter 分隔符缺失"
    front_matter = parts[1]
    body = parts[2]

    assert "product: weconduct" in front_matter
    assert "version: 0.9.1" in front_matter
    assert "doc_id: weconduct:reference:embedded-graphs" in front_matter
    assert "<weconduct-graph" in body
    assert 'src="../../assets/graphs/smoke/flow-start.json"' in body
    assert 'title="开始节点"' in body
    assert "可访问回退文本" in body
    assert "20" in body
    assert "至少 1 个节点" in body or "至少一个节点" in body
