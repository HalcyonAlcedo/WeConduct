from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "weconduct-0.9.1" / "components.json"
DEFAULT_GROUPS = ROOT / "data" / "weconduct-0.9.1" / "component-groups.json"
DEFAULT_DOCS_ROOT = ROOT / "docs"
DEFAULT_GRAPHS_ROOT = DEFAULT_DOCS_ROOT / "assets" / "graphs" / "components"
VERSION = "0.9.1"
GRAPH_DATA_VERSION = "0.9.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--groups", default=str(DEFAULT_GROUPS))
    parser.add_argument("--docs-root", default=str(DEFAULT_DOCS_ROOT))
    parser.add_argument("--graphs-root", default=str(DEFAULT_GRAPHS_ROOT))
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--family")
    parser.add_argument("--groups-only", action="store_true")
    parser.add_argument("--details", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global VERSION
    VERSION = args.version
    include_groups = args.groups_only or not args.details
    include_details = args.details or not args.groups_only
    result = generate_component_pages(
        manifest_path=Path(args.manifest).resolve(),
        groups_path=Path(args.groups).resolve(),
        docs_root=Path(args.docs_root).resolve(),
        graphs_root=Path(args.graphs_root).resolve(),
        include_groups=include_groups,
        include_details=include_details,
        families=parse_selectors(args.family),
    )
    print(
        f"groups={result['groups']} details={result['details']} "
        f"group_graphs={result['group_graphs']} detail_graphs={result['detail_graphs']}"
    )
    return 0


def parse_selectors(raw: str | None) -> set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


def generate_component_pages(
    *,
    manifest_path: Path,
    groups_path: Path,
    docs_root: Path,
    graphs_root: Path,
    include_groups: bool,
    include_details: bool,
    families: set[str] | None = None,
) -> dict[str, int]:
    manifest = read_json(manifest_path)
    catalog = read_json(groups_path)
    if not isinstance(manifest, list) or not isinstance(catalog, dict):
        raise ValueError("component manifest or group catalog has invalid shape")
    groups = catalog.get("groups")
    assignments = catalog.get("assignments")
    if not isinstance(groups, list) or not isinstance(assignments, dict):
        raise ValueError("component group catalog is missing groups or assignments")

    manifest_by_key = {item["resource_key"]: item for item in manifest}
    group_by_id = {group["group_id"]: group for group in groups}
    keys_by_group: dict[str, list[str]] = {group_id: [] for group_id in group_by_id}
    for resource_key, assignment in assignments.items():
        keys_by_group[assignment["primary_group_id"]].append(resource_key)

    selectors = families or set()
    selected_group_ids = {
        group["group_id"]
        for group in groups
        if not selectors or group["family"] in selectors or group["group_id"] in selectors
    }
    if selectors and not selected_group_ids:
        raise ValueError(f"no component groups matched selectors: {sorted(selectors)}")

    counts = {"groups": 0, "details": 0, "group_graphs": 0, "detail_graphs": 0}
    if include_groups:
        write_global_index(docs_root, groups, keys_by_group, manifest_by_key)
        for group in groups:
            if group["group_id"] not in selected_group_ids:
                continue
            keys = sorted(keys_by_group[group["group_id"]])
            write_group_page(docs_root, graphs_root, group, keys, manifest_by_key, assignments)
            write_group_graph(graphs_root, group, keys, manifest_by_key)
            counts["groups"] += 1
            counts["group_graphs"] += 1

    if include_details:
        for resource_key in sorted(manifest_by_key):
            assignment = assignments[resource_key]
            group = group_by_id[assignment["primary_group_id"]]
            if group["group_id"] not in selected_group_ids:
                continue
            component = manifest_by_key[resource_key]
            write_detail_page(
                docs_root, graphs_root, component, assignment, group,
                keys_by_group[group["group_id"]], manifest_by_key, assignments,
            )
            write_detail_graph(graphs_root, component, group["family"])
            counts["details"] += 1
            counts["detail_graphs"] += 1
    return counts


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def docs_path(docs_root: Path, catalog_path: str) -> Path:
    prefix = "docs/"
    if not catalog_path.startswith(prefix):
        raise ValueError(f"catalog path must start with docs/: {catalog_path}")
    return docs_root / catalog_path[len(prefix):]


def relative_link(from_page: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_page.parent)).as_posix()


def graph_compatibility() -> dict[str, Any]:
    return {
        "graph_data_version": GRAPH_DATA_VERSION,
        "built_with_app_version": VERSION,
        "minimum_loader_app_version": "0.5.2",
        "last_upgraded_by_app_version": VERSION,
        "upgrade_history": [],
    }


