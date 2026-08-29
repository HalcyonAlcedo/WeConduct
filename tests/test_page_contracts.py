import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "tools" / "validate_pages.py"
MANIFEST_PATH = ROOT / "data" / "weconduct-0.9.1" / "components.json"
GROUPS_PATH = ROOT / "data" / "weconduct-0.9.1" / "component-groups.json"
REQUIRED_SECTIONS = [
    "功能说明",
    "什么时候用",
    "需要什么权限",
    "端口说明",
    "配置参数",
    "输入、输出与副作用",
    "使用示例",
    "预期结果",
    "常见问题",
    "注意事项",
    "相关节点",
]


def run_validate_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, front_matter: dict[str, str], body_lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    lines.extend(f"{key}: {value}" for key, value in front_matter.items())
    lines.append("---")
    lines.append("")
    lines.extend(body_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_minimal_fixture(root: Path) -> tuple[Path, Path, Path]:
    docs_root = root / "docs"
    manifest_path = root / "components.json"
    groups_path = root / "component-groups.json"
    write_json(
        manifest_path,
        [
            {
                "resource_key": "browser.navigate",
                "display_name_zh": "导航",
                "capability_domain": "browser",
                "component_library_visible": True,
                "compatibility_only": False,
            }
        ],
    )
    write_json(
        groups_path,
        {
            "product": "weconduct",
            "version": "0.9.1",
            "groups": [
                {
                    "group_id": "browser-navigation",
                    "family": "browser",
                    "title_zh": "页面导航",
                    "description_zh": "desc",
                    "index_path": "docs/weconduct/components/browser/navigation/index.md",
                    "detail_dir": "docs/weconduct/components/browser/navigation",
                }
            ],
            "assignments": {
                "browser.navigate": {
                    "primary_group_id": "browser-navigation",
                    "page_path": "docs/weconduct/components/browser/navigation/navigate.md",
                    "related_group_ids": [],
                }
            },
        },
    )
    write_markdown(
        docs_root / "index.md",
        {"product": "site", "version": "latest", "doc_id": "site:index"},
        ["# 首页"],
    )
    write_markdown(
        docs_root / "weconduct" / "components" / "browser" / "navigation" / "index.md",
        {
            "product": "weconduct",
            "version": "0.9.1",
            "doc_id": "component-group:browser-navigation",
        },
        ["# 页面导航"],
    )
    component_body = ["# 导航"]
    component_body.extend(f"## {section}" for section in REQUIRED_SECTIONS)
    write_markdown(
        docs_root / "weconduct" / "components" / "browser" / "navigation" / "navigate.md",
        {
            "product": "weconduct",
            "version": "0.9.1",
            "doc_id": "component:browser.navigate",
        },
        component_body,
    )
    write_markdown(
        docs_root / "weave" / "overview.md",
        {"product": "weave", "version": "0.5.0", "doc_id": "weave:overview"},
        ["# Weave"],
    )
    write_markdown(
        docs_root / "reference" / "status.md",
        {"product": "site", "version": "latest", "doc_id": "site:reference:status"},
        ["# Status"],
    )
    return docs_root, manifest_path, groups_path


def test_validate_pages_accepts_valid_fixture(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "pages=5" in result.stdout
    assert "missing_component_pages=0" in result.stdout
    assert "missing_group_pages=0" in result.stdout


def test_validate_pages_accepts_utf8_bom_front_matter(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    index_path = docs_root / "index.md"
    original = index_path.read_text(encoding="utf-8")
    index_path.write_text("\ufeff" + original, encoding="utf-8")

    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "missing front matter" not in f"{result.stdout}\n{result.stderr}"


def test_validate_pages_rejects_unknown_product_selector(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)

    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
        "--product",
        "site",
    )

    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "unknown --product selector" in combined
    assert "site" in combined
    assert "weconduct" in combined
    assert "weave" in combined


def test_validate_pages_rejects_missing_required_sections(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    write_markdown(
        docs_root / "weconduct" / "components" / "browser" / "navigation" / "navigate.md",
        {
            "product": "weconduct",
            "version": "0.9.1",
            "doc_id": "component:browser.navigate",
        },
        ["# 导航", "## 功能说明"],
    )
    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )
    assert result.returncode != 0
    assert "什么时候用" in f"{result.stdout}\n{result.stderr}"


def test_validate_pages_rejects_malformed_frontmatter_duplicate_doc_id_and_wrong_version(
    tmp_path: Path,
) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    write_markdown(
        docs_root / "weconduct" / "duplicate.md",
        {"product": "weconduct", "version": "0.9.1", "doc_id": "component:browser.navigate"},
        ["# 重复"],
    )
    malformed = docs_root / "weconduct" / "bad.md"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("not-frontmatter\n", encoding="utf-8")
    write_markdown(
        docs_root / "weave" / "wrong.md",
        {"product": "weave", "version": "0.8.1", "doc_id": "weave:wrong"},
        ["# Wrong"],
    )
    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "duplicate" in combined
    assert "front matter" in combined
    assert "0.5.0" in combined


def test_allow_incomplete_only_waives_missing_pages(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    (docs_root / "weconduct" / "components" / "browser" / "navigation" / "navigate.md").unlink()
    (docs_root / "weconduct" / "components" / "browser" / "navigation" / "index.md").unlink()

    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
        "--allow-incomplete",
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "missing_component_pages=1" in result.stdout
    assert "missing_group_pages=1" in result.stdout

    # weconduct page version is validated for FORMAT, not a pinned literal
    # (pages may document different versions). A malformed version is still
    # rejected; a different-but-well-formed version (e.g. 0.8.0) is accepted.
    write_markdown(
        docs_root / "weconduct" / "components" / "browser" / "navigation" / "index.md",
        {
            "product": "weconduct",
            "version": "not-a-version",
            "doc_id": "component-group:browser-navigation",
        },
        ["# 页面导航"],
    )
    malformed_result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
        "--allow-incomplete",
    )
    assert malformed_result.returncode != 0
    assert "version malformed" in f"{malformed_result.stdout}\n{malformed_result.stderr}"


def test_actual_repo_page_validation_reports_complete_component_catalog() -> None:
    result = run_validate_cli(
        "--docs-root",
        str(ROOT / "docs"),
        "--manifest",
        str(MANIFEST_PATH),
        "--groups",
        str(GROUPS_PATH),
        "--allow-incomplete",
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "missing_component_pages=0" in result.stdout
    assert "missing_group_pages=0" in result.stdout


def test_validate_pages_ignores_internal_documents(tmp_path: Path) -> None:
    docs_root, manifest_path, groups_path = build_minimal_fixture(tmp_path)
    internal_plan = docs_root / "superpowers" / "plans" / "implementation.md"
    internal_plan.parent.mkdir(parents=True, exist_ok=True)
    internal_plan.write_text("# Internal plan without user-page metadata\n", encoding="utf-8")

    result = run_validate_cli(
        "--docs-root",
        str(docs_root),
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "errors=0" in result.stdout
