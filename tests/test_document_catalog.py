import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "weconduct-0.9.1" / "components.json"
GROUPS_PATH = ROOT / "data" / "weconduct-0.9.1" / "component-groups.json"
SCRIPT_PATH = ROOT / "tools" / "build_document_catalog.py"

EXPECTED_GROUP_IDS = {
    "flow-and-components",
    "control-branching",
    "control-loops",
    "control-parallel",
    "control-reliability",
    "browser-navigation",
    "browser-interaction",
    "browser-waits",
    "browser-page-context",
    "browser-state-and-content",
    "browser-storage-and-cookies",
    "browser-network-and-downloads",
    "browser-scripts-and-extraction",
    "browser-dialogs",
    "data-variables",
    "data-page-values",
    "data-conversion-and-expressions",
    "data-lists",
    "files-text-and-csv",
    "excel-read",
    "excel-write-and-update",
    "network-automation",
    "input-and-messaging",
    "python",
    "time",
    "compatibility-and-internal",
}
EXPECTED_HIDDEN_KEYS = {
    "control.jump_to_step",
    "control.end_foreach",
    "control.foreach_continue",
    "control.foreach_break",
    "graph.call_subgraph",
    "call_blueprint",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_catalog_cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def manifest() -> list[dict[str, Any]]:
    payload = read_json(MANIFEST_PATH)
    assert isinstance(payload, list)
    return payload


@pytest.fixture()
def group_payload() -> dict[str, Any]:
    payload = read_json(GROUPS_PATH)
    assert isinstance(payload, dict)
    return payload


def test_committed_component_group_snapshot_matches_manifest(
    manifest: list[dict[str, Any]],
    group_payload: dict[str, Any],
) -> None:
    assert group_payload["product"] == "weconduct"
    assert group_payload["version"] == "0.9.1"

    groups = group_payload["groups"]
    assignments = group_payload["assignments"]
    assert len(groups) == 26
    assert {group["group_id"] for group in groups} == EXPECTED_GROUP_IDS
    assert len(assignments) == 135

    manifest_keys = {item["resource_key"] for item in manifest}
    assert set(assignments) == manifest_keys

    valid_group_ids = {group["group_id"] for group in groups}
    index_paths = set()
    detail_dirs = set()
    for group in groups:
        assert group["family"].strip()
        assert group["title_zh"].strip()
        assert group["description_zh"].strip()
        assert group["index_path"].strip()
        assert group["detail_dir"].strip()
        index_paths.add(group["index_path"])
        detail_dirs.add(group["detail_dir"])
    assert len(index_paths) == 26
    assert len(detail_dirs) == 26

    page_paths = set()
    hidden_assignments = {
        resource_key: assignment["primary_group_id"]
        for resource_key, assignment in assignments.items()
        if resource_key in EXPECTED_HIDDEN_KEYS
    }
    assert hidden_assignments == {
        resource_key: "compatibility-and-internal"
        for resource_key in EXPECTED_HIDDEN_KEYS
    }

    for component in manifest:
        resource_key = component["resource_key"]
        assignment = assignments[resource_key]
        assert assignment["primary_group_id"] in valid_group_ids
        assert assignment["page_path"].strip()
        assert assignment["page_path"] not in page_paths
        page_paths.add(assignment["page_path"])
        assert all(group_id in valid_group_ids for group_id in assignment["related_group_ids"])
        if component["component_library_visible"]:
            assert assignment["primary_group_id"] != "compatibility-and-internal"
        else:
            assert component["compatibility_only"] is True
    assert len(page_paths) == 135


def test_catalog_cli_report_list_and_family_filters(tmp_path: Path) -> None:
    report_path = tmp_path / "catalog.json"
    result = run_catalog_cli("--report", str(report_path))
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "135 components, 26 groups, 0 unassigned, 0 duplicate paths"
    assert result.stderr == ""
    assert report_path.read_text(encoding="utf-8").endswith("\n")

    report = read_json(report_path)
    assert report["summary"] == {
        "components": 135,
        "groups": 26,
        "unassigned": 0,
        "duplicate_page_paths": 0,
        "duplicate_index_paths": 0,
    }
    assert len(report["groups"]) == 26
    assert len(report["assignments"]) == 135

    list_result = run_catalog_cli("--list", "--family", "browser,excel-read")
    assert list_result.returncode == 0, list_result.stderr or list_result.stdout
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert lines
    families = {line.split("\t")[0] for line in lines}
    groups = {line.split("\t")[1] for line in lines}
    assert "browser" in families
    assert "excel-read" in groups
    assert all(len(line.split("\t")) == 5 for line in lines)


def test_catalog_cli_rejects_unknown_family_selector() -> None:
    result = run_catalog_cli("--family", "browser,unknown-family")

    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "unknown --family selector" in combined
    assert "unknown-family" in combined
    assert "browser" not in combined or "unknown-family" in combined


def test_catalog_cli_rejects_string_bool_manifest_flags(tmp_path: Path) -> None:
    manifest_path = tmp_path / "components.json"
    groups_path = tmp_path / "component-groups.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "resource_key": "browser.navigate",
                    "display_name_zh": "导航",
                    "capability_domain": "browser",
                    "component_library_visible": "false",
                    "compatibility_only": "0",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    groups_path.write_text(
        json.dumps(
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
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_catalog_cli("--manifest", str(manifest_path), "--groups", str(groups_path))

    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "component_library_visible" in combined or "compatibility_only" in combined
    assert "bool" in combined


def test_catalog_cli_rejects_invalid_group_contract(tmp_path: Path) -> None:
    manifest_path = tmp_path / "components.json"
    groups_path = tmp_path / "component-groups.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "resource_key": "browser.navigate",
                    "display_name_zh": "导航",
                    "capability_domain": "browser",
                    "component_library_visible": True,
                    "compatibility_only": False,
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    groups_path.write_text(
        json.dumps(
            {
                "product": "weconduct",
                "version": "0.8.0",
                "groups": [
                    {
                        "group_id": "browser-navigation",
                        "family": "browser",
                        "title_zh": "页面导航",
                        "description_zh": "desc",
                        "index_path": "docs/weconduct/components/browser/navigation/index.md",
                        "detail_dir": "docs/weconduct/components/browser/navigation",
                    },
                    {
                        "group_id": "browser-navigation",
                        "family": "browser",
                        "title_zh": "重复",
                        "description_zh": "desc",
                        "index_path": "docs/weconduct/components/browser/navigation/index.md",
                        "detail_dir": "docs/weconduct/components/browser/navigation",
                    },
                ],
                "assignments": {
                    "browser.navigate": {
                        "primary_group_id": "unknown-group",
                        "page_path": "docs/weconduct/components/browser/navigation/navigate.md",
                        "related_group_ids": ["missing-group"],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_catalog_cli(
        "--manifest",
        str(manifest_path),
        "--groups",
        str(groups_path),
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert (
        "version" in combined
        or "browser-navigation" in combined
        or "unknown-group" in combined
    )
