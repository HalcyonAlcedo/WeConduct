from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "weconduct-0.8.1" / "components.json"
DEFAULT_GROUPS = ROOT / "data" / "weconduct-0.8.1" / "component-groups.json"
DEFAULT_DOCS_ROOT = ROOT / "docs"
DEFAULT_GRAPHS_ROOT = DEFAULT_DOCS_ROOT / "assets" / "graphs" / "components"
VERSION = "0.8.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--groups", default=str(DEFAULT_GROUPS))
    parser.add_argument("--docs-root", default=str(DEFAULT_DOCS_ROOT))
    parser.add_argument("--graphs-root", default=str(DEFAULT_GRAPHS_ROOT))
    parser.add_argument("--family")
    parser.add_argument("--groups-only", action="store_true")
    parser.add_argument("--details", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
        write_global_index(docs_root, groups, keys_by_group)
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
        "graph_data_version": "0.6.2",
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


def write_global_index(docs_root: Path, groups: list[dict[str, Any]], keys_by_group: dict[str, list[str]]) -> None:
    path = docs_root / "weconduct" / "components" / "index.md"
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        "doc_id: weconduct:components:index", "---", "", "# 内置节点参考", "",
        "WeConduct 0.8.1 包含 126 个内置节点：120 个在组件库可见，6 个仅用于兼容或内部图加载。",
        "", "可以按中文名、英文名或资源键搜索。聚合页用于比较同类节点和常见组合；详情页提供完整端口、配置、权限、诊断和示例。",
        "", "## 分类", "",
    ]
    for group in groups:
        group_page = docs_path(docs_root, group["index_path"])
        lines.append(
            f"- [{group['title_zh']}]({relative_link(path, group_page)})："
            f"{group['description_zh']}（{len(keys_by_group[group['group_id']])} 个节点）"
        )
    lines.extend([
        "", "## 阅读方式", "",
        "先在聚合页选择节点，再进入详情页核对参数。兼容与内部节点不会出现在普通组件库中，不建议用于新流程。",
        "", "图示使用方法见[内嵌节点图](../reference/embedded-graphs.md)。",
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
        "## 如何选择", "",
        "| 节点 | 资源键 | 主要用途 |", "|---|---|---|",
    ]
    for key in keys:
        item = manifest[key]
        detail_path = docs_path(docs_root, assignments[key]["page_path"])
        lines.append(
            f"| [{item['display_name_zh']}]({relative_link(path, detail_path)}) | `{key}` | {item['description_zh']} |"
        )
    lines.extend(["", "## 常见组合", ""])
    if len(shown) > 1:
        names = " → ".join(manifest[key]["display_name_zh"] for key in shown[:4])
        lines.append(f"可从 `{names}` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。")
    else:
        lines.append("本组只有一个节点，通常与流程入口、变量节点和相邻能力域组合使用。")
    lines.extend([
        "", "## 组合图", "",
        f"<weconduct-graph src=\"{relative_link(path, graph_path)}\" title=\"{group['title_zh']}节点概览\">图示加载失败时，可使用下方节点列表。</weconduct-graph>",
        "", "该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。",
        "", "## 节点列表", "",
    ])
    for key in keys:
        item = manifest[key]
        detail_path = docs_path(docs_root, assignments[key]["page_path"])
        visibility = "兼容/内部" if item["compatibility_only"] else "组件库可见"
        lines.append(f"- [{item['display_name_zh']}]({relative_link(path, detail_path)}) (`{key}`)：{visibility}。")
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
        f"资源键：`{component['resource_key']}`",
        f"英文名：{component['display_name']}", "",
        "## 功能说明", "", component["description_zh"], "",
        f"该节点属于“{group['title_zh']}”。实现类型为 `{component.get('implementation_kind') or '未声明'}`，运行展开角色为 `{component['expansion_role']}`。",
        "", "## 适用场景", "", usage_text(component), "",
        "## 前置条件与权限", "", permission_text(component), "",
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
        lines.append("该节点没有额外参数；行为由输入、运行上下文或固定语义决定。")
    lines.extend([
        "", "## 输入、输出与副作用", "",
        io_text(component, input_ports, output_ports), "",
        "## 使用示例", "",
        f"<weconduct-graph src=\"{relative_link(path, graph_path)}\" title=\"{component['display_name_zh']}配置示例\">图示加载失败时，可阅读下方配置。</weconduct-graph>",
        "", "示例配置：", "", "```json", json.dumps(config, ensure_ascii=False, indent=2), "```", "",
        "将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。",
        "", "## 预期结果", "", expected_result_text(component, output_ports), "",
        "## 常见错误", "", common_errors_text(component), "",
        "## 限制与注意事项", "", limitation_text(component), "",
        "## 相关节点", "",
        f"- 返回[{group['title_zh']}]({relative_link(path, group_page)})聚合页。",
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
    if lower in {"url", "base_url"} or lower.endswith("_url"):
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
        return "用于浏览器自动化流程中，在页面或浏览器上下文已经就绪后完成该动作。"
    if key.startswith("data."):
        return "用于整理运行时数据、变量或列表，并把结果交给后续节点。"
    if key.startswith("control."):
        return "用于改变控制流、循环、并行或失败处理结构。"
    if key.startswith("excel."):
        return "用于读取或修改 Excel 工作簿中的结构化数据。"
    if key.startswith("file."):
        return "用于项目允许路径内的文本或 CSV 文件处理。"
    return f"在需要“{component['display_name_zh']}”能力的流程中使用。"


def permission_text(component: dict[str, Any]) -> str:
    key = component["resource_key"]
    permissions: list[str] = []
    if key.startswith(("file.", "excel.")):
        permissions.append("启用文件访问，并确保路径位于允许根内")
    if key == "http.request":
        permissions.append("按目标地址启用本地或远程网络访问")
    if key == "python.run":
        permissions.append("启用 Python 执行，并准备项目 Python 运行时")
    if "screenshot" in key:
        permissions.append("启用浏览器截图和文件访问")
    if "download" in key:
        permissions.append("启用浏览器下载和文件访问")
    if "upload" in key:
        permissions.append("启用浏览器上传和文件访问")
    if "cookie" in key:
        permissions.append("启用 Cookie 操作")
    if "storage" in key:
        permissions.append("启用浏览器存储操作")
    if key in {"browser.inject_js", "browser.run_js"} or "script" in key or "javascript" in key:
        permissions.append("按节点行为启用 JavaScript 注入或求值")
    if key.startswith("browser."):
        permissions.append("启用浏览器执行器，并确保存在可用页面目标")
    if key == "browser.download_file":
        permissions.append("按 URL 启用本地或远程网络访问")
    if not permissions:
        return "不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。"
    return "；".join(dict.fromkeys(permissions)) + "。"


def io_text(component: dict[str, Any], inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> str:
    input_names = "、".join(f"`{item['port_id']}`" for item in inputs) or "无显式输入端口"
    output_names = "、".join(f"`{item['port_id']}`" for item in outputs) or "无显式输出端口"
    key = component["resource_key"]
    guidance = domain_guidance(key)
    side_effect = guidance.get("side_effect", "主要更新运行时数据")
    if key.startswith("browser."):
        side_effect = guidance.get("side_effect", "可能读取或改变页面、浏览器状态、网络记录或本地文件")
    elif key.startswith(("file.", "excel.")):
        side_effect = "可能读取或写入文件"
    elif key.startswith("control."):
        side_effect = "改变后续控制路径"
    return f"输入：{input_names}。输出：{output_names}。副作用：{side_effect}。"


def expected_result_text(component: dict[str, Any], outputs: list[dict[str, Any]]) -> str:
    guidance = domain_guidance(component["resource_key"])
    if guidance.get("expected"):
        return guidance["expected"]
    data_outputs = [item for item in outputs if item["relation_layer"] == "data"]
    if data_outputs:
        names = "、".join(f"`{item['port_id']}`" for item in data_outputs)
        return f"节点成功后返回 `status = succeeded`，并可从 {names} 或节点输出字段取得结果。"
    return "节点成功后返回 `status = succeeded`，控制流从声明的控制输出继续；无数据输出时通过会话事件和节点结果确认执行。"


def common_errors_text(component: dict[str, Any]) -> str:
    required = [key for key, meta in merged_parameters(component).items() if meta.get("required")]
    messages = []
    if required:
        messages.append("缺少必填参数：" + "、".join(f"`{key}`" for key in required))
    messages.extend(["端口不存在或关系层不匹配", "输入类型与参数要求不一致"])
    if component["resource_key"].startswith(("browser.", "file.", "excel.", "http.", "python.")):
        messages.append("运行环境、资源路径或安全权限未满足")
    extra = domain_guidance(component["resource_key"]).get("error")
    if extra:
        messages.append(extra)
    return "；".join(messages) + "。诊断应保留节点 ID、资源键和原始错误信息。"


def limitation_text(component: dict[str, Any]) -> str:
    notes = []
    if component["compatibility_only"]:
        notes.append("该节点仅用于兼容或内部图加载，不在普通组件库显示，不建议用于新流程")
    if not component["component_library_visible"]:
        notes.append("不能从普通组件库直接添加")
    if component["resource_key"].startswith("browser."):
        notes.append("页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定")
    extra = domain_guidance(component["resource_key"]).get("limit")
    if extra:
        notes.append(extra)
    notes.append("示例图只展示节点配置；完整流程还需入口、控制边和业务输入")
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
    if resource_key.startswith("file."):
        return {
            "usage": "在允许文件根中读取或写入文本、CSV 数据，并显式选择编码和表头规则。",
            "side_effect": "读取目标文件；写入节点会创建或覆盖文件内容",
            "expected": "读取结果写入指定变量，或文件写入完成后返回保存信息。",
            "error": "路径越界、编码不匹配、CSV 行列越界或文件不可访问",
            "limit": "CSV 行列索引和 `has_header` 会共同影响实际定位",
        }
    if resource_key == "http.request":
        return {
            "usage": "向明确的 HTTP URL 发送请求，配置方法、请求头、正文和超时。",
            "side_effect": "访问本地或远程网络目标，并可能对服务端产生写操作",
            "expected": "请求完成后返回状态码、响应头和解码后的响应内容。",
            "error": "URL 无效、网络权限不足、连接超时或响应解码失败",
            "limit": "本地和远程目标分别受网络安全权限约束",
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
