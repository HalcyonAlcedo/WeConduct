from pathlib import Path


def test_preview_packaging_files_reference_desktop_shell_entrypoint() -> None:
    root = Path(__file__).resolve().parents[1]
    spec_text = (
        root / "packaging" / "pyinstaller" / "weconduct_preview.spec"
    ).read_text(encoding="utf-8")
    script_text = (root / "scripts" / "build_bundle.ps1").read_text(encoding="utf-8")
    runtime_hook_text = (
        root / "packaging" / "pyinstaller" / "desktop_shell_runtime_hook.py"
    ).read_text(encoding="utf-8")
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    release_workflow_text = (
        root / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
    portable_readme_text = (
        root / "packaging" / "portable" / "README_PORTABLE.txt"
    ).read_text(encoding="utf-8")

    assert "weconduct.cli.main" in spec_text
    assert "desktop-shell" in spec_text
    assert "ui/dist" in spec_text.replace("\\", "/")
    assert "captcha_ocr_source" in spec_text
    assert "captcha_ocr" in spec_text
    assert "ms-playwright" not in spec_text
    assert "PLAYWRIGHT_BROWSERS_PATH" not in runtime_hook_text
    assert "pyinstaller" in script_text.lower()
    assert "npm run build" in script_text.lower()
    assert "packaging/pyinstaller/weconduct_preview.spec" in script_text.replace(
        "\\",
        "/",
    )
    assert "pywebview" in pyproject_text
    assert "playwright" in pyproject_text
    assert "pyinstaller" in pyproject_text
    assert "openpyxl" in pyproject_text
    assert "README_PORTABLE.txt" in release_workflow_text
    assert "Copy-Item packaging/portable/README_PORTABLE.txt" in release_workflow_text
    assert "Unblock-File" in portable_readme_text


def test_preview_packaging_pins_pythonnet_stack_versions() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'pywebview==6.2.1' in pyproject_text
    assert 'pythonnet==3.0.5' in pyproject_text
    assert 'clr_loader==0.2.10' in pyproject_text


def test_preview_packaging_spec_collects_bundled_python_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    spec_text = (
        root / "packaging" / "pyinstaller" / "weconduct_preview.spec"
    ).read_text(encoding="utf-8")

    assert "bundled_python_source" in spec_text
    assert 'datas.append((str(bundled_python_source), "."))' in spec_text
