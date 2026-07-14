from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_mkdocs_metadata_and_assets_baseline() -> None:
    content = read_text("mkdocs.yml")

    assert "site_name: WeConduct 文档" in content
    assert "WeConduct 0.8.1" in content
    assert "Weave 0.5.0" in content
    assert "site_url: https://halcyonalcedo.github.io/WeConduct/" in content
    assert "repo_url: https://github.com/HalcyonAlcedo/WeConduct" in content
    assert "repo_name: HalcyonAlcedo/WeConduct" in content
    assert 'edit_uri: ""' in content
    assert "navigation.tabs" in content
    assert "navigation.indexes" in content
    assert "navigation.prune" in content
    assert "extra_javascript:" in content
    assert "- assets/javascripts/weconduct-graph.js" in content
    assert "extra_css:" in content
    assert "- assets/stylesheets/weconduct-graph.css" in content


def test_index_front_matter_and_versions() -> None:
    content = read_text("docs/index.md")

    assert content.startswith("---\n")
    assert "product: site" in content
    assert "version: latest" in content
    assert "doc_id: site:index" in content
    assert "WeConduct 0.8.1" in content
    assert "Weave 0.5.0" in content


def test_workflow_uses_official_pages_actions_on_docs_branch() -> None:
    content = read_text(".github/workflows/deploy-docs.yml")

    assert "workflow_dispatch:" in content
    assert "branches:" in content
    assert "- docs" in content
    assert "contents: read" in content
    assert "pages: write" in content
    assert "id-token: write" in content
    assert "group: pages" in content
    assert "cancel-in-progress: true" in content
    assert "python -m pip install -r requirements-dev.txt" in content
    assert "python -m pytest -q" in content
    assert 'if (Test-Path "validate_pages.py")' in content
    assert 'if (Test-Path "validate_graph_examples.py")' in content
    assert "python -m mkdocs build --strict" in content
    assert "actions/upload-pages-artifact@v3" in content
    assert "actions/deploy-pages@v4" in content
