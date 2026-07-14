from pathlib import Path

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
    assert config["nav"] == [{"首页": "index.md"}]


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
