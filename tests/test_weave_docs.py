from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAGES = {
    "weave/index.md": "weave:index",
    "weave/getting-started/install-and-update.md": "weave:getting-started:install-and-update",
    "weave/guide/workspaces.md": "weave:guide:workspaces",
    "weave/guide/browser-sessions.md": "weave:guide:browser-sessions",
    "weave/guide/page-tree-and-search.md": "weave:guide:page-tree-and-search",
    "weave/guide/node-details-and-selectors.md": "weave:guide:node-details-and-selectors",
    "weave/guide/overlay-and-inspect-mode.md": "weave:guide:overlay-and-inspect-mode",
    "weave/guide/network-capture-and-replay.md": "weave:guide:network-capture-and-replay",
    "weave/guide/intercept-rules.md": "weave:guide:intercept-rules",
    "weave/guide/browser-storage.md": "weave:guide:browser-storage",
    "weave/guide/layout-and-settings.md": "weave:guide:layout-and-settings",
    "weave/guide/plugins.md": "weave:guide:plugins",
    "weave/workflows/use-with-weconduct.md": "weave:workflows:use-with-weconduct",
    "weave/troubleshooting/index.md": "weave:troubleshooting:index",
}


def collect_nav_targets(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= collect_nav_targets(item)
        return result
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result |= collect_nav_targets(item)
        return result
    return set()


def test_weave_pages_have_stable_front_matter_and_navigation() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    nav_targets = collect_nav_targets(config["nav"])
    for relative_path, doc_id in EXPECTED_PAGES.items():
        path = ROOT / "docs" / relative_path
        assert path.exists(), relative_path
        text = path.read_text(encoding="utf-8")
        _, raw_front_matter, _ = text.split("---\n", 2)
        front_matter = yaml.safe_load(raw_front_matter)
        assert front_matter["product"] == "weave"
        assert front_matter["version"] == "0.5.0"
        assert front_matter["doc_id"] == doc_id
        assert relative_path in nav_targets


def test_weave_docs_state_current_user_facing_limits() -> None:
    install = (ROOT / "docs/weave/getting-started/install-and-update.md").read_text(encoding="utf-8")
    network = (ROOT / "docs/weave/guide/network-capture-and-replay.md").read_text(encoding="utf-8")
    storage = (ROOT / "docs/weave/guide/browser-storage.md").read_text(encoding="utf-8")
    cooperation = (ROOT / "docs/weave/workflows/use-with-weconduct.md").read_text(encoding="utf-8")
    plugins = (ROOT / "docs/weave/guide/plugins.md").read_text(encoding="utf-8")

    assert "内置“网络捕获”面板当前没有“重放”按钮" in network
    assert "不能在当前内置 UI 里直接新增 Cookie" in storage
    assert "没有直接同步接口" in cooperation
    assert "只覆盖 0.5.0 的用户操作" in plugins
    assert "插件开发 API" in plugins
    assert "尚未发布公开 Release 或可下载资产" in install
    assert "便携产物" in install
