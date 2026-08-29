from pathlib import Path
import json
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def read_yaml(relative_path: str, *, loader: type[yaml.Loader]) -> object:
    return yaml.load(read_text(relative_path), Loader=loader)


def parse_front_matter(relative_path: str) -> tuple[dict[str, object], str]:
    content = read_text(relative_path)
    parts = content.split("---", 2)
    assert len(parts) == 3, "front matter 分隔符格式不正确"
    front_matter = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return front_matter, body


def read_json(relative_path: str) -> object:
    return json.loads(read_text(relative_path))


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*(?:\{\s*#([A-Za-z0-9_-]+)\s*\})?\s*$")
INTERNAL_TASK_RE = re.compile(r"Task\s*\d+", re.IGNORECASE)


def split_nav_target(target: str) -> tuple[str, str | None]:
    path, sep, fragment = target.partition("#")
    return path, fragment if sep else None


def collect_markdown_anchors(relative_path: str) -> set[str]:
    anchors: set[str] = set()
    for line in read_text(f"docs/{relative_path}").splitlines():
        match = HEADING_RE.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        explicit_anchor = match.group(3)
        if explicit_anchor:
            anchors.add(explicit_anchor)
            continue
        generated = title.lower().replace("`", "")
        generated = re.sub(r"[^\w\s-]", "", generated)
        generated = re.sub(r"\s+", "-", generated).strip("-")
        if generated:
            anchors.add(generated)
    return anchors


def strip_fenced_code_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def collect_nav_targets(items: list[object]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for item in items:
        assert isinstance(item, dict) and len(item) == 1
        [(label, value)] = item.items()
        if isinstance(value, str):
            targets.append((label, value))
        else:
            assert isinstance(value, list), f"{label} 的导航值必须是路径或列表"
            targets.extend(collect_nav_targets(value))
    return targets


def test_mkdocs_metadata_and_assets_baseline() -> None:
    config = read_yaml("mkdocs.yml", loader=yaml.SafeLoader)

    assert config["site_name"] == "WeConduct 文档"
    assert "WeConduct 0.9.1" in config["site_description"]
    assert "Weave 0.5.0" in config["site_description"]
    assert config["site_url"] == "https://halcyonalcedo.github.io/WeConduct/"
    assert config["repo_url"] == "https://github.com/HalcyonAlcedo/WeConduct"
    assert config["repo_name"] == "HalcyonAlcedo/WeConduct"
    assert config["edit_uri"] == ""
    assert config["theme"]["features"] == [
        "navigation.tabs",
        "navigation.sections",
        "navigation.indexes",
        "navigation.top",
        "navigation.instant",
        "navigation.tracking",
        "search.suggest",
        "search.highlight",
        "content.code.copy",
        "content.code.annotate",
        "toc.follow",
        "navigation.footer",
    ]
    assert config["plugins"] == [{"search": {"lang": "zh"}}]
    assert config["not_in_nav"] == "weconduct/components/**/*.md\n"
    assert config["extra_javascript"] == ["assets/graph-runtime/weconduct-graph.js"]
    assert all("mermaid" not in js.lower() for js in config["extra_javascript"])
    assert config["extra_css"] == [
        "assets/graph-runtime/weconduct-graph.css",
        "assets/stylesheets/extra.css",
    ]
    nav = config["nav"]
    assert [next(iter(item)) for item in nav] == [
        "首页", "WeConduct", "内置节点", "示例", "Weave", "故障排查", "参考"
    ]

    nav_targets = dict(collect_nav_targets(nav))
    assert nav_targets["首页"] == "index.md"
    assert nav_targets["总览"] == "weconduct/index.md"
    assert nav_targets["安装 0.9.1"] == "weconduct/getting-started/install.md"
    assert nav_targets["项目管理"] == "weconduct/guide/project-management.md"
    assert nav_targets["项目布局"] == "weconduct/guide/project-layout.md"
    assert nav_targets["图编辑器"] == "weconduct/guide/graph-editor.md"
    assert nav_targets["组件库"] == "weconduct/guide/component-library.md"
    assert nav_targets["节点配置"] == "weconduct/guide/node-configuration.md"
    assert nav_targets["子图与自定义组件"] == "weconduct/guide/subgraphs-and-custom-components.md"
    assert nav_targets["WebControl 转换"] == "weconduct/guide/webcontrol-conversion.md"
    assert nav_targets["标准运行"] == "weconduct/guide/runtime.md"
    assert nav_targets["终止运行"] == "weconduct/guide/runtime-abort.md"
    assert nav_targets["执行历史"] == "weconduct/guide/execution-history.md"
    assert nav_targets["启动 Debug"] == "weconduct/guide/debug-start.md"
    assert nav_targets["Debug 控制与步进"] == "weconduct/guide/debug-controls.md"
    assert nav_targets["断点与记录帧"] == "weconduct/guide/breakpoints-and-record-frames.md"
    assert nav_targets["Debug 变量"] == "weconduct/guide/debug-variables.md"
    assert nav_targets["Debug 快照"] == "weconduct/guide/debug-snapshots.md"
    assert nav_targets["程序设置"] == "weconduct/guide/program-settings.md"
    assert nav_targets["项目设置"] == "weconduct/guide/project-settings.md"
    assert nav_targets["Python 运行时"] == "weconduct/guide/python-runtime.md"
    assert nav_targets["资源管理"] == "weconduct/guide/resource-management.md"
    assert nav_targets["构建 .wcrun"] == "weconduct/guide/wcrun-packaging.md"
    assert nav_targets["加载 .wcrun"] == "weconduct/guide/wcrun-loading.md"
    assert nav_targets["安全权限"] == "weconduct/reference/security-permissions.md"
    assert nav_targets["资源与安全"] == "weconduct/concepts/resources-and-security.md"
    assert nav_targets["节点总览"] == "weconduct/components/index.md"
    assert nav_targets["示例总览"] == "weconduct/examples/index.md"
    assert nav_targets["Weave 总览"] == "weave/index.md"
    assert nav_targets["排障总览"] == "weconduct/troubleshooting/index.md"
    assert nav_targets["内嵌节点图"] == "weconduct/reference/embedded-graphs.md"

    group_catalog = read_json("data/weconduct-0.9.1/component-groups.json")
    nav_target_values = set(nav_targets.values())
    for group in group_catalog["groups"]:
        expected_path = group["index_path"].removeprefix("docs/")
        assert expected_path in nav_target_values, f"聚合页未进入导航: {expected_path}"

    docs_root = ROOT / "docs"
    for label, target in collect_nav_targets(nav):
        target_file, fragment = split_nav_target(target)
        target_path = docs_root / target_file
        assert target_path.exists(), f"{label} -> {target} 不存在"
        if target_file != "index.md":
            assert target_file.startswith(("weconduct/", "weave/", "reference/")), (
                f"{label} -> {target} 未落在产品或站点参考目录下"
            )
        if fragment:
            anchors = collect_markdown_anchors(target_file)
            assert fragment in anchors, f"{label} -> {target} 缺少锚点 {fragment}"


def test_dedicated_landing_pages_front_matter_and_real_basics() -> None:
    expected_pages = {
        "docs/weconduct/guide/program-settings.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:program-settings"},
            "body_checks": ["default_window_size", "allow_file_access", "variable_apply_mode", "restart_required"],
        },
        "docs/weconduct/guide/project-settings.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:project-settings"},
            "body_checks": ["history_retention_limit", "default_output_name", "runtime_enabled", ".wcrun"],
        },
        "docs/weconduct/guide/python-runtime.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:python-runtime"},
            "body_checks": ["bundled", "requirements_txt", "wheelhouse_rebuild", "健康检查", "重建", "清理", "导出"],
        },
        "docs/weconduct/guide/resource-management.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:resource-management"},
            "body_checks": ["嵌入资源", "外部资源", "custom_node_graph", "导入", "导出"],
        },
        "docs/weconduct/guide/wcrun-packaging.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:wcrun-packaging"},
            "body_checks": ["saved_project_only", "预检", "package_embed_mode", "校验和"],
        },
        "docs/weconduct/guide/wcrun-loading.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:wcrun-loading"},
            "body_checks": ["检查", "加载", "卸载", "外部绑定", "一键修改并放行权限"],
        },
        "docs/weconduct/reference/security-permissions.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:reference:security-permissions"},
            "body_checks": ["allow_file_access", "restricted", "Documents", "Downloads", "一键放行"],
        },
        "docs/weconduct/guide/runtime.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:runtime"},
            "body_checks": ["自动准备", "completed", "succeeded", "failed", "aborted"],
        },
        "docs/weconduct/guide/runtime-abort.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:runtime-abort"},
            "body_checks": ["立即提交", "aborting", "aborted", "cancelled"],
        },
        "docs/weconduct/guide/execution-history.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:execution-history"},
            "body_checks": ["session_id", "incomplete", "只读"],
        },
        "docs/weconduct/guide/debug-start.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:debug-start"},
            "body_checks": ["preparing", "running", "paused", "stepping"],
        },
        "docs/weconduct/guide/debug-controls.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:debug-controls"},
            "body_checks": ["继续", "暂停", "单步跳过", "单步进入", "单步跳出", "can_step_out"],
        },
        "docs/weconduct/guide/breakpoints-and-record-frames.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:breakpoints-record-frames"},
            "body_checks": ["breakpoint.hit", "record_frame.hit", "frame_identity", "临时断点"],
        },
        "docs/weconduct/guide/debug-variables.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:debug-variables"},
            "body_checks": ["立即提交", "暂存编辑", "历史快照只读", "Ctrl+Enter"],
        },
        "docs/weconduct/guide/debug-snapshots.md": {
            "front_matter": {"product": "weconduct", "version": "0.9.1", "doc_id": "weconduct:guide:debug-snapshots"},
            "body_checks": ["manual_pause", "frame_identity", "变量快照", "只读"],
        },
        "docs/weconduct/guide/project-management.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:project-management",
            },
            "body_checks": [
                ".weconduct.json",
                ".wcrun",
                "workspace-state.json",
                "最近项目",
                "只读",
            ],
        },
        "docs/weconduct/guide/project-layout.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:project-layout",
            },
            "body_checks": [
                "workspace.graph.json",
                "resources/index.json",
                "resource-overrides.json",
                "project-settings.json",
                "project_resources_index_path",
            ],
        },
        "docs/weconduct/guide/graph-editor.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:graph-editor",
            },
            "body_checks": [
                "Ctrl+Z",
                "Ctrl+Y",
                "Ctrl+C",
                "Ctrl+V",
                "复制节点",
                "粘贴节点",
                "元数据编辑",
                "graph_preferences",
            ],
        },
        "docs/weconduct/guide/component-library.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:component-library",
            },
            "body_checks": [
                "135",
                "129",
                "6",
                "component_library_visible",
                "compatibility_only",
            ],
        },
        "docs/weconduct/guide/node-configuration.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:node-configuration",
            },
            "body_checks": [
                "元数据编辑",
                "类型化值",
                "版本冲突",
                "Debug",
                "保存冲突",
            ],
        },
        "docs/weconduct/guide/subgraphs-and-custom-components.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:subgraphs-and-custom-components",
            },
            "body_checks": [
                "component.input",
                "component.output",
                "share_parent_variables",
                "graph.call_subgraph",
                "schema",
            ],
        },
        "docs/weconduct/guide/webcontrol-conversion.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:guide:webcontrol-conversion",
            },
            "body_checks": [
                "source_path",
                "blueprint_paths",
                "conversion-report.json",
                "legacy_webcontrol_step",
                "不支持",
            ],
        },
        "docs/weconduct/components/index.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:components:index",
            },
            "body_checks": ["135", "129", "6", "embedded-graphs.md", "搜索"],
        },
        "docs/weconduct/examples/index.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:examples:index",
            },
            "body_checks": ["0.9.1", "ZIP", "占位值"],
        },
        "docs/weconduct/troubleshooting/index.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.9.1",
                "doc_id": "weconduct:troubleshooting:index",
            },
            "body_checks": ["诊断", "校验"],
        },
    }

    for relative_path, page_contract in expected_pages.items():
        front_matter, body = parse_front_matter(relative_path)
        assert front_matter == page_contract["front_matter"]
        for needle in page_contract["body_checks"]:
            assert needle in body, f"{relative_path} 缺少关键信息 {needle!r}"


