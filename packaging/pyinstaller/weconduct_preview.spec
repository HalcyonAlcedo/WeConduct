# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

root = Path(SPECPATH).parents[1]
captcha_ocr_source = root / "third_party" / "captcha_ocr"
icon_path = root / "assets" / "icons" / "weconduct.ico"
bundled_python_source = Path(getattr(sys, "_base_executable", sys.executable)).resolve()

datas = [(str(root / "ui" / "dist"), "ui/dist")]
if captcha_ocr_source.exists():
    datas.append((str(captcha_ocr_source), "captcha_ocr"))
if bundled_python_source.exists():
    datas.append((str(bundled_python_source), "."))

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
