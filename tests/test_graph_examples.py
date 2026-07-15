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


def test_embedded_graph_javascript_runtime_hardening_behaviors() -> None:
    script = f"""
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync({json.dumps(str(JS_PATH))}, "utf8");
const registrations = new Map();

class FakeHTMLElement {{
  constructor() {{
    this._attrs = new Map();
    this.isConnected = true;
    this.classList = {{ add() {{}} }};
  }}
  setAttribute(name, value) {{ this._attrs.set(name, String(value)); }}
  getAttribute(name) {{ return this._attrs.has(name) ? this._attrs.get(name) : null; }}
}}

const context = {{
  console,
  AbortController,
  HTMLElement: FakeHTMLElement,
  customElements: {{
    define(name, ctor) {{ registrations.set(name, ctor); }},
    get(name) {{ return registrations.get(name); }},
  }},
  document: {{
    fullscreenElement: null,
    addEventListener() {{}},
    removeEventListener() {{}},
    exitFullscreen() {{ return Promise.resolve(); }},
  }},
  window: {{}},
  fetch() {{ return Promise.resolve({{ ok: true, json: async () => ({{}}) }}); }},
}};
context.globalThis = context;
vm.runInNewContext(source, context, {{ filename: "weconduct-graph.js" }});
const GraphCtor = registrations.get("weconduct-graph");
if (!GraphCtor) {{
  throw new Error("custom element not registered");
}}

let titleLoadCount = 0;
const titleEl = new GraphCtor();
titleEl._graphData = {{ nodes: [{{}}], edges: [] }};
titleEl.updateRenderedTitle = () => {{ titleEl._titleUpdated = true; }};
titleEl.renderGraph = (graph, title) => {{ titleEl._renderedTitle = title; }};
titleEl.load = () => {{ titleLoadCount += 1; }};
titleEl.attributeChangedCallback("title", "旧标题", "新标题");
if (titleLoadCount !== 0) {{
  throw new Error("title change should not trigger load");
}}
if (!titleEl._titleUpdated && titleEl._renderedTitle !== "新标题") {{
  throw new Error("title change should update rendered title");
}}

const srcEl = new GraphCtor();
let abortCount = 0;
srcEl.abortActiveRequest = () => {{ abortCount += 1; }};
srcEl.load = () => {{ srcEl._loaded = true; }};
srcEl.attributeChangedCallback("src", "old.json", "new.json");
if (abortCount !== 1 || !srcEl._loaded) {{
  throw new Error("src change should abort stale request and reload");
}}

const disconnectEl = new GraphCtor();
let disconnectAbortCount = 0;
disconnectEl.abortActiveRequest = () => {{ disconnectAbortCount += 1; }};
disconnectEl.disconnectedCallback();
if (disconnectAbortCount !== 1) {{
  throw new Error("disconnectedCallback should abort active request");
}}

const fullscreenEl = new GraphCtor();
let fullscreenError = null;
fullscreenEl.renderError = (message) => {{ fullscreenError = message; }};
fullscreenEl.requestFullscreen = () => Promise.reject(new Error("blocked"));
fullscreenEl.toggleFullscreen().then(() => {{
  if (!fullscreenError || !fullscreenError.includes("全屏")) {{
    throw new Error("toggleFullscreen should surface readable fullscreen error");
  }}
}}).catch((error) => {{
  throw error;
}});

const keyEl = new GraphCtor();
keyEl._state.translateX = 0;
keyEl._state.translateY = 0;
keyEl._state.scale = 1;
let fitCount = 0;
keyEl.fitToGraph = () => {{ fitCount += 1; }};
keyEl.updateTransform = () => {{}};
keyEl.handleViewportKeydown({{ key: "ArrowRight", preventDefault() {{}} }});
keyEl.handleViewportKeydown({{ key: "+", preventDefault() {{}} }});
keyEl.handleViewportKeydown({{ key: "0", preventDefault() {{}} }});
if (keyEl._state.translateX <= 0) {{
  throw new Error("keyboard pan should move viewport");
}}
if (keyEl._state.scale <= 1) {{
  throw new Error("keyboard zoom should increase scale");
}}
if (fitCount !== 1) {{
  throw new Error("keyboard 0 should trigger fit");
}}

const pointerEl = new GraphCtor();
pointerEl._state.pointerId = 7;
pointerEl.clearPointerDrag();
if (pointerEl._state.pointerId !== null) {{
  throw new Error("clearPointerDrag should reset pointer state");
}}
"""
    result = run_node_script(script)
    assert result.returncode == 0, result.stderr or result.stdout