def test_runtime_and_configuration_guides_match_081_ui_contracts() -> None:
    execution_history = Path("docs/weconduct/guide/execution-history.md").read_text(encoding="utf-8")
    assert "**任务执行** 面板" in execution_history
    assert "**输出 → 历史** 显示的是编译历史" in execution_history
    assert "不是完整节点事件、诊断或变量快照归档" in execution_history

    project_settings = Path("docs/weconduct/guide/project-settings.md").read_text(encoding="utf-8")
    assert "<项目文件名>.data/project-settings.json" in project_settings
    assert "项目名称保存后立即生效" in project_settings
    assert "默认输出文件名" in project_settings

    python_runtime = Path("docs/weconduct/guide/python-runtime.md").read_text(encoding="utf-8")
    assert "| `runtime_enabled` | `false` |" in python_runtime
    assert "| `package_embed_mode` | `wheelhouse_rebuild` |" in python_runtime
    assert "`disabled` 是未启用时的状态摘要" in python_runtime

    resources = Path("docs/weconduct/guide/resource-management.md").read_text(encoding="utf-8")
    assert "当前支持的操作" in resources
    assert "最多 256 个文件" in resources
    assert "64 MiB" in resources
    assert "发现冲突时中止导入" in resources

    subgraphs = Path("docs/weconduct/guide/subgraphs-and-custom-components.md").read_text(encoding="utf-8")
    assert "宿主版本至少为 0.9.1" in subgraphs
    assert "图数据格式仍沿用 0.9.0" in subgraphs

    external_api = Path("docs/weconduct/guide/external-api.md").read_text(encoding="utf-8")
    assert "/api/ext/v1/debug/{session_id}/projection" in external_api
    assert "/api/ext/v1/debug/{session_id}/live-projection" not in external_api
    assert "/api/ext/v1/project/resource-audit" in external_api
    assert ".wcsubgraph" in external_api

    packaging = Path("docs/weconduct/guide/wcrun-packaging.md").read_text(encoding="utf-8")
    assert "已保存图的校验诊断" in packaging
    assert "必需外部资源是否缺少绑定" in packaging

    loading = Path("docs/weconduct/guide/wcrun-loading.md").read_text(encoding="utf-8")
    assert "实际路径字符串" in loading
    assert "仅支持 `initial_variable`" in loading

    permissions = Path("docs/weconduct/reference/security-permissions.md").read_text(encoding="utf-8")
    assert "用户 `Downloads` 和 `custom_roots`" in permissions
    assert "不会自动把用户 `Documents` 加入允许根" in permissions


