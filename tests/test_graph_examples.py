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
JS_PATH = ROOT / "docs" / "assets" / "javascripts" / "weconduct-graph.js"
CSS_PATH = ROOT / "docs" / "assets" / "stylesheets" / "weconduct-graph.css"
DOC_PATH = ROOT / "docs" / "weconduct" / "reference" / "embedded-graphs.md"


def run_validate_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
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
    assert compatibility["graph_data_version"] == "0.6.2"
    assert compatibility["built_with_app_version"] == "0.8.1"
    assert compatibility["minimum_loader_app_version"] == "0.5.2"
    assert compatibility["last_upgraded_by_app_version"] == "0.8.1"


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
    bad_built["root_metadata"]["graph_compatibility"]["built_with_app_version"] = "0.8.0"
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


def test_embedded_graph_javascript_contains_required_api_and_interactions() -> None:
    script = read_text(JS_PATH)

    assert 'customElements.define("weconduct-graph"' in script
    assert "fetch(src" in script or "fetch(this.getAttribute(\"src\")" in script
    assert "createElementNS(SVG_NS, \"svg\")" in script
    assert "aria-label" in script
    assert "fullscreen" in script.lower()
    assert "pointerdown" in script
    assert "pointermove" in script
    assert "wheel" in script
    assert "requestFullscreen" in script
    assert "fit" in script.lower()
    assert "zoom in" in script.lower() or "zoom-in" in script.lower()
    assert "zoom out" in script.lower() or "zoom-out" in script.lower()
    assert "Validation failed" in script or "加载失败" in script or "验证失败" in script


def test_embedded_graph_stylesheet_contains_responsive_and_motion_contracts() -> None:
    stylesheet = read_text(CSS_PATH)
    assert "aspect-ratio" in stylesheet
    assert "prefers-reduced-motion" in stylesheet
    assert ":host" in stylesheet or "weconduct-graph" in stylesheet
    assert "--graph-control" in stylesheet or "--graph-data" in stylesheet


def test_embedded_graph_doc_contains_front_matter_and_live_example() -> None:
    content = read_text(DOC_PATH)
    parts = content.split("---", 2)
    assert len(parts) == 3, "front matter 分隔符缺失"
    front_matter = parts[1]
    body = parts[2]

    assert "product: weconduct" in front_matter
    assert "version: 0.8.1" in front_matter
    assert "doc_id: weconduct:reference:embedded-graphs" in front_matter
    assert "<weconduct-graph" in body
    assert 'src="../../assets/graphs/smoke/flow-start.json"' in body
    assert 'title="开始节点"' in body
    assert "可访问回退文本" in body
    assert "20" in body
