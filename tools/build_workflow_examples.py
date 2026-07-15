from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "weconduct-0.8.1" / "components.json"
DOCS_ROOT = ROOT / "docs"
VERSION = "0.8.1"


EXAMPLES: tuple[dict[str, Any], ...] = (
    {
        "id": "browser-form-automation",
        "title": "浏览器表单自动化",
        "scenario": "打开网页，填写文本字段并提交表单。",
        "prerequisites": "启用浏览器执行器和远程网络权限；把示例 URL 与选择器替换为目标站点真实值。",
        "nodes": [
            ("flow.start", {}),
            ("browser.navigate", {"url": "https://example.com/form"}),
            ("browser.fill", {"selector": "input[name='query']", "value": "WeConduct"}),
            ("browser.click", {"selector": "button[type='submit']"}),
        ],
        "edges": [(0, "out", 1, "in"), (1, "out", 2, "in"), (2, "out", 3, "in")],
        "expected": "浏览器进入目标页面，字段值变为 `WeConduct`，随后触发表单提交。",
        "diagnosis": "优先检查 `allow_browser_executor`、网络权限、URL 和两个选择器；动态页面可在填写前增加条件等待。",
    },
    {
        "id": "browser-table-to-excel",
        "title": "网页表格导出 Excel",
        "scenario": "打开包含表格的页面，将表头和行数据提取到新的 Excel 工作簿。",
        "prerequisites": "启用浏览器执行器、远程网络、文件访问和允许的输出目录。",
        "nodes": [
            ("flow.start", {}),
            ("browser.navigate", {"url": "https://example.com/table"}),
            ("browser.extract_web_table_to_excel", {"selector": "table", "path": "output/table.xlsx", "sheet_name": "Data"}),
        ],
        "edges": [(0, "out", 1, "in"), (1, "out", 2, "in")],
        "expected": "`output/table.xlsx` 被创建，`Data` 工作表包含页面表头和数据行。",
        "diagnosis": "检查表格选择器、文件允许根和目标文件占用；该节点新建工作簿，不会追加既有文件。",
    },
    {
        "id": "browser-auth-session",
        "title": "浏览器认证会话准备",
        "scenario": "在导航前应用 Cookie 与 Local Storage，再检查登录态页面元素。",
        "prerequisites": "启用浏览器执行器、Cookie、浏览器存储和远程网络权限；示例凭据仅为占位。",
        "nodes": [
            ("flow.start", {}),
            ("session.apply_auth_session", {"cookies": [{"name": "session", "value": "replace-me", "domain": "example.com", "path": "/"}], "local_storage": {"token": "replace-me"}}),
            ("browser.navigate", {"url": "https://example.com/account"}),
            ("browser.exists", {"selector": "[data-user-menu]", "variable_name": "logged_in"}),
        ],
        "edges": [(0, "out", 1, "in"), (1, "out", 2, "in"), (2, "out", 3, "in")],
        "expected": "认证材料进入浏览器上下文，页面打开后把登录元素是否存在写入 `logged_in`。",
        "diagnosis": "检查 Cookie 的 domain/path/secure 属性、页面 origin、存储键和认证材料是否过期。",
    },
    {
        "id": "data-list-processing",
        "title": "列表整理与统计",
        "scenario": "创建列表、追加元素、排序，并统计最终长度。",
        "prerequisites": "不需要外部服务或高风险权限，可直接用于理解变量和列表节点。",
        "nodes": [
            ("flow.start", {}),
            ("data.create_list", {"variable_name": "numbers", "items": [3, 1, 2]}),
            ("data.list_append", {"variable_name": "numbers", "value": 4}),
            ("data.list_sort", {"variable_name": "numbers"}),
            ("data.list_length", {"variable_name": "numbers", "output_variable_name": "count"}),
        ],
        "edges": [(0, "out", 1, "in"), (1, "out", 2, "in"), (2, "out", 3, "in"), (3, "out", 4, "in")],
        "expected": "`numbers` 变为 `[1, 2, 3, 4]`，`count` 为 `4`。",
        "diagnosis": "检查 `numbers` 是否被其他节点覆盖为非列表值，以及变量名是否完全一致。",
    },
    {
        "id": "file-csv-transformation",
        "title": "CSV 读取与文本输出",
        "scenario": "读取项目内示例 CSV 表格，并把处理说明写入文本文件。",
        "prerequisites": "启用文件访问；下载项目已包含 `sample/input.csv`，输出目录必须位于允许根。",
        "nodes": [
            ("flow.start", {}),
            ("file.read_csv_table", {"path": "sample/input.csv", "encoding": "utf-8", "has_header": True, "variable_name": "rows"}),
            ("data.map", {"source": None, "variable_name": "csv_rows", "mode": "map"}),
            ("file.write_text_file", {"path": "output/summary.txt", "encoding": "utf-8", "content": "CSV 已读取，结果位于变量 rows。"}),
        ],
        "edges": [
            (0, "out", 1, "in"), (1, "out", 2, "in"), (2, "out", 3, "in"),
            (1, "out:rows", 2, "in:source", "data"),
            (2, "out:value", 3, "in:content", "data"),
        ],
        "expected": "CSV 行写入 `rows`，映射结果写入 `csv_rows`，并生成 `output/summary.txt`。",
        "diagnosis": "检查项目根、文件权限、UTF-8 编码和 `has_header` 是否与实际 CSV 一致。",
        "extra_files": {"sample/input.csv": "name,score\nAlice,90\nBob,85\n"},
    },
    {
        "id": "control-branch-and-loop",
        "title": "条件分支与循环",
        "scenario": "初始化计数器，通过条件分支进入循环，并在满足退出条件后读取结果。",
        "prerequisites": "不需要外部权限；编辑控制边时必须使用节点声明的 `true/false/loop/done/repeat` 端口。",
        "nodes": [
            ("flow.start", {}),
            ("data.set_variable", {"name": "counter", "value": 0}),
            ("control.if", {"expression": "counter < 3"}),
            ("data.increment_variable", {"variable_name": "counter", "step": 1}),
            ("control.while", {"expression": "counter < 3"}),
            ("data.get_variable", {"name": "counter"}),
        ],
        "edges": [
            (0, "out", 1, "in"), (1, "out", 2, "in"), (2, "true", 4, "in"),
            (2, "false", 5, "in"), (4, "loop", 3, "in"), (3, "out", 4, "repeat"),
            (4, "done", 5, "in"),
        ],
        "expected": "计数器按循环结构递增，完成后读取 `counter`。",
        "diagnosis": "若图校验失败，检查循环回边是否接到允许的重复入口，以及表达式是否返回布尔值。",
    },
    {
        "id": "parallel-retry-failover",
        "title": "并行、重试与故障切换",
        "scenario": "并行执行两个变量写入，汇合后进入重试和故障切换结构。",
        "prerequisites": "不需要外部权限；该示例用于讲解控制结构，实际业务需把 attempt/primary/fallback 分支替换为可判定动作。",
        "nodes": [
            ("flow.start", {}),
            ("control.parallel_fork", {}),
            ("data.set_variable", {"name": "left_done", "value": True}),
            ("data.set_variable", {"name": "right_done", "value": True}),
            ("control.join", {}),
            ("control.retry", {"max_attempts": 3, "success_expression": "left_done and right_done"}),
            ("control.failover", {"fallback_expression": "not left_done"}),
            ("data.set_variable", {"name": "route", "value": "primary"}),
            ("data.set_variable", {"name": "route", "value": "backup"}),
            ("data.set_variable", {"name": "route", "value": "failed"}),
        ],
        "edges": [
            (0, "out", 1, "in"), (1, "branch:left", 2, "in"), (1, "branch:right", 3, "in"),
            (2, "out", 4, "in:left"), (3, "out", 4, "in:right"), (4, "out", 5, "in"),
            (5, "attempt", 6, "in"), (5, "exhausted", 9, "in"), (6, "primary", 7, "in"),
            (6, "fallback:backup", 8, "in"), (6, "failed", 9, "in"),
        ],
        "expected": "左右分支汇合后进入重试；根据结果从 primary、backup 或 failed 路径写入 `route`。",
        "diagnosis": "检查 fork/join 的分支 key 是否一致、`max_attempts >= 1`，以及所有结构出口是否已连接。",
    },
    {
        "id": "http-and-python-processing",
        "title": "HTTP 与 Python 处理",
        "scenario": "请求 JSON 数据，再在项目 Python 运行时中进行自定义处理。",
        "prerequisites": "启用远程网络和 Python 执行；在项目设置启用并准备项目 Python 运行时。",
        "nodes": [
            ("flow.start", {}),
            ("http.request", {"method": "GET", "url": "https://example.com/data.json", "headers": {"Accept": "application/json"}, "timeout": 30, "body": None}),
            ("data.set_variable", {"name": "response_body", "value": None}),
            ("python.run", {"code": "result = {'processed': True, 'body': variables.get('response_body')}"}),
        ],
        "edges": [
            (0, "out", 1, "in"), (1, "out", 2, "in"), (2, "out", 3, "in"),
            (1, "out:body", 2, "in:value", "data"),
        ],
        "expected": "HTTP 节点返回响应摘要，Python 子进程返回可 JSON 序列化的 `result`。",
        "diagnosis": "检查 URL、远程网络权限、Python runtime 状态、导入阻止列表和执行超时。",
    },
    {
        "id": "custom-component",
        "title": "自定义组件边界",
        "scenario": "使用组件输入、内部变量处理和组件输出组织可复用子图。",
        "prerequisites": "下载项目包含一个自定义组件资源；从资源管理打开组件图查看输入和输出 schema。",
        "nodes": [
            ("flow.start", {}),
            ("component.input", {"name": "text", "value_type": "string", "required": True}),
            ("data.set_variable", {"name": "normalized", "value": "example"}),
            ("component.output", {"outputs": {"normalized": {"type": "string", "required": True}}}),
        ],
        "edges": [(0, "out", 2, "in")],
        "expected": "组件资源暴露 `text` 输入和 `normalized` 输出，主项目可在资源管理中继续编辑。",
        "diagnosis": "检查组件 schema、资源索引和父子图变量映射；组件边界节点只能用于自定义组件图。",
        "custom_resource": True,
    },
    {
        "id": "wcrun-package-workflow",
        "title": "`.wcrun` 打包工作流",
        "scenario": "准备一个无外部依赖的流程，用于演示保存、预检、构建、检查和加载 `.wcrun`。",
        "prerequisites": "先保存下载项目，再在 `.wcrun` 包管理中执行预检；选择用户有写权限的输出路径。",
        "nodes": [
            ("flow.start", {}),
            ("data.set_variables_batch", {"variables": {"package_demo": True, "version": "0.8.1"}}),
            ("data.get_variable", {"name": "package_demo"}),
        ],
        "edges": [(0, "out", 1, "in"), (1, "out", 2, "in")],
        "expected": "标准运行完成后可构建 `.wcrun`；加载包时图和项目设置只读。",
        "diagnosis": "预检只覆盖已保存图诊断和必需外部资源绑定；Python 与安全要求在检查、加载和运行就绪阶段确认。",
    },
)


