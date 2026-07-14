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
    assert "WeConduct 0.8.1" in config["site_description"]
    assert "Weave 0.5.0" in config["site_description"]
    assert config["site_url"] == "https://halcyonalcedo.github.io/WeConduct/"
    assert config["repo_url"] == "https://github.com/HalcyonAlcedo/WeConduct"
    assert config["repo_name"] == "HalcyonAlcedo/WeConduct"
    assert config["edit_uri"] == ""
    assert config["theme"]["features"] == [
        "navigation.tabs",
        "navigation.sections",
        "navigation.indexes",
        "navigation.prune",
        "navigation.top",
        "search.suggest",
        "search.highlight",
        "content.code.copy",
        "toc.follow",
    ]
    assert config["plugins"] == [{"search": {"lang": "zh"}}]
    assert config["extra_javascript"] == ["assets/javascripts/weconduct-graph.js"]
    assert config["extra_css"] == ["assets/stylesheets/weconduct-graph.css"]
    nav = config["nav"]
    assert [next(iter(item)) for item in nav] == [
        "首页", "WeConduct", "内置节点", "示例", "Weave", "故障排查", "参考"
    ]

    nav_targets = dict(collect_nav_targets(nav))
    assert nav_targets["首页"] == "index.md"
    assert nav_targets["总览"] == "weconduct/index.md"
    assert nav_targets["安装 0.8.1"] == "weconduct/getting-started/install.md"
    assert nav_targets["项目管理"] == "weconduct/guide/project-management.md"
    assert nav_targets["项目布局"] == "weconduct/guide/project-layout.md"
    assert nav_targets["图编辑器"] == "weconduct/guide/graph-editor.md"
    assert nav_targets["组件库"] == "weconduct/guide/component-library.md"
    assert nav_targets["节点配置"] == "weconduct/guide/node-configuration.md"
    assert nav_targets["子图与自定义组件"] == "weconduct/guide/subgraphs-and-custom-components.md"
    assert nav_targets["WebControl 转换"] == "weconduct/guide/webcontrol-conversion.md"
    assert nav_targets["资源与安全"] == "weconduct/concepts/resources-and-security.md"
    assert nav_targets["内置节点"] == "weconduct/components/index.md"
    assert nav_targets["示例"] == "weconduct/examples/index.md"
    assert nav_targets["Weave"] == "weave/index.md"
    assert nav_targets["故障排查"] == "weconduct/troubleshooting/index.md"
    assert nav_targets["参考"] == "weconduct/reference/embedded-graphs.md"

    docs_root = ROOT / "docs"
    for label, target in collect_nav_targets(nav):
        target_file, fragment = split_nav_target(target)
        target_path = docs_root / target_file
        assert target_path.exists(), f"{label} -> {target} 不存在"
        if target_file != "index.md":
            assert target_file.startswith(("weconduct/", "weave/")), (
                f"{label} -> {target} 未落在 weconduct/ 或 weave/ 下"
            )
        if fragment:
            anchors = collect_markdown_anchors(target_file)
            assert fragment in anchors, f"{label} -> {target} 缺少锚点 {fragment}"


def test_dedicated_landing_pages_front_matter_and_real_basics() -> None:
    expected_pages = {
        "docs/weconduct/guide/project-management.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
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
                "version": "0.8.1",
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
                "version": "0.8.1",
                "doc_id": "weconduct:guide:graph-editor",
            },
            "body_checks": [
                "Ctrl+Z",
                "Ctrl+Y",
                "复制节点",
                "粘贴节点",
                "元数据编辑",
                "graph_preferences",
            ],
        },
        "docs/weconduct/guide/component-library.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
                "doc_id": "weconduct:guide:component-library",
            },
            "body_checks": [
                "126",
                "120",
                "6",
                "component_library_visible",
                "compatibility_only",
            ],
        },
        "docs/weconduct/guide/node-configuration.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
                "doc_id": "weconduct:guide:node-configuration",
            },
            "body_checks": [
                "typed-value",
                "component-schema",
                "图稿版本冲突",
                "debugger",
                "component.input",
            ],
        },
        "docs/weconduct/guide/subgraphs-and-custom-components.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
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
                "version": "0.8.1",
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
                "version": "0.8.1",
                "doc_id": "weconduct:components:index",
            },
            "body_checks": ["126", "120", "6", "embedded-graphs.md", "聚合页", "详情页", "搜索"],
        },
        "docs/weconduct/examples/index.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
                "doc_id": "weconduct:examples:index",
            },
            "body_checks": ["graph-v1", "0.8.1", "smoke", "下载", "验收"],
        },
        "docs/weconduct/troubleshooting/index.md": {
            "front_matter": {
                "product": "weconduct",
                "version": "0.8.1",
                "doc_id": "weconduct:troubleshooting:index",
            },
            "body_checks": ["排查流程", "诊断", "校验", "页面加载"],
        },
    }

    for relative_path, page_contract in expected_pages.items():
        front_matter, body = parse_front_matter(relative_path)
        assert front_matter == page_contract["front_matter"]
        for needle in page_contract["body_checks"]:
            assert needle in body, f"{relative_path} 缺少关键信息 {needle!r}"


def test_docs_do_not_expose_internal_task_labels() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        text = strip_fenced_code_blocks(path.read_text(encoding="utf-8"))
        match = INTERNAL_TASK_RE.search(text)
        if match:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {match.group(0)}")

    assert not offenders, "发现用户可见内部任务引用:\n" + "\n".join(offenders)


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
    assert "WeConduct 0.8.1" in body
    assert "Weave 0.5.0" in body


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
        "Setup Python",
        "Install dependencies",
        "Run baseline tests",
        "Configure GitHub Pages",
        "Run page validator when available",
        "Run graph validator when available",
        "Build site",
        "Upload Pages artifact",
    ]
    assert build_steps[0]["uses"] == "actions/checkout@v4"
    assert build_steps[1]["uses"] == "actions/setup-python@v5"
    assert build_steps[2]["run"] == "python -m pip install -r requirements-dev.txt"
    assert build_steps[3]["run"] == "python -m pytest -q"
    assert build_steps[4]["uses"] == "actions/configure-pages@v5"
    assert build_steps[5]["shell"] == "pwsh"
    assert 'if (Test-Path "validate_pages.py")' in build_steps[5]["run"]
    assert "Pending validate_pages.py" in build_steps[5]["run"]
    assert build_steps[6]["shell"] == "pwsh"
    assert 'if (Test-Path "validate_graph_examples.py")' in build_steps[6]["run"]
    assert "Pending validate_graph_examples.py" in build_steps[6]["run"]
    assert build_steps[7]["run"] == "python -m mkdocs build --strict"
    assert build_steps[8]["uses"] == "actions/upload-pages-artifact@v4"
    assert build_steps[8]["with"] == {"path": "site"}

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
