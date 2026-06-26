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
    assert "pyinstaller" in pyproject_text


def test_preview_packaging_spec_collects_bundled_python_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    spec_text = (
        root / "packaging" / "pyinstaller" / "weconduct_preview.spec"
    ).read_text(encoding="utf-8")

    assert "bundled_python_source" in spec_text
    assert 'datas.append((str(bundled_python_source), "."))' in spec_text