def node_from_component(component: dict[str, Any], index: int, *, sample: bool = True) -> dict[str, Any]:
    resource_key = component["resource_key"]
    return {
        "node_id": f"node-{slug(resource_key)}-{index + 1}",
        "lowered_kind": component["lowered_kind"],
        "source_anchor_ref": f"docs:{resource_key}:{index + 1}",
        "expansion_role": component["expansion_role"],
        "display_name": component["display_name_zh"],
        "node_kind": resource_key,
        "position": {"x": 60 + (index % 3) * 290, "y": 80 + (index // 3) * 190},
        "ports": component["ports"],
        "node_config": build_sample_config(component) if sample else component.get("node_config", {}),
    }


def graph_payload(graph_id: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "graph_model_id": graph_id,
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": nodes,
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "root_metadata": {"graph_compatibility": graph_compatibility()},
        "graph_effective_diagnostic_anchor_refs": [],
    }


def slug(resource_key: str) -> str:
    return resource_key.replace(".", "-").replace("_", "-")


def write_global_index(
    docs_root: Path,
    groups: list[dict[str, Any]],
    keys_by_group: dict[str, list[str]],
    manifest: dict[str, dict[str, Any]],
) -> None:
    path = docs_root / "weconduct" / "components" / "index.md"
    total_count = len(manifest)
    visible_count = sum(
        1 for component in manifest.values()
        if component.get("component_library_visible") is True
    )
    compatibility_count = sum(
        1 for component in manifest.values()
        if component.get("compatibility_only") is True
    )
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        "doc_id: weconduct:components:index", "---", "", "# 内置节点参考", "",
        f"WeConduct {VERSION} 提供了 " + str(total_count) + " 个内置节点，涵盖了浏览器自动化、网络自动化、数据处理、文件操作、流程控制等常见任务。",
        "", f"其中 {visible_count} 个节点可直接从组件库拖入画布使用，另有 {compatibility_count} 个节点仅用于兼容旧版项目的内部迁移。",
        "", "## 如何查找节点", "",
        "你可以按中文名称、英文名称或资源键（如 `browser.click`）在组件库中搜索。",
        "每个节点类别下都有一个聚合页，方便你对比同类节点并了解常见搭配方式；",
        "点击具体节点会进入详情页，提供完整的端口说明、配置参数、所需权限和使用建议。",
        "", "## 节点分类", "",
    ]
    for group in groups:
        group_page = docs_path(docs_root, group["index_path"])
        lines.append(
            f"- [{group['title_zh']}]({relative_link(path, group_page)})："
            f"{group['description_zh']}（{len(keys_by_group[group['group_id']])} 个节点）"
        )
    lines.extend([
        "", "## 阅读建议", "",
        "如果你是第一次使用某个节点，建议先从聚合页了解同类节点的差异，再进入详情页查看完整的配置说明。",
        "兼容与内部节点不会出现在普通组件库中，通常不需要关注，除非你在维护旧版项目。",
        "", "节点图的使用方法见[内嵌节点图](../reference/embedded-graphs.md)。",
    ])
    write_text(path, "\n".join(lines))


def write_group_page(
    docs_root: Path,
    graphs_root: Path,
    group: dict[str, Any],
    keys: list[str],
    manifest: dict[str, dict[str, Any]],
    assignments: dict[str, dict[str, Any]],
) -> None:
    path = docs_path(docs_root, group["index_path"])
    graph_path = graphs_root / "groups" / f"{group['group_id']}.json"
    shown = keys[:6]
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        f"doc_id: component-group:{group['group_id']}", "---", "",
        f"# {group['title_zh']}", "", group["description_zh"], "",
    ]
    if group["group_id"] == "compatibility-and-internal":
        lines.extend([
            "",
            "!!! warning 这些节点不在组件库中",
            "    本组的 " + str(len(keys)) + " 个节点仅用于兼容旧版项目或内部图结构迁移，**不会出现在普通组件库中**，也不能从组件库拖入画布。如果你在旧项目中看到这些节点，说明它们是从早期版本自动迁移过来的。新项目不需要关注这些节点。",
            "",
        ])
    lines.extend([
        "## 节点速览", "",
        "| 节点 | 资源键 | 主要用途 |", "|---|---|---|",
    ])
    for key in keys:
        item = manifest[key]
        detail_path = docs_path(docs_root, assignments[key]["page_path"])
        lines.append(
            f"| [{item['display_name_zh']}]({relative_link(path, detail_path)}) | `{key}` | {item['description_zh']} |"
        )
    lines.extend(["", "## 典型搭配", ""])
    if len(shown) > 1:
        names = " → ".join(manifest[key]["display_name_zh"] for key in shown[:4])
        lines.append(f"这类节点通常会按 `{names}` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。")
    else:
        lines.append("本组只有一个节点，通常与流程入口、变量节点以及其他功能模块组合使用。")
    lines.extend([
        "", "## 节点对比图", "",
        f"<weconduct-graph src=\"{relative_link(path, graph_path)}\" title=\"{group['title_zh']}节点概览\">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>",
        "", "上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。",
        "", "## 全部节点", "",
    ])
    for key in keys:
        item = manifest[key]
        detail_path = docs_path(docs_root, assignments[key]["page_path"])
        visibility = "兼容/内部（不在组件库中显示）" if item["compatibility_only"] else ""
        line = f"- [{item['display_name_zh']}]({relative_link(path, detail_path)}) (`{key}`)"
        if visibility:
            line += f"：{visibility}"
        lines.append(line)
    write_text(path, "\n".join(lines))


