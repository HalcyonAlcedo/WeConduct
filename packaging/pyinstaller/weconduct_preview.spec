# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parents[1]
captcha_ocr_source = root / "third_party" / "captcha_ocr"
icon_path = root / "assets" / "icons" / "weconduct.ico"
bundled_python_home = Path(getattr(sys, "_base_executable", sys.executable)).resolve().parent


def _collect_bundled_python_runtime_entries(base_dir: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not base_dir.exists():
        return entries
    required_paths = [
        base_dir / "python.exe",
        base_dir / "pythonw.exe",
        base_dir / "DLLs",
        base_dir / "Lib" / "venv" / "__init__.py",
        base_dir / "Lib" / "ensurepip" / "__init__.py",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "bundled python runtime source is incomplete: " + ", ".join(missing)
        )
    for candidate in base_dir.iterdir():
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in {".exe", ".dll"}:
            continue
        entries.append((str(candidate), "bundled-python"))
    for directory_name in ("DLLs", "Lib"):
        source_dir = base_dir / directory_name
        if not source_dir.exists():
            continue
        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if directory_name == "Lib" and any(
                blocked in file_path.parts
                for blocked in ("site-packages", "__pycache__", "test", "tkinter", "idlelib", "turtledemo")
            ):
                continue
            relative_parent = file_path.relative_to(base_dir).parent.as_posix()
            entries.append((str(file_path), f"bundled-python/{relative_parent}"))
    pyvenv_cfg = base_dir / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        entries.append((str(pyvenv_cfg), "bundled-python"))
    return entries

datas = [(str(root / "ui" / "dist"), "ui/dist")]
if captcha_ocr_source.exists():
    datas.append((str(captcha_ocr_source), "captcha_ocr"))
datas.extend(_collect_bundled_python_runtime_entries(bundled_python_home))

network_runtime_packages = (
    "httpx",
    "h2",
    "httpx_sse",
    "websockets",
    "graphql",
    "authlib",
    "cryptography",
    "msgpack",
    "socksio",
    "python_socks",
)

# Do not collect every optional integration of these packages.  In particular,
# authlib's Django/Flask integrations, websockets' legacy/sync stacks and
# python-socks' curio backend are not part of the WeConduct runner.
network_runtime_submodules: dict[str, set[str]] = {
    "httpx": {
        "httpx",
        "httpx._client",
        "httpx._config",
        "httpx._models",
        "httpx._transports",
        "httpx._transports.base",
        "httpx._transports.default",
        "httpx._transports.asgi",
        "httpx._transports.wsgi",
    },
    "httpx_sse": {"httpx_sse", "httpx_sse._api"},
    "h2": {
        "h2",
        "h2.config",
        "h2.connection",
        "h2.events",
        "h2.exceptions",
        "h2.frame_buffer",
        "h2.settings",
        "h2.stream",
        "h2.utilities",
        "h2.windows",
    },
    "websockets": {
        "websockets",
        "websockets.asyncio",
        "websockets.asyncio.client",
        "websockets.asyncio.connection",
        "websockets.asyncio.server",
        "websockets.client",
        "websockets.exceptions",
        "websockets.frames",
        "websockets.headers",
        "websockets.http11",
        "websockets.protocol",
        "websockets.server",
        "websockets.streams",
    },
    "graphql": {
        "graphql",
        "graphql.error",
        "graphql.execution",
        "graphql.language",
        "graphql.pyutils",
        "graphql.type",
        "graphql.utilities",
    },
    "authlib": {"authlib", "authlib.oauth2"},
    "cryptography": {
        "cryptography",
        "cryptography.hazmat",
        "cryptography.hazmat.bindings",
        "cryptography.hazmat.primitives",
        "cryptography.x509",
    },
    "msgpack": {"msgpack", "msgpack._cmsgpack", "msgpack.fallback"},
    "socksio": {"socksio"},
    "python_socks": {
        "python_socks",
        "python_socks.async_",
        "python_socks.async_.asyncio",
        "python_socks.async_.asyncio._proxy",
    },
}
application_hiddenimports: list[str] = [
    # application.__init__ uses importlib for the public UpdateService export.
    "weconduct.application.update_service",
]
network_hiddenimports: list[str] = [
    "weconduct.network_runtime.windows_proxy_worker",
]
network_binaries: list[tuple[str, str]] = []
for package_name in network_runtime_packages:
    allowed_modules = network_runtime_submodules[package_name]
    network_hiddenimports.extend(
        collect_submodules(
            package_name,
            filter=lambda module_name, allowed=allowed_modules: module_name in allowed,
        )
    )

for package_name in ("cryptography", "msgpack"):
    network_binaries.extend(collect_dynamic_libs(package_name))

a = Analysis(
    [str(root / "src" / "weconduct" / "cli" / "main.py")],
    pathex=[str(root / "src")],
    binaries=network_binaries,
    datas=datas,
    hiddenimports=[
        "weconduct.cli.main",
        "webview",
        *application_hiddenimports,
        *network_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(root / "packaging" / "pyinstaller" / "desktop_shell_runtime_hook.py")],
    excludes=[
        "websockets.legacy",
        "websockets.sync",
        "authlib.integrations.django_client",
        "authlib.integrations.flask_client",
        "django",
        "curio",
    ],
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
