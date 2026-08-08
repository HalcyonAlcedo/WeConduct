from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "docs/weconduct/troubleshooting/index.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:index"),
    "docs/weconduct/troubleshooting/project-and-startup.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:project-and-startup"),
    "docs/weconduct/troubleshooting/graph-validation.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:graph-validation"),
    "docs/weconduct/troubleshooting/runtime-and-debug.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:runtime-and-debug"),
    "docs/weconduct/troubleshooting/browser-and-network.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:browser-and-network"),
    "docs/weconduct/troubleshooting/files-python-and-packages.md": ("weconduct", "0.9.0", "weconduct:troubleshooting:files-python-and-packages"),
    "docs/weconduct/reference/keyboard-shortcuts.md": ("weconduct", "0.9.0", "weconduct:reference:keyboard-shortcuts"),
    "docs/weconduct/reference/project-format.md": ("weconduct", "0.9.0", "weconduct:reference:project-format"),
    "docs/weconduct/reference/variable-syntax.md": ("weconduct", "0.9.0", "weconduct:reference:variable-syntax"),
    "docs/weconduct/reference/glossary.md": ("weconduct", "0.9.0", "weconduct:reference:glossary"),
}


def nav_targets(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= nav_targets(item)
        return result
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result |= nav_targets(item)
        return result
    return set()


def test_reference_and_troubleshooting_pages_are_published() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    published = nav_targets(config["nav"])
    for path_text, (product, version, doc_id) in PAGES.items():
        path = ROOT / path_text
        assert path.exists(), path_text
        text = path.read_text(encoding="utf-8")
        _, raw_front_matter, _ = text.split("---\n", 2)
        front_matter = yaml.safe_load(raw_front_matter)
        assert front_matter["product"] == product
        assert front_matter["version"] == version
        assert front_matter["doc_id"] == doc_id
        assert path_text.removeprefix("docs/") in published


def test_hidden_version_manifests_reserve_future_switcher() -> None:
    expected = {
        "weconduct": "0.9.0",
        "weave": "0.5.0",
    }
    for product, version in expected.items():
        payload = json.loads((ROOT / "versions" / f"{product}.json").read_text(encoding="utf-8"))
        assert payload["product"] == product
        assert payload["current"] == version
        assert payload["switcher_enabled"] is False
        assert payload["versions"] == [
                {
                    "version": version,
                    "path": f"/WeConduct/{product}/",
                    "latest": True,
                }
            ]


def test_reference_pages_include_real_contract_terms() -> None:
    project_format = (ROOT / "docs/weconduct/reference/project-format.md").read_text(encoding="utf-8")
    variables = (ROOT / "docs/weconduct/reference/variable-syntax.md").read_text(encoding="utf-8")

    assert "project_file_schema_version" in project_format
    assert "project-v2" in project_format
    assert "graph-v1" in project_format
    assert "initial_variables" in variables
    assert "runtime" in variables