def read_manifest() -> dict[str, dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {item["resource_key"]: item for item in payload}


def graph_compatibility() -> dict[str, Any]:
    return {
        "graph_data_version": "0.6.2",
        "built_with_app_version": VERSION,
        "minimum_loader_app_version": "0.5.2",
        "last_upgraded_by_app_version": VERSION,
        "upgrade_history": [],
    }


def build_graph(spec: dict[str, Any], manifest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for index, (resource_key, overrides) in enumerate(spec["nodes"]):
        component = manifest[resource_key]
        config = json.loads(json.dumps(component.get("node_config", {}), ensure_ascii=False))
        config.update(overrides)
        nodes.append(
            {
                "node_id": f"node-{index + 1}",
                "lowered_kind": component["lowered_kind"],
                "source_anchor_ref": f"docs:example:{spec['id']}:{index + 1}",
                "expansion_role": component["expansion_role"],
                "display_name": component["display_name_zh"],
                "node_kind": resource_key,
                "position": {"x": 60 + (index % 4) * 290, "y": 70 + (index // 4) * 210},
                "ports": component["ports"],
                "node_config": config,
            }
        )
    edges = []
    for index, edge in enumerate(spec["edges"]):
        source, source_port, target, target_port, *relation = edge
        edges.append({
            "edge_id": f"edge-{index + 1}",
            "relation_layer": relation[0] if relation else "control",
            "from_node_id": f"node-{source + 1}",
            "to_node_id": f"node-{target + 1}",
            "from_port_id": source_port,
            "to_port_id": target_port,
        })
    return {
        "graph_model_id": f"graph:docs:example:{spec['id']}",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "root_metadata": {"graph_compatibility": graph_compatibility()},
        "graph_effective_diagnostic_anchor_refs": [],
    }


def build_project_files(
    spec: dict[str, Any], graph: dict[str, Any], manifest: dict[str, dict[str, Any]]
) -> dict[str, bytes]:
    example_id = spec["id"]
    project_name = f"{example_id}.weconduct.json"
    storage_root = f"{example_id}.weconduct.data"
    saved_graph = graph
    if spec.get("custom_resource"):
        saved_graph = build_graph(
            {
                "id": "custom-component-main",
                "nodes": [
                    ("flow.start", {}),
                    ("data.set_variable", {"name": "component_example", "value": "打开资源管理查看文本规范化组件"}),
                ],
                "edges": [(0, "out", 1, "in")],
            },
            manifest,
        )
    used_keys = list(
        dict.fromkeys(
            node["node_kind"] for node in saved_graph["nodes"] if node.get("node_kind") in manifest
        )
    )
    builtin_refs = [
        {
            "resource_id": manifest[key]["resource_id"],
            "resource_key": key,
            "resource_type": "builtin_component",
            "origin": "builtin",
            "implementation_kind": manifest[key].get("implementation_kind") or "core_atomic",
            "compatibility_aliases": manifest[key].get("compatibility_aliases", []),
            "definition_version": "builtin-registry-v1",
        }
        for key in used_keys
    ]
    project_resource_refs: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    if spec.get("custom_resource"):
        resource_id = "custom_node_graph:docs-normalize-text"
        resource_key = "project.docs_normalize_text"
        relative_dir = f"{storage_root}/resources/custom_node_graph/docs-normalize-text"
        resource_graph = build_custom_resource_graph(manifest)
        resource_manifest = {
            "resource_manifest_schema_version": 1,
            "resource_id": resource_id,
            "resource_key": resource_key,
            "resource_type": "custom_node_graph",
            "origin": "project",
            "implementation_kind": "project_component",
            "display_name": "文本规范化",
            "display_name_i18n": {"zh-CN": "文本规范化"},
            "description": "Normalize input text in a reusable component.",
            "description_i18n": {"zh-CN": "在可复用组件中规范化输入文本。"},
            "compatibility_aliases": [],
            "input_schema": {"text": {"type": "string", "required": True}},
            "output_schema": {"normalized": {"type": "string", "required": True}},
            "graph_document_id": resource_id,
            "graph_document_save_revision": 1,
        }
        resources.append(
            {
                "resource_id": resource_id,
                "resource_key": resource_key,
                "resource_type": "custom_node_graph",
                "origin": "project",
                "implementation_kind": "project_component",
                "display_name": "文本规范化",
                "source_ref": relative_dir,
                "manifest_path": f"{relative_dir}/manifest.json",
                "graph_path": f"{relative_dir}/graph.json",
                "enabled_by_default": True,
                "compatibility_aliases": [],
            }
        )
        project_resource_refs.append({"resource_id": resource_id, "source_ref": relative_dir})
        files[f"{relative_dir}/manifest.json"] = json_bytes(resource_manifest)
        files[f"{relative_dir}/graph.json"] = json_bytes(resource_graph)

    project = {
        "project_file_schema_version": 2,
        "saved_at": "2026-07-15T00:00:00+00:00",
        "project": {
            "project_id": f"docs-{example_id}",
            "project_name": spec["title"],
            "project_schema_version": "project-v2",
            "project_status": "ready",
            "workspace_root": ".",
            "source_of_truth": "graph_document",
            "main_graph_document_id": saved_graph["graph_model_id"],
            "resource_registry_revision": 0,
            "main_graph_path": f"{storage_root}/graphs/workspace.graph.json",
            "project_resources_index_path": f"{storage_root}/resources/index.json",
            "resource_overrides_path": f"{storage_root}/resource-overrides.json",
        },
        "builtin_resource_refs": builtin_refs,
        "project_resource_refs": project_resource_refs,
        "editor_history": {"undo_stack": [], "redo_stack": []},
        "execution_history": {"runtime_runs": [], "debug_sessions": []},
        "graph_document_meta": {"save_revision": 1, "saved_at": "2026-07-15T00:00:00+00:00"},
    }
    files[project_name] = json_bytes(project)
    files[f"{storage_root}/graphs/workspace.graph.json"] = json_bytes(saved_graph)
    files[f"{storage_root}/resources/index.json"] = json_bytes(
        {"project_resources_schema_version": 1, "resources": resources}
    )
    files[f"{storage_root}/resource-overrides.json"] = json_bytes(
        {"resource_overrides_schema_version": 1, "resources": {}}
    )
    files["README.txt"] = (
        f"{spec['title']}\nWeConduct {VERSION}\n\n"
        f"解压后打开 {project_name}。\n"
    ).encode("utf-8")
    for relative_path, content in spec.get("extra_files", {}).items():
        files[relative_path] = content.encode("utf-8")
    return files


def build_custom_resource_graph(manifest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    spec = {
        "id": "custom-resource-normalize-text",
        "nodes": [
            ("component.input", {"name": "text", "value_type": "string", "required": True}),
            ("data.set_variable", {"name": "normalized", "value": "example"}),
            ("component.output", {"outputs": {"normalized": {"type": "string", "required": True}}}),
        ],
        "edges": [],
    }
    graph = build_graph(spec, manifest)
    graph["graph_model_id"] = "custom_node_graph:docs-normalize-text"
    return graph


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_archive(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 7, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])


def write_page(spec: dict[str, Any], graph: dict[str, Any], manifest: dict[str, dict[str, Any]]) -> None:
    page_path = DOCS_ROOT / "weconduct" / "examples" / f"{spec['id']}.md"
    responsibilities = []
    for resource_key, _ in spec["nodes"]:
        component = manifest[resource_key]
        responsibilities.append(
            f"- [{component['display_name_zh']}](../components/{component_link(resource_key)}.md) "
            f"(`{resource_key}`)：{component['description_zh']}"
        )
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        f"doc_id: weconduct:example:{spec['id']}", "---", "", f"# {spec['title']}", "",
        "## 场景", "", spec["scenario"], "", "## 前置条件", "", spec["prerequisites"], "",
        "## 流程图", "",
        f"<weconduct-graph src=\"../../assets/graphs/examples/{spec['id']}.json\" title=\"{spec['title']}\">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>",
        "", "## 节点职责", "", *responsibilities, "", "## 配置步骤", "",
        "1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。",
        "2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。",
        "3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。",
        "4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。",
        "", "## 预期结果", "", spec["expected"], "", "## 失败诊断", "", spec["diagnosis"], "",
        "保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。",
        "", "## 下载项目", "",
        f"- [下载 {spec['id']}.zip](../../downloads/weconduct/0.8.1/{spec['id']}.zip)",
        f"- [查看原始 graph-v1 JSON](../../assets/graphs/examples/{spec['id']}.json)",
        "", "下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。",
    ]
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def component_link(resource_key: str) -> str:
    catalog = json.loads(
        (ROOT / "data" / "weconduct-0.8.1" / "component-groups.json").read_text(encoding="utf-8")
    )
    page_path = catalog["assignments"][resource_key]["page_path"]
    return page_path.removeprefix("docs/weconduct/components/").removesuffix(".md")


def write_index() -> None:
    lines = [
        "---", "product: weconduct", f"version: {VERSION}",
        "doc_id: weconduct:examples:index", "---", "", "# 可下载示例", "",
        "以下示例同时提供说明页、可交互节点图和目录项目 ZIP。所有图固定使用 `graph-v1` 和 WeConduct 0.8.1 节点契约。",
        "", "## 示例目录", "",
    ]
    for spec in EXAMPLES:
        lines.append(
            f"- [{spec['title']}]({spec['id']}.md)：{spec['scenario']} "
            f"[下载 ZIP](../../downloads/weconduct/0.8.1/{spec['id']}.zip)"
        )
    lines.extend(
        [
            "", "## 使用边界", "",
            "数据列表和 `.wcrun` 准备示例不依赖外部服务；浏览器、HTTP、文件、Python 示例需要对应权限或运行环境。",
            "示例 URL、选择器和凭据均为占位值。不要把测试凭据写入项目或提交到版本库。",
        ]
    )
    path = DOCS_ROOT / "weconduct" / "examples" / "index.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    manifest = read_manifest()
    graph_root = DOCS_ROOT / "assets" / "graphs" / "examples"
    download_root = DOCS_ROOT / "downloads" / "weconduct" / VERSION
    graph_root.mkdir(parents=True, exist_ok=True)
    for spec in EXAMPLES:
        graph = build_graph(spec, manifest)
        (graph_root / f"{spec['id']}.json").write_bytes(json_bytes(graph))
        write_page(spec, graph, manifest)
        write_archive(
            download_root / f"{spec['id']}.zip",
            build_project_files(spec, graph, manifest),
        )
    write_index()
    print(f"examples={len(EXAMPLES)} graphs={len(EXAMPLES)} downloads={len(EXAMPLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