def write_group_graph(graphs_root: Path, group: dict[str, Any], keys: list[str], manifest: dict[str, dict[str, Any]]) -> None:
    nodes = [node_from_component(manifest[key], index) for index, key in enumerate(keys[:6])]
    write_json(
        graphs_root / "groups" / f"{group['group_id']}.json",
        graph_payload(f"graph:docs:group:{group['group_id']}", nodes),
    )


def write_detail_page(
    docs_root: Path,
    graphs_root: Path,
    component: dict[str, Any],
    assignment: dict[str, Any],
    group: dict[str, Any],
    related_keys: list[str],
    manifest: dict[str, dict[str, Any]],
    assignments: dict[str, dict[str, Any]],
) -> None:
    path = docs_path(docs_root, assignment["page_path"])
    graph_path = graphs_root / group["family"] / f"{slug(component['resource_key'])}.json"
    ports = component.get("ports", [])
    input_ports = [port for port in ports if port["direction"] == "input"]
    output_ports = [port for port in ports if port["direction"] == "output"]
    parameters = merged_parameters(component)
    config = build_sample_config(component)
    group_page = docs_path(docs_root, group["index_path"])
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        f"doc_id: component:{component['resource_key']}", "---", "",
        f"# {component['display_name_zh']}", "",
        f"资源键：`{component['resource_key']}`　|　英文名：{component['display_name']}",
        "## 功能说明", "", component["description_zh"], "",
        "## 什么时候用", "", usage_text(component), "",
        "## 需要什么权限", "", permission_text(component), "",
        "## 端口说明", "",
        "| 端口 | 方向 | 关系层 | 语义 |", "|---|---|---|---|",
    ]
    if ports:
        for port in ports:
            lines.append(
                f"| `{port['port_id']}` | {port['direction']} | `{port['relation_layer']}` | `{port['semantic_slot']}` |"
            )
    else:
        lines.append("| 无 | - | - | 该节点不声明端口 |")
    lines.extend(["", "## 配置参数", ""])
    if parameters:
        lines.extend(["| 参数 | 类型 | 必填 | 默认值 | 编辑器 |", "|---|---|---|---|---|"])
        defaults = component.get("node_config", {})
        for key, meta in parameters.items():
            default = json.dumps(defaults.get(key), ensure_ascii=False)
            lines.append(
                f"| `{key}` | `{meta.get('type', 'any')}` | {'是' if meta.get('required') else '否'} | `{default}` | `{meta.get('editor_kind') or 'default'}` |"
            )
    else:
        lines.append("该节点没有额外参数，其行为完全由输入数据和运行上下文决定。")
    lines.extend([
        "", "## 输入、输出与副作用", "",
        io_text(component, input_ports, output_ports), "",
        "## 使用示例", "",
        f"<weconduct-graph src=\"{relative_link(path, graph_path)}\" title=\"{component['display_name_zh']}配置示例\">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>",
        "", "示例配置：", "", "```json", json.dumps(config, ensure_ascii=False, indent=2), "```", "",
        "使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。",
        "", "## 预期结果", "", expected_result_text(component, output_ports), "",
        "## 常见问题", "", common_errors_text(component), "",
        "## 注意事项", "", limitation_text(component), "",
        "## 相关节点", "",
        f"- 返回[{group['title_zh']}]({relative_link(path, group_page)})聚合页查看更多同类节点。",
    ])
    siblings = [key for key in related_keys if key != component["resource_key"]][:5]
    for key in siblings:
        sibling_path = docs_path(docs_root, assignments[key]["page_path"])
        lines.append(
            f"- [{manifest[key]['display_name_zh']}]({relative_link(path, sibling_path)}) (`{key}`)。"
        )
    write_text(path, "\n".join(lines))


def write_detail_graph(graphs_root: Path, component: dict[str, Any], family: str) -> None:
    payload = graph_payload(
        f"graph:docs:component:{component['resource_key']}",
        [node_from_component(component, 0)],
    )
    write_json(graphs_root / family / f"{slug(component['resource_key'])}.json", payload)


def build_sample_config(component: dict[str, Any]) -> dict[str, Any]:
    defaults = json.loads(json.dumps(component.get("node_config", {}), ensure_ascii=False))
    parameters = merged_parameters(component)
    for key, meta in parameters.items():
        current = defaults.get(key)
        if current not in (None, "", [], {}):
            continue
        if current is None and not meta.get("required"):
            continue
        defaults[key] = sample_value(
            key, meta.get("type", "any"), current,
            resource_key=component["resource_key"],
        )
    return defaults