def test_docs_do_not_expose_internal_task_labels() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if path.relative_to(ROOT / "docs").as_posix().startswith("superpowers/"):
            continue
        text = strip_fenced_code_blocks(path.read_text(encoding="utf-8"))
        match = INTERNAL_TASK_RE.search(text)
        if match:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {match.group(0)}")

    assert not offenders, "发现用户可见内部任务引用:\n" + "\n".join(offenders)


def test_markdown_source_has_clean_line_endings() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        content = path.read_bytes()
        relative_path = path.relative_to(ROOT).as_posix()
        if not content.endswith(b"\n") or content.endswith(b"\n\n"):
            offenders.append(f"{relative_path}: EOF 换行数量不正确")
        text = content.decode("utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip():
                offenders.append(f"{relative_path}:{line_number}: 存在尾随空格")

    assert not offenders, "Markdown 源文件格式不干净:\n" + "\n".join(offenders)


def test_weave_product_metadata_baseline() -> None:
    payload = read_json("data/weave-0.5.0/product.json")

    assert payload["product"] == "weave"
    assert payload["version"] == "0.5.0"

    distribution = payload["distribution"]
    assert distribution["os"] == "windows"
    assert distribution["arch"] == "x64"
    assert distribution["package_type"] == "single-file-portable"
    assert distribution["update_mode"] == "manual-exe-replacement"
    assert distribution["entry_executable"] == "Weave.exe"
    assert distribution["sibling_data_dirs"] == [".weave", "plugins"]


def test_index_front_matter_and_versions() -> None:
    front_matter, body = parse_front_matter("docs/index.md")

    assert front_matter == {
        "product": "site",
        "version": "latest",
        "doc_id": "site:index",
    }
    assert "WeConduct" in body
    assert "Weave" in body


def test_workflow_uses_official_pages_actions_on_docs_branch() -> None:
    workflow = read_yaml(".github/workflows/deploy-docs.yml", loader=yaml.BaseLoader)

    assert workflow["on"]["push"]["branches"] == ["docs"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert workflow["concurrency"] == {
        "group": "pages",
        "cancel-in-progress": "true",
    }

    assert list(workflow["jobs"]) == ["build", "deploy"]
    build_job = workflow["jobs"]["build"]
    deploy_job = workflow["jobs"]["deploy"]

    assert build_job["runs-on"] == "ubuntu-latest"
    build_steps = build_job["steps"]
    assert [step["name"] for step in build_steps] == [
        "Checkout docs branch",
        "Setup Node.js",
        "Install graph runtime dependencies",
        "Test graph runtime",
        "Build graph runtime",
        "Setup Python",
        "Install dependencies",
        "Run baseline tests",
        "Validate documentation pages",
        "Validate graph examples",
        "Configure GitHub Pages",
        "Build site",
        "Upload Pages artifact",
    ]
    assert build_steps[0]["uses"] == "actions/checkout@v4"
    assert build_steps[1]["uses"] == "actions/setup-node@v4"
    assert build_steps[1]["with"] == {"node-version": "24", "cache": "npm"}
    assert build_steps[2]["run"] == "npm ci"
    assert build_steps[3]["run"] == "npm run test:graph"
    assert build_steps[4]["run"] == "npm run build:graph"
    assert build_steps[5]["uses"] == "actions/setup-python@v5"
    assert build_steps[6]["run"] == "python -m pip install -r requirements-dev.txt"
    assert build_steps[7]["run"] == "python -m pytest -q"
    assert build_steps[8]["run"] == "python tools/validate_pages.py"
    assert build_steps[9]["run"] == "python tools/validate_graph_examples.py"
    assert build_steps[10]["uses"] == "actions/configure-pages@v5"
    assert build_steps[11]["run"] == "python -m mkdocs build --strict"
    assert build_steps[12]["uses"] == "actions/upload-pages-artifact@v4"
    assert build_steps[12]["with"] == {"path": "site"}

    assert deploy_job["runs-on"] == "ubuntu-latest"
    assert deploy_job["needs"] == "build"
    assert deploy_job["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }
    deploy_steps = deploy_job["steps"]
    assert len(deploy_steps) == 1
    assert deploy_steps[0]["name"] == "Deploy to GitHub Pages"
    assert deploy_steps[0]["id"] == "deployment"
    assert deploy_steps[0]["uses"] == "actions/deploy-pages@v4"
