from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_IDS = (
    "browser-form-automation",
    "browser-table-to-excel",
    "browser-auth-session",
    "data-list-processing",
    "file-csv-transformation",
    "control-branch-and-loop",
    "parallel-retry-failover",
    "http-and-python-processing",
    "custom-component",
    "wcrun-package-workflow",
)


def parse_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, raw, body = text.split("---\n", 2)
    return yaml.safe_load(raw), body


def test_all_workflow_examples_have_pages_graphs_and_downloads() -> None:
    for example_id in EXAMPLE_IDS:
        page = ROOT / "docs" / "weconduct" / "examples" / f"{example_id}.md"
        graph = ROOT / "docs" / "assets" / "graphs" / "examples" / f"{example_id}.json"
        download = ROOT / "docs" / "downloads" / "weconduct" / "0.9.0" / f"{example_id}.zip"
        assert page.exists(), example_id
        assert graph.exists(), example_id
        assert download.exists(), example_id

        front_matter, body = parse_front_matter(page)
        assert front_matter == {
            "product": "weconduct",
            "version": "0.9.0",
            "doc_id": f"weconduct:example:{example_id}",
        }
        for heading in (
            "这个示例做什么", "准备工作", "流程图", "图中使用了哪些节点", "如何运行",
            "运行后应该看到什么", "如果出错怎么办", "下载项目",
        ):
            assert f"## {heading}" in body
        assert f"{example_id}.json" in body
        assert f"{example_id}.zip" in body


def test_download_archives_contain_directory_projects() -> None:
    for example_id in EXAMPLE_IDS:
        archive_path = (
            ROOT / "docs" / "downloads" / "weconduct" / "0.9.0" / f"{example_id}.zip"
        )
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            project_name = f"{example_id}.weconduct.json"
            storage_root = f"{example_id}.weconduct.data"
            required = {
                project_name,
                f"{storage_root}/graphs/workspace.graph.json",
                f"{storage_root}/resources/index.json",
                f"{storage_root}/resource-overrides.json",
            }
            assert required <= names, f"{example_id}: {sorted(required - names)}"
            project = json.loads(archive.read(project_name).decode("utf-8"))
            assert project["project_file_schema_version"] == 2
            assert project["project"]["project_schema_version"] == "project-v2"
            assert project["project"]["main_graph_path"] == (
                f"{storage_root}/graphs/workspace.graph.json"
            )


def test_example_index_lists_every_download() -> None:
    index = (ROOT / "docs" / "weconduct" / "examples" / "index.md").read_text(encoding="utf-8")
    for example_id in EXAMPLE_IDS:
        assert f"{example_id}.md" in index
        assert f"{example_id}.zip" in index


def test_download_projects_open_with_weconduct_090(tmp_path: Path) -> None:
    source_root = Path(os.environ.get("WECONDUCT_SOURCE_ROOT", ROOT.parent / "WeConduct"))
    if not (source_root / "src" / "weconduct").exists():
        pytest.skip("WeConduct source tree is unavailable")
    sys.path.insert(0, str(source_root / "src"))
    try:
        from weconduct.application import CompilationWorkbenchService

        for example_id in EXAMPLE_IDS:
            archive_path = (
                ROOT / "docs" / "downloads" / "weconduct" / "0.9.0" / f"{example_id}.zip"
            )
            target = tmp_path / example_id
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(target)
            service = CompilationWorkbenchService()
            result = service.open_project(
                project_path=target / f"{example_id}.weconduct.json"
            )
            assert result["project"]["project_name"]
            graph_model = service.get_graph_document()["graph_model"]
            validation = service.validate_graph_document(graph_model.model_dump(mode="json"))
            assert validation["status"] == "valid", (
                example_id,
                validation["diagnostics"],
            )
            if example_id in {
                "data-list-processing",
                "custom-component",
                "wcrun-package-workflow",
            }:
                started = service.start_runtime_session(graph_document_payload=None)
                session_id = started["runtime_session"]["session_id"]
                runtime = service.run_runtime_session(session_id=session_id)
                assert runtime["runtime_session"]["status"] == "completed", (example_id, runtime)
                assert runtime["result"]["status"] == "succeeded", (example_id, runtime)
    finally:
        sys.path.remove(str(source_root / "src"))
