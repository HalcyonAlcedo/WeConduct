from pathlib import Path


def test_python_workspace_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "pyproject.toml").exists()
    assert (root / "pytest.ini").exists()
    assert (root / "src" / "weconduct" / "__init__.py").exists()
    assert (root / "ui" / "README.md").exists()
