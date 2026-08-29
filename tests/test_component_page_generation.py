from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "build_component_pages.py"


def load_generator():
    assert GENERATOR_PATH.exists(), f"missing component page generator: {GENERATOR_PATH}"
    spec = importlib.util.spec_from_file_location("build_component_pages", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_creates_all_group_and_detail_contracts(tmp_path: Path) -> None:
    generator = load_generator()
    docs_root = tmp_path / "docs"
    graphs_root = docs_root / "assets" / "graphs" / "components"

    result = generator.generate_component_pages(
        manifest_path=ROOT / "data" / "weconduct-0.9.1" / "components.json",
        groups_path=ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        docs_root=docs_root,
        graphs_root=graphs_root,
        include_groups=True,
        include_details=True,
    )

    assert result == {"groups": 26, "details": 135, "group_graphs": 26, "detail_graphs": 135}
    component_root = docs_root / "weconduct" / "components"
    assert (component_root / "index.md").exists()
    group_pages = [path for path in component_root.rglob("index.md") if path != component_root / "index.md"]
    detail_pages = [path for path in (docs_root / "weconduct" / "components").rglob("*.md") if path.name != "index.md"]
    assert len(group_pages) == 26
    assert len(detail_pages) == 135

    required_sections = {
        "功能说明", "什么时候用", "需要什么权限", "端口说明", "配置参数",
        "输入、输出与副作用", "使用示例", "预期结果", "常见问题",
        "注意事项", "相关节点",
    }
    sample = next(path for path in detail_pages if path.name == "set-variable.md")
    text = sample.read_text(encoding="utf-8")
    assert "doc_id: component:data.set_variable" in text
    assert required_sections <= {line[3:] for line in text.splitlines() if line.startswith("## ")}
    assert "<weconduct-graph" in text


def test_generator_is_deterministic_and_graphs_use_manifest_ports(tmp_path: Path) -> None:
    generator = load_generator()
    kwargs = {
        "manifest_path": ROOT / "data" / "weconduct-0.9.1" / "components.json",
        "groups_path": ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        "include_groups": True,
        "include_details": True,
    }
    first_docs = tmp_path / "first" / "docs"
    second_docs = tmp_path / "second" / "docs"
    generator.generate_component_pages(
        docs_root=first_docs,
        graphs_root=first_docs / "assets" / "graphs" / "components",
        **kwargs,
    )
    generator.generate_component_pages(
        docs_root=second_docs,
        graphs_root=second_docs / "assets" / "graphs" / "components",
        **kwargs,
    )

    first_files = {
        path.relative_to(first_docs): path.read_bytes()
        for path in first_docs.rglob("*") if path.is_file()
    }
    second_files = {
        path.relative_to(second_docs): path.read_bytes()
        for path in second_docs.rglob("*") if path.is_file()
    }
    assert first_files == second_files

    markdown_files = {
        path: content
        for path, content in first_files.items()
        if path.suffix == ".md"
    }
    for path, content in markdown_files.items():
        assert content.endswith(b"\n") and not content.endswith(b"\n\n"), (
            f"{path.as_posix()} 必须且只能保留一个 EOF 换行"
        )
        text = content.decode("utf-8")
        trailing_lines = [
            index
            for index, line in enumerate(text.splitlines(), start=1)
            if line != line.rstrip()
        ]
        assert not trailing_lines, f"{path.as_posix()} 存在尾随空格: {trailing_lines}"

    manifest = {item["resource_key"]: item for item in json.loads(kwargs["manifest_path"].read_text(encoding="utf-8"))}
    for graph_path in (first_docs / "assets" / "graphs" / "components").rglob("*.json"):
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in payload["nodes"]:
            expected = {(p["port_id"], p["direction"], p["relation_layer"]) for p in manifest[node["node_kind"]]["ports"]}
            actual = {(p["port_id"], p["direction"], p["relation_layer"]) for p in node["ports"]}
            assert actual == expected


def test_generator_keeps_graph_data_version_when_documenting_new_app_version(tmp_path: Path) -> None:
    generator = load_generator()
    generator.VERSION = "0.9.1"
    docs_root = tmp_path / "docs"
    generator.generate_component_pages(
        manifest_path=ROOT / "data" / "weconduct-0.9.1" / "components.json",
        groups_path=ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        docs_root=docs_root,
        graphs_root=docs_root / "assets" / "graphs" / "components",
        include_groups=False,
        include_details=True,
    )

    graph = json.loads(
        (docs_root / "assets" / "graphs" / "components" / "data" / "data-get-variable.json")
        .read_text(encoding="utf-8")
    )
    compatibility = graph["root_metadata"]["graph_compatibility"]
    assert compatibility["graph_data_version"] == "0.9.0"
    assert compatibility["built_with_app_version"] == "0.9.1"
    assert compatibility["last_upgraded_by_app_version"] == "0.9.1"


def test_parameter_tables_cover_node_config_and_schema_union(tmp_path: Path) -> None:
    generator = load_generator()
    docs_root = tmp_path / "docs"
    generator.generate_component_pages(
        manifest_path=ROOT / "data" / "weconduct-0.9.1" / "components.json",
        groups_path=ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        docs_root=docs_root,
        graphs_root=docs_root / "assets" / "graphs" / "components",
        include_groups=False,
        include_details=True,
    )

    manifest = json.loads((ROOT / "data" / "weconduct-0.9.1" / "components.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "data" / "weconduct-0.9.1" / "component-groups.json").read_text(encoding="utf-8"))
    assignments = catalog["assignments"]
    for component in manifest:
        page_path = assignments[component["resource_key"]]["page_path"].removeprefix("docs/")
        text = (docs_root / page_path).read_text(encoding="utf-8")
        parameter_section = text.split("## 配置参数", 1)[1].split("## 输入、输出与副作用", 1)[0]
        expected_keys = set(component["node_config"]) | set(component["parameter_schema"])
        for key in expected_keys:
            assert f"`{key}`" in parameter_section, f"{component['resource_key']} 缺少参数 {key}"

    get_variable_path = assignments["data.get_variable"]["page_path"].removeprefix("docs/")
    get_variable_text = (docs_root / get_variable_path).read_text(encoding="utf-8")
    assert "| `name` | `string` | 是 | `\"\"` | `default` |" in get_variable_text


def test_key_families_receive_domain_specific_guidance(tmp_path: Path) -> None:
    generator = load_generator()
    docs_root = tmp_path / "docs"
    generator.generate_component_pages(
        manifest_path=ROOT / "data" / "weconduct-0.9.1" / "components.json",
        groups_path=ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        docs_root=docs_root,
        graphs_root=docs_root / "assets" / "graphs" / "components",
        include_groups=False,
        include_details=True,
    )
    catalog = json.loads((ROOT / "data" / "weconduct-0.9.1" / "component-groups.json").read_text(encoding="utf-8"))

    def page(resource_key: str) -> str:
        relative = catalog["assignments"][resource_key]["page_path"].removeprefix("docs/")
        return (docs_root / relative).read_text(encoding="utf-8")

    assert "毫秒" in page("browser.wait_for_timeout")
    assert "URL 模式" in page("browser.wait_for_response")
    assert "下载事件" in page("browser.wait_for_download")
    assert "原列表" in page("data.list_sort")
    assert "工作簿" in page("excel.update_batch")
    assert "项目 Python 运行时" in page("python.run")
    assert "编译器管理" in page("control.retry")


def test_090_network_and_input_examples_follow_runtime_boundaries(tmp_path: Path) -> None:
    generator = load_generator()
    docs_root = tmp_path / "docs"
    generator.generate_component_pages(
        manifest_path=ROOT / "data" / "weconduct-0.9.1" / "components.json",
        groups_path=ROOT / "data" / "weconduct-0.9.1" / "component-groups.json",
        docs_root=docs_root,
        graphs_root=docs_root / "assets" / "graphs" / "components",
        include_groups=False,
        include_details=True,
    )
    catalog = json.loads((ROOT / "data" / "weconduct-0.9.1" / "component-groups.json").read_text(encoding="utf-8"))

    def page(resource_key: str) -> str:
        relative = catalog["assignments"][resource_key]["page_path"].removeprefix("docs/")
        return (docs_root / relative).read_text(encoding="utf-8")

    input_page = page("input.request")
    assert "超时先使用已配置的默认值，否则尝试从 `timed_out` 继续" in input_page
    expected_result = input_page.split("## 预期结果", 1)[1].split("## 常见问题", 1)[0]
    assert expected_result.index("默认值") < expected_result.index("timed_out")
    assert '"endpoint": "https://example.com/graphql"' in page("network.graphql_request")
    assert '"url": "wss://example.com/socket"' in page("network.websocket_connect")