def merged_parameters(component: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults = component.get("node_config", {})
    schema = component.get("parameter_schema", {})
    keys = list(defaults)
    keys.extend(key for key in schema if key not in defaults)
    result: dict[str, dict[str, Any]] = {}
    for key in keys:
        meta = dict(schema.get(key, {}))
        default = defaults.get(key)
        meta.setdefault("type", infer_parameter_type(key, default))
        meta.setdefault("required", default == "")
        meta.setdefault("editor_kind", "default")
        result[key] = meta
    return result


def infer_parameter_type(key: str, value: Any) -> str:
    lower = key.lower()
    if lower in {"timeout", "delay_ms", "row_index", "start", "end", "x", "y", "index", "level", "max_jumps", "status_code"}:
        return "integer"
    if lower.endswith(("_index", "_count", "_ms")):
        return "integer"
    if lower in {"activate", "current", "http_only", "secure", "clear_after", "has_header"}:
        return "boolean"
    if value is None:
        return "any"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "any"


def sample_value(key: str, field_type: str, current: Any, *, resource_key: str = "") -> Any:
    lower = key.lower()
    if "selector" in lower:
        return "#example"
    if resource_key == "network.graphql_request" and lower == "endpoint":
        return "https://example.com/graphql"
    if lower in {"url", "base_url"} or lower.endswith("_url"):
        if resource_key == "network.websocket_connect" and lower == "url":
            return "wss://example.com/socket"
        if resource_key == "network.sse_connect" and lower == "url":
            return "https://example.com/events"
        return "https://example.com"
    if "sheet" in lower:
        return "Sheet1"
    if "cell" in lower:
        return "A1"
    if lower == "code":
        return "result = variables"
    if "path" in lower or "file" in lower:
        if resource_key.startswith("excel.") or resource_key.endswith("to_excel"):
            return "output/example.xlsx"
        if "csv" in resource_key:
            return "output/example.csv"
        return "output/example.txt"
    if "pattern" in lower:
        return "example"
    if "expression" in lower or "condition" in lower:
        return "1 == 1"
    if lower in {"name", "variable_name", "output_variable_name"} or lower.endswith("_variable"):
        return "result"
    if lower == "method":
        return "GET"
    if field_type in {"integer", "number"}:
        return 1
    if field_type == "boolean":
        return False
    if field_type in {"object", "map"}:
        return {}
    if field_type in {"array", "list"}:
        return []
    if current is None and field_type == "any":
        return "example"
    return "example"


def usage_text(component: dict[str, Any]) -> str:
    key = component["resource_key"]
    guidance = domain_guidance(key)
    if guidance.get("usage"):
        return guidance["usage"]
    if key.startswith("browser."):
        return "在浏览器自动化流程中执行该动作，需要当前页面或浏览器上下文已经就绪。"
    if key.startswith("data."):
        return "处理运行时数据、变量或列表，结果可以交给后续节点继续使用。"
    if key.startswith("control."):
        return "改变流程的执行路径，比如分支、循环、并行或失败重试。"
    if key.startswith("excel."):
        return "读取或修改 Excel 工作簿中的结构化数据。"
    if key.startswith("file."):
        return "在项目允许的路径内处理文本或 CSV 文件。"
    return f"当你需要 {component['display_name_zh']} 功能时使用。"


def permission_text(component: dict[str, Any]) -> str:
    key = component["resource_key"]
    permissions: list[str] = []
    if key.startswith(("file.", "excel.")):
        permissions.append("需要开启文件访问权限，并确保目标路径在允许的目录范围内")
    if key.startswith("network."):
        permissions.append("需要按目标地址开启本地或远程网络访问")
        if key == "network.upload":
            permissions.append("需要开启文件访问，并确保上传文件位于允许的目录范围内")
    if key == "python.run":
        permissions.append("需要开启 Python 执行权限，并准备好项目的 Python 运行时环境")
    if "screenshot" in key:
        permissions.append("需要开启浏览器截图和文件访问")
    if "download" in key:
        permissions.append("需要开启浏览器下载和文件访问")
    if "upload" in key:
        permissions.append("需要开启浏览器上传和文件访问")
    if "cookie" in key:
        permissions.append("需要开启 Cookie 操作权限")
    if "storage" in key:
        permissions.append("需要开启浏览器存储操作权限")
    if key in {"browser.inject_js", "browser.run_js"} or "script" in key or "javascript" in key:
        permissions.append("需要按节点行为开启 JavaScript 注入或求值权限")
    if key.startswith("browser."):
        permissions.append("需要开启浏览器执行器，并确保存在可用的页面目标")
    if key == "browser.download_file":
        permissions.append("需要按目标 URL 开启本地或远程网络访问")
    if not permissions:
        return "该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。"
    return "；".join(dict.fromkeys(permissions)) + "。"


def io_text(component: dict[str, Any], inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> str:
    input_names = "、".join(f"`{item['port_id']}`" for item in inputs) or "没有显式输入端口"
    output_names = "、".join(f"`{item['port_id']}`" for item in outputs) or "没有显式输出端口"
    key = component["resource_key"]
    guidance = domain_guidance(key)
    side_effect = guidance.get("side_effect", "更新运行时数据")
    if key.startswith("browser."):
        side_effect = guidance.get("side_effect", "可能改变页面状态、浏览器上下文、网络记录或本地文件")
    elif key.startswith(("file.", "excel.")):
        side_effect = guidance.get("side_effect", "可能读取或写入文件")
    elif key.startswith("control."):
        side_effect = "改变后续执行路径"
    return f"输入端口：{input_names}。输出端口：{output_names}。对外影响：{side_effect}。"


def expected_result_text(component: dict[str, Any], outputs: list[dict[str, Any]]) -> str:
    guidance = domain_guidance(component["resource_key"])
    if guidance.get("expected"):
        return guidance["expected"]
    data_outputs = [item for item in outputs if item["relation_layer"] == "data"]
    if data_outputs:
        names = "、".join(f"`{item['port_id']}`" for item in data_outputs)
        return f"节点执行成功后，状态为 `succeeded`。你可以从 {names} 端口或节点输出字段获取结果。"
    return "节点执行成功后，状态为 `succeeded`，控制流继续向下一个节点传递。如果没有数据输出，可以通过运行日志和节点结果确认执行情况。"


def common_errors_text(component: dict[str, Any]) -> str:
    required = [key for key, meta in merged_parameters(component).items() if meta.get("required")]
    messages = []
    if required:
        messages.append("缺少必填参数：" + "、".join(f"`{key}`" for key in required))
    messages.extend(["端口名称写错或关系层不匹配", "输入值的类型与参数要求不一致"])
    if component["resource_key"].startswith(("browser.", "file.", "excel.", "http.", "network.", "python.")):
        messages.append("运行环境、资源路径或安全权限未正确配置")
    extra = domain_guidance(component["resource_key"]).get("error")
    if extra:
        messages.append(extra)
    return "；".join(messages) + "。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。"


def limitation_text(component: dict[str, Any]) -> str:
    notes = []
    if component["compatibility_only"]:
        notes.append("该节点仅用于兼容旧版项目或内部图加载，不会出现在普通组件库中，不建议在新流程中使用")
    if not component["component_library_visible"]:
        notes.append("该节点不能从普通组件库直接添加")
    if component["resource_key"].startswith("browser."):
        notes.append("页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器")
    extra = domain_guidance(component["resource_key"]).get("limit")
    if extra:
        notes.append(extra)
    notes.append("示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入")
    return "；".join(notes) + "。"


def domain_guidance(resource_key: str) -> dict[str, str]:
    if resource_key == "browser.wait_for_timeout":
        return {
            "usage": "在没有可观测页面条件、只能为外部过程留出固定时间时使用；`timeout` 以毫秒计。",
            "expected": "等待指定毫秒数后返回 `status = succeeded`，随后继续控制流。",
            "limit": "固定等待不会确认页面真的就绪，优先使用元素、文本、请求或响应等待",
        }
    if resource_key in {"browser.wait_for_request", "browser.wait_for_response"}:
        target = "请求" if resource_key.endswith("request") else "响应"
        return {
            "usage": f"查询浏览器会话已记录的网络活动，按 URL 模式和可选条件等待匹配的{target}。",
            "expected": f"在超时前捕获匹配{target}后成功，并把捕获记录写入节点结果。",
            "error": f"URL 模式、方法或状态码未匹配任何{target}",
            "limit": "浏览器会话记录器必须在目标事件发生前已安装，记录最多保留最近 500 条；`timeout` 以毫秒计",
        }
    if resource_key == "browser.wait_for_download":
        return {
            "usage": "在触发下载的交互之前或对应控制链中等待浏览器下载事件，并保存下载结果。",
            "side_effect": "等待下载事件并把文件写入允许的下载目录",
            "expected": "捕获下载事件后返回保存路径，并可按 `variable_name` 写入运行时变量。",
            "error": "超时前没有下载事件，或下载目录不满足文件权限",
        }
    if resource_key == "browser.download_file":
        return {
            "usage": "已知文件 URL 且不需要页面点击时，直接发起浏览器上下文下载。",
            "side_effect": "通过直接网络请求访问目标 URL，并把响应内容写入下载目录",
            "expected": "下载完成后返回最终文件路径和下载元数据。",
            "error": "URL 不可访问、响应不是可下载内容或文件写入被拒绝",
            "limit": "该节点不复用当前标签页导航，仍受本地/远程网络和文件允许根约束",
        }
    if resource_key.startswith("browser.wait_for_"):
        return {
            "usage": "在继续操作前等待页面达到该节点声明的条件，避免用固定延时猜测就绪时机。",
            "expected": "条件在超时前满足时返回 `status = succeeded`，否则产生超时诊断。",
            "limit": "`timeout` 以毫秒计；匹配模式和页面上下文必须与目标元素或 URL 一致",
        }
    if resource_key in {"browser.switch_to_frame", "browser.open_frame_page"}:
        return {
            "usage": "目标元素位于 iframe 时，按选择器、名称、URL 片段或索引定位框架上下文。",
            "side_effect": "切换当前页面操作所使用的 frame 上下文",
            "expected": "成功定位 frame 后，后续选择器操作在该 frame 上下文执行。",
            "error": "多个定位条件互相冲突，或没有找到匹配 frame",
        }
    if resource_key in {"browser.switch_to_parent_frame", "browser.switch_to_default_content"}:
        return {
            "usage": "完成 iframe 内操作后，返回父级 frame 或顶层页面上下文。",
            "side_effect": "改变后续浏览器节点使用的 frame 上下文",
            "expected": "上下文切换成功，后续选择器从新的 frame 层级解析。",
        }
    if resource_key in {"browser.open_tab", "browser.switch_tab", "browser.close_tab", "browser.wait_for_popup"}:
        return {
            "usage": "在多标签页或弹窗流程中创建、定位、激活或关闭页面目标。",
            "side_effect": "改变浏览器页面集合或当前活动页面",
            "expected": "目标标签页被定位并按配置激活、关闭或写入变量。",
            "error": "索引、标签或 URL 模式没有匹配可用页面",
        }
    if resource_key.startswith("browser.") and any(token in resource_key for token in ("cookie", "storage")):
        return {
            "usage": "读写当前浏览器上下文的 Cookie 或 Web Storage，用于会话恢复和状态准备。",
            "side_effect": "读取、修改或清除浏览器持久状态；写操作会影响后续页面请求",
            "expected": "读取节点返回目标值或默认值；写入和删除节点完成对应状态变更。",
            "limit": "域、路径、secure 属性和当前页面 origin 会限制数据可见范围",
        }
    if resource_key in {"browser.inject_js", "browser.run_js"}:
        return {
            "usage": "内置浏览器动作无法表达目标行为时，在当前页面上下文执行受控 JavaScript。",
            "side_effect": "脚本可读取或修改页面 DOM 和页面全局状态",
            "expected": "脚本执行完成；`run_js` 可把可序列化返回值写入变量。",
            "error": "脚本语法错误、返回值不可序列化或 JavaScript 权限未开启",
            "limit": "脚本依赖页面实现，导航后注入状态不会自动保留",
        }
    if resource_key.startswith("data.list_"):
        mutation = resource_key in {
            "data.list_append", "data.list_extend", "data.list_set", "data.list_insert",
            "data.list_remove", "data.list_sort", "data.list_reverse",
        }
        return {
            "usage": "对运行时变量中的列表执行定位、读取或变更；索引从 `0` 开始。",
            "side_effect": "直接更新原列表变量" if mutation else "读取原列表并输出查询结果",
            "expected": "列表操作完成后返回结果；变更类节点会保留更新后的原列表。",
            "error": "目标变量不是列表、索引越界或待查找值不存在",
            "limit": "切片的 `end` 遵循不包含结束位置的列表切片语义",
        }
    if resource_key.startswith("data."):
        return {
            "usage": "在流程中读取、写入或转换运行时变量，并把结果交给后续节点。",
            "side_effect": "按 `variable_name` 或节点语义读取或更新运行时变量",
            "expected": "操作成功后返回处理结果；声明输出变量时同步写入运行时上下文。",
            "error": "变量不存在、值类型不兼容或表达式/正则格式无效",
        }
    if resource_key.startswith("control."):
        return {
            "usage": "构造分支、循环、并行或可靠性控制结构，由编译器管理控制出口和运行状态。",
            "side_effect": "不直接处理业务数据，而是选择或重复执行后续控制分支",
            "expected": "条件、汇合或尝试状态确定后，从对应控制输出继续。",
            "error": "控制出口未连接、表达式无效或循环/重试边界配置不合法",
            "limit": "控制节点必须按端口语义成对组织，不能用普通执行节点替代结构边界",
        }
    if resource_key.startswith("excel."):
        return {
            "usage": "在允许路径内读取或更新 Excel 工作簿；先确认文件、工作表和单元格/行表范围。",
            "side_effect": "读取工作簿，写入类节点还会更新并保存目标文件",
            "expected": "读取节点返回结构化值；写入或批量更新节点保存工作簿后成功。",
            "error": "工作簿或工作表不存在、单元格/行参数无效或文件被占用",
            "limit": "行号和表头选项会影响数据定位，写入前应确认目标文件备份",
        }
    if resource_key == "file.read_text_file":
        return {
            "usage": "从允许文件根中读取文本内容，并按配置的编码返回结果。",
            "side_effect": "读取目标文本文件，不修改文件内容",
            "expected": "返回文件路径、编码和 `content`；当前节点不使用 CSV 行列参数，也不会执行写入。",
            "error": "路径越界、文件不存在、编码不匹配或文件不可访问",
            "limit": "读取结果会进入运行时输出；需要写入变量时应使用明确的数据输出或后续变量节点",
        }
    if resource_key == "file.write_text_file":
        return {
            "usage": "把文本或可转换的运行时值写入允许文件根中的目标文件。",
            "side_effect": "创建或覆盖目标文本文件",
            "expected": "字符串原样写入；`dict`/`list` 转为 UTF-8 JSON 文本；其他值使用运行时字符串表示，并返回路径、编码和 `bytes_written`。",
            "error": "路径越界、编码不匹配、内容无法转换或文件不可写",
            "limit": "该节点不使用 CSV 行列索引或 `has_header`；需要长期保存会话数据时应显式选择持久化路径",
        }
    if resource_key == "file.read_csv_cell":
        return {
            "usage": "读取 CSV 指定行和列的单元格值。",
            "side_effect": "读取目标 CSV 文件，不修改文件内容",
            "expected": "返回选定行列的 `value`，并可按节点配置写入运行时变量。",
            "error": "路径越界、CSV 格式/编码错误、行号越界或列不存在",
            "limit": "`has_header` 会影响列名解析；`row_index` 从 `0` 开始",
        }
    if resource_key == "file.read_csv_row":
        return {
            "usage": "读取 CSV 指定行，并返回该行的结构化值。",
            "side_effect": "读取目标 CSV 文件，不修改文件内容",
            "expected": "返回 `row` 和行元数据，并可按节点配置写入运行时变量。",
            "error": "路径越界、CSV 格式/编码错误或行号越界",
            "limit": "`row_index` 从 `0` 开始；`has_header` 会影响行对象的列名表示",
        }
    if resource_key == "file.read_csv_table":
        return {
            "usage": "读取 CSV 文件的完整表格，并保留表头和行集合。",
            "side_effect": "读取目标 CSV 文件，不修改文件内容",
            "expected": "返回 `headers`、`rows` 和 `row_count`，并可按节点配置写入运行时变量。",
            "error": "路径越界、CSV 格式/编码错误或文件不可访问",
            "limit": "`has_header` 决定是否把首行作为表头；大文件会占用运行时内存",
        }
    if resource_key.startswith("file."):
        return {
            "usage": "在允许文件根中读取或写入文本、CSV 数据，并显式选择编码和表头规则。",
            "side_effect": "读取目标文件；写入节点会创建或覆盖文件内容",
            "expected": "读取结果写入指定变量，或文件写入完成后返回保存信息。",
            "error": "路径越界、编码不匹配、CSV 行列越界或文件不可访问",
            "limit": "CSV 行列索引和 `has_header` 会共同影响实际定位",
        }
    if resource_key.startswith("network."):
        network_guidance = {
            "network.http_request": {
                "usage": "向 HTTP/HTTPS 目标发送 REST 请求；使用上下文策略继承认证、代理和会话状态，也可以通过数据端口覆盖本次请求。",
                "side_effect": "访问本地或远程网络目标，并可能对服务端产生写操作",
                "expected": "请求完成后返回响应摘要、状态码、响应头、响应体引用和请求元数据。",
                "error": "URL、方法或请求体无效，网络权限不足，认证/TLS/代理配置错误，连接超时或响应处理失败",
                "limit": "敏感认证值在运行链路中可用，但日志、事件、历史和诊断只保留脱敏结果",
            },
            "network.upload": {
                "usage": "把允许目录中的文件或运行时数据上传到 HTTP/HTTPS 目标，支持 multipart 字段和校验值。",
                "side_effect": "读取本地文件并向网络目标上传数据",
                "expected": "上传完成后返回响应、上传字节数、源校验值和请求元数据。",
                "error": "文件路径越界、文件不可读、目标拒绝上传、网络权限或认证配置错误",
                "limit": "上传文件受文件访问允许根和大小限制约束",
            },
            "network.download": {
                "usage": "从 HTTP/HTTPS 目标下载响应内容，并把结果保存到网络运行时的会话临时资源。",
                "side_effect": "访问网络目标并创建会话级临时下载资源",
                "expected": "下载完成后返回响应、文件大小、SHA-256 校验值和最终 URL。",
                "error": "目标不可访问、响应状态不符合预期、网络权限不足或临时资源写入失败",
                "limit": "临时下载资源随执行会话清理；需要长期保存时显式使用文件节点持久化",
            },
            "network.response_assert": {
                "usage": "对前一个网络节点的响应执行状态码、响应头、正文、JSON、Schema、URL 或耗时断言。",
                "side_effect": "读取响应并选择通过或失败控制分支",
                "expected": "断言通过时从 `passed` 继续，失败时从 `failed` 继续，并输出断言报告。",
                "error": "输入不是响应对象、断言规则格式错误或响应不满足条件",
                "limit": "该节点不重新发送请求；必须连接已有网络响应",
            },
            "network.graphql_request": {
                "usage": "发送 GraphQL Query 或 Mutation，配置 endpoint、query、变量和扩展字段。",
                "side_effect": "访问 GraphQL 服务，并可能执行服务端 Mutation",
                "expected": "返回 GraphQL data、errors、extensions 以及底层 HTTP 元数据。",
                "error": "endpoint/query 无效、服务端返回 GraphQL errors、网络权限或认证配置错误",
                "limit": "0.9.0 不支持 GraphQL Subscription；运行时会稳定拒绝该操作",
            },
            "network.sse_connect": {
                "usage": "以拉取式操作连接 SSE 端点，使用 `action` 选择 connect、receive 或 close。",
                "side_effect": "创建或消费会话级 SSE 连接",
                "expected": "connect 返回连接 ID，receive 返回事件，close 释放连接登记",
                "error": "端点不可访问、连接 ID 不存在、认证/TLS/代理失败或读取超时",
                "limit": "0.9.0 是主动拉取式基础操作，不是推送事件源，也不提供方案 C 的自动重连",
            },
            "network.websocket_connect": {
                "usage": "以拉取式操作连接 WebSocket，使用 `action` 选择 connect、send、receive、ping 或 close。",
                "side_effect": "创建或消费会话级 WebSocket 连接",
                "expected": "connect 返回连接 ID，send/receive/ping 按连接状态执行，close 释放连接登记",
                "error": "握手失败、连接 ID 不存在、消息不可序列化或连接读写失败",
                "limit": "0.9.0 不提供统一长连接状态机、自动重连或推送式图激活",
            },
            "network.batch_request": {
                "usage": "在一个网络节点中按输入请求列表执行有界并发批量请求。",
                "side_effect": "向多个网络目标发起请求并消耗网络运行时资源",
                "expected": "返回与请求顺序对应的结果列表；并发度受 `max_concurrency` 限制",
                "error": "请求列表结构错误、并发度无效、单项请求失败或网络策略拒绝目标",
                "limit": "节点内支持有界并发；图级调度仍保持逻辑并行、实际串行",
            },
        }
        return network_guidance.get(resource_key, {})
    if resource_key == "message.emit":
        return {
            "usage": "在运行或 Debug 流程中发布一条用户消息，用于进度、提示或错误分支说明。",
            "side_effect": "向 Runtime/Debug 诊断和消息面板发布事件",
            "expected": "消息出现在当前会话的消息/诊断视图中，随后继续控制流",
            "error": "消息为空、严重级别不受支持或当前会话已经终止",
        }
    if resource_key == "input.request":
        return {
            "usage": "暂停整个执行会话，等待 UI、CLI 或外部 API 提交多字段表单。",
            "side_effect": "暂停会话并创建会话级待输入请求",
            "expected": "提交成功后从 `out` 继续；超时先使用已配置的默认值，否则尝试从 `timed_out` 继续；两者都没有时节点失败",
            "error": "字段定义无效、必填字段缺失、类型校验失败、请求超时或会话被终止",
            "limit": "敏感字段不提供默认值；提交值只在当前会话内存中存在并在日志、事件和历史中脱敏",
        }
    if resource_key == "python.run":
        return {
            "usage": "需要自定义数据处理且内置节点不足时，在项目 Python 运行时中执行代码。",
            "side_effect": "启动项目运行时子进程，并可读取输入变量、返回可序列化结果",
            "expected": "子进程正常结束后返回结果和运行时来源信息。",
            "error": "项目 Python 运行时未启用、代码为空、导入被阻止或执行超时",
            "limit": "仅能返回 JSON 可序列化数据，导入和执行时间受安全策略限制",
        }
    if resource_key == "time.get_current_time":
        return {
            "usage": "在流程中生成当前时间文本，用于日志、文件名或业务字段。",
            "expected": "按配置格式生成时间字符串并写入指定变量。",
            "error": "时间格式字符串无效或输出变量名为空",
        }
    if resource_key in {"component.input", "component.output", "graph.call_subgraph", "call_blueprint"}:
        return {
            "usage": "定义自定义组件边界或调用已有子图；输入输出必须与组件 schema 一致。",
            "side_effect": "在父图与子图之间映射变量和控制上下文",
            "expected": "子图完成后按输出映射把结果返回调用方。",
            "error": "子图不存在、schema 不匹配或输入输出映射引用无效",
        }
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