def test_embedded_graph_preserves_latest_title_when_pending_request_resolves() -> None:
    script = f"""
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync({json.dumps(str(JS_PATH))}, "utf8");
const registrations = new Map();

class FakeElement {{
  constructor(tagName = "div", namespaceURI = null) {{
    this.tagName = tagName.toUpperCase();
    this.namespaceURI = namespaceURI;
    this.children = [];
    this.attributes = new Map();
    this.style = {{}};
    this.className = "";
    this.classList = {{
      add: (...names) => {{
        const tokens = new Set((this.className || "").split(/\\s+/).filter(Boolean));
        for (const name of names) tokens.add(name);
        this.className = Array.from(tokens).join(" ");
      }},
    }};
    this.textContent = "";
    this.parentNode = null;
    this.onpointerdown = null;
    this.onpointermove = null;
    this.onpointerup = null;
    this.onpointercancel = null;
    this.onlostpointercapture = null;
    this.onkeydown = null;
  }}
  append(...nodes) {{
    for (const node of nodes) {{
      if (node == null) continue;
      node.parentNode = this;
      this.children.push(node);
    }}
  }}
  setAttribute(name, value) {{
    this.attributes.set(name, String(value));
    if (name === "class") this.className = String(value);
  }}
  getAttribute(name) {{
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }}
  addEventListener() {{}}
  removeEventListener() {{}}
  setPointerCapture() {{}}
  releasePointerCapture() {{}}
  querySelector(selector) {{
    const matcher = (node) => {{
      if (selector.startsWith(".")) {{
        return (node.className || "").split(/\\s+/).includes(selector.slice(1));
      }}
      return false;
    }};
    const queue = [...this.children];
    while (queue.length) {{
      const node = queue.shift();
      if (matcher(node)) return node;
      queue.push(...(node.children || []));
    }}
    return null;
  }}
}}

class FakeHTMLElement extends FakeElement {{
  constructor() {{
    super("weconduct-graph");
    this._attrs = new Map();
    this.isConnected = true;
    this.innerHTML = "";
  }}
  setAttribute(name, value) {{
    this._attrs.set(name, String(value));
  }}
  getAttribute(name) {{
    return this._attrs.has(name) ? this._attrs.get(name) : null;
  }}
  append(...nodes) {{
    this.children = [];
    super.append(...nodes);
  }}
}}

let pendingResolve = null;
const graphPayload = {{
  graph_model_id: "pending-title",
  compilation_id: null,
  graph_schema_version: "graph-v1",
  nodes: [{{
    node_id: "node-start",
    node_kind: "flow.start",
    display_name: "开始",
    position: {{ x: 80, y: 96 }},
    ports: [{{ port_id: "out", direction: "output", relation_layer: "control" }}],
    node_config: {{}},
  }}],
  edges: [],
}};

const context = {{
  console,
  AbortController,
  HTMLElement: FakeHTMLElement,
  customElements: {{
    define(name, ctor) {{ registrations.set(name, ctor); }},
    get(name) {{ return registrations.get(name); }},
  }},
  document: {{
    fullscreenElement: null,
    addEventListener() {{}},
    removeEventListener() {{}},
    exitFullscreen() {{ return Promise.resolve(); }},
    createElement(tag) {{ return new FakeElement(tag); }},
    createElementNS(ns, tag) {{ return new FakeElement(tag, ns); }},
  }},
  window: {{}},
  fetch() {{
    return new Promise((resolve) => {{
      pendingResolve = () => resolve({{
        ok: true,
        json: async () => graphPayload,
      }});
    }});
  }},
}};
context.globalThis = context;
vm.runInNewContext(source, context, {{ filename: "weconduct-graph.js" }});

const GraphCtor = registrations.get("weconduct-graph");
if (!GraphCtor) throw new Error("custom element not registered");

async function main() {{
  const element = new GraphCtor();
  element.setAttribute("src", "pending.json");
  element.setAttribute("title", "旧标题");
  const loadPromise = element.load();
  element.setAttribute("title", "新标题");
  element.attributeChangedCallback("title", "旧标题", "新标题");
  pendingResolve();
  await loadPromise;
  const titleNode = element._shell && element._shell.querySelector(".wc-graph-title");
  if (!titleNode) {{
    throw new Error("graph title node missing after load");
  }}
  if (titleNode.textContent !== "新标题") {{
    throw new Error(`expected latest title after pending load, got ${{titleNode.textContent}}`);
  }}
}}

main().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    result = run_node_script(script)
    assert result.returncode == 0, result.stderr or result.stdout


def test_embedded_graph_javascript_contains_required_api_and_interactions() -> None:
    script = read_text(JS_PATH)

    assert 'customElements.define("weconduct-graph"' in script
    assert "fetch(resolveGraphSource(src)" in script
    assert 'assetMarker = "assets/graphs/"' in script
    stylesheet = CSS_PATH.read_text(encoding="utf-8")
    assert "@media (max-width: 720px)" in stylesheet
    assert "aspect-ratio: auto" in stylesheet
    assert "max-width: 100%" in stylesheet
    assert "AbortController" in script or "_requestToken" in script
    assert "createElementNS(SVG_NS, \"svg\")" in script
    assert "aria-label" in script
    assert "fullscreen" in script.lower()
    assert "pointerdown" in script
    assert "pointermove" in script
    assert "pointercancel" in script
    assert "lostpointercapture" in script
    assert "wheel" in script
    assert "keydown" in script
    assert "tabindex" in script.lower() or "tabIndex" in script
    assert "requestFullscreen" in script
    assert "catch" in script
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
    assert "overflow-wrap" in stylesheet or "word-break" in stylesheet
    assert "text-overflow" in stylesheet or "min-width: 0" in stylesheet
    assert "white-space" in stylesheet or "word-break" in stylesheet


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
    assert "至少 1 个节点" in body or "至少一个节点" in body
