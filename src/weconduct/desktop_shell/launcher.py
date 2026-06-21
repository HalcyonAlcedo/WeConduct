from __future__ import annotations

from dataclasses import dataclass
import os
import json
from pathlib import Path
import sys
from threading import Thread
from types import ModuleType
from typing import Any

from weconduct.api import build_api_server


class DesktopShellDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DesktopShellOptions:
    host: str = "127.0.0.1"
    port: int = 0
    workspace_state_path: Path | None = None
    preferences_path: Path | None = None
    ui_dist_path: Path | None = None
    title: str = "WeConduct"
    width: int = 1920
    height: int = 1080


def resolve_default_workspace_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_path = Path(local_app_data)
    else:
        base_path = Path.home() / "AppData" / "Local"
    return base_path / "WeConduct" / "workspace-state.json"


def resolve_default_preferences_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_path = Path(local_app_data)
    else:
        base_path = Path.home() / "AppData" / "Local"
    return base_path / "WeConduct" / "preferences.json"


def resolve_default_ui_dist_path() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root) / "ui" / "dist"
    return Path(__file__).resolve().parents[3] / "ui" / "dist"


def launch_desktop_shell(
    options: DesktopShellOptions,
    *,
    webview_module: ModuleType | Any | None = ...,
) -> dict:
    webview = _resolve_webview_module(webview_module)
    workspace_state_path = (
        Path(options.workspace_state_path)
        if options.workspace_state_path is not None
        else resolve_default_workspace_state_path()
    )
    preferences_path = (
        Path(options.preferences_path)
        if options.preferences_path is not None
        else resolve_default_preferences_path()
    )
    ui_dist_path = (
        Path(options.ui_dist_path)
        if options.ui_dist_path is not None
        else resolve_default_ui_dist_path()
    )
    preferred_width, preferred_height = _resolve_preferred_window_size(
        preferences_path,
        fallback_width=options.width,
        fallback_height=options.height,
    )
    server = build_api_server(
        host=options.host,
        port=options.port,
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
        ui_dist_path=ui_dist_path,
    )
    runtime_host, runtime_port = server.server_address
    base_url = f"http://{runtime_host}:{runtime_port}"
    window_ref: dict[str, Any] = {}
    server.file_dialog_provider = _build_file_dialog_provider(webview, window_ref)
    server.open_path_provider = _build_open_path_provider(window_ref)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        window_ref["window"] = webview.create_window(
            options.title,
            base_url,
            width=preferred_width,
            height=preferred_height,
        )
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
    return {
        "status": "closed",
        "base_url": base_url,
        "workspace_state_path": str(workspace_state_path.resolve()),
        "preferences_path": str(preferences_path.resolve()),
        "ui_dist_path": str(ui_dist_path.resolve()),
    }


def _resolve_preferred_window_size(
    preferences_path: Path,
    *,
    fallback_width: int,
    fallback_height: int,
) -> tuple[int, int]:
    if not preferences_path.exists():
        return fallback_width, fallback_height
    try:
        payload = json.loads(preferences_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback_width, fallback_height
    if not isinstance(payload, dict):
        return fallback_width, fallback_height
    program_settings = payload.get("program_settings")
    if not isinstance(program_settings, dict):
        return fallback_width, fallback_height
    default_window_size = program_settings.get("default_window_size")
    if not isinstance(default_window_size, dict):
        return fallback_width, fallback_height
    width = default_window_size.get("width")
    height = default_window_size.get("height")
    if not isinstance(width, int) or width <= 0:
        width = fallback_width
    if not isinstance(height, int) or height <= 0:
        height = fallback_height
    return width, height


def _resolve_webview_module(webview_module: ModuleType | Any | None):
    if webview_module is None:
        raise DesktopShellDependencyError(
            "pywebview is required for the desktop shell. "
            "Install the project desktop dependencies before launching P4 preview."
        )
    if webview_module is not ...:
        return webview_module
    try:
        import webview
    except ImportError as exc:
        raise DesktopShellDependencyError(
            "pywebview is required for the desktop shell. "
            "Install the project desktop dependencies before launching P4 preview."
        ) from exc
    return webview


def _build_file_dialog_provider(webview: Any, window_ref: dict[str, Any]):
    def provider(payload: dict) -> dict:
        window = window_ref.get("window")
        if window is None or not hasattr(window, "create_file_dialog"):
            raise RuntimeError("host file dialog is unavailable")

        mode = payload["mode"]
        dialog_type = _resolve_file_dialog_type(webview, mode)
        default_path = payload.get("default_path") or ""
        file_types = tuple(payload.get("file_types") or ())
        kwargs = {
            "directory": default_path,
            "allow_multiple": mode == "open_files",
        }
        if file_types:
            kwargs["file_types"] = file_types
        if mode == "save_file":
            kwargs["save_filename"] = default_path

        try:
            selected = window.create_file_dialog(dialog_type, **kwargs)
        except TypeError:
            # 部分 pywebview 版本不接受 title/directory 之外的扩展参数。
            selected = window.create_file_dialog(dialog_type)
        paths = _normalize_file_dialog_paths(selected)
        return {
            "status": "selected" if paths else "cancelled",
            "mode": mode,
            "paths": paths,
        }

    return provider


def _resolve_file_dialog_type(webview: Any, mode: str):
    if mode == "open_folder":
        return getattr(webview, "FOLDER_DIALOG", "folder")
    if mode == "save_file":
        return getattr(webview, "SAVE_DIALOG", "save")
    return getattr(webview, "OPEN_DIALOG", "open")


def _normalize_file_dialog_paths(selected: Any) -> list[str]:
    if selected is None:
        return []
    if isinstance(selected, (str, Path)):
        return [str(selected)]
    return [str(path) for path in selected if path]


def _build_open_path_provider(window_ref: dict[str, Any]):
    def provider(payload: dict) -> dict:
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("field must be a non-empty string: path")
        resolved_path = Path(raw_path).expanduser().resolve()
        if not resolved_path.exists():
            raise ValueError("path does not exist")

        os.startfile(str(resolved_path))  # type: ignore[attr-defined]

        return {
            "status": "opened",
            "path": str(resolved_path),
            "target_kind": "directory" if resolved_path.is_dir() else "file",
        }

    return provider
