# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
captcha_ocr_source = root / "third_party" / "captcha_ocr"
icon_path = root / "assets" / "icons" / "weconduct.ico"
bundled_python_home = Path(getattr(sys, "_base_executable", sys.executable)).resolve().parent


def _collect_bundled_python_runtime_entries(base_dir: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not base_dir.exists():
        return entries
    candidate_names = [
        "python.exe",
        "pythonw.exe",
        "python313.dll",
        "python3.dll",
        "VCRUNTIME140.dll",
        "VCRUNTIME140_1.dll",
        "MSVCP140.dll",
        "MSVCP140_1.dll",
        "api-ms-win-crt-conio-l1-1-0.dll",
        "api-ms-win-crt-convert-l1-1-0.dll",
        "api-ms-win-crt-environment-l1-1-0.dll",
        "api-ms-win-crt-filesystem-l1-1-0.dll",
        "api-ms-win-crt-heap-l1-1-0.dll",
        "api-ms-win-crt-locale-l1-1-0.dll",
        "api-ms-win-crt-math-l1-1-0.dll",
        "api-ms-win-crt-process-l1-1-0.dll",
        "api-ms-win-crt-runtime-l1-1-0.dll",
        "api-ms-win-crt-stdio-l1-1-0.dll",
        "api-ms-win-crt-string-l1-1-0.dll",
        "api-ms-win-crt-time-l1-1-0.dll",
        "api-ms-win-crt-utility-l1-1-0.dll",
    ]
    for name in candidate_names:
        candidate = base_dir / name
        if candidate.exists() and candidate.is_file():
            entries.append((str(candidate), "bundled-python"))
    return entries

datas = [(str(root / "ui" / "dist"), "ui/dist")]
if captcha_ocr_source.exists():
    datas.append((str(captcha_ocr_source), "captcha_ocr"))
datas.extend(_collect_bundled_python_runtime_entries(bundled_python_home))

a = Analysis(
    [str(root / "src" / "weconduct" / "cli" / "main.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["weconduct.cli.main", "webview"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / "packaging" / "pyinstaller" / "desktop_shell_runtime_hook.py")],
    excludes=[],
    noarchive=False,
)
# The runtime hook appends "desktop-shell" so the bundled executable opens the
# preview desktop shell instead of showing raw CLI usage.
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WeConduct",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WeConduct",
)
