from pathlib import Path

from weconduct.desktop_shell.launcher import (
    launch_desktop_shell,
    resolve_default_preferences_path,
    DesktopShellOptions,
)


def test_default_preferences_path_uses_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    path = resolve_default_preferences_path()

    assert path == tmp_path / "LocalAppData" / "WeConduct" / "preferences.json"


def test_launch_desktop_shell_reports_preferences_path(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    preferences_path = tmp_path / "state" / "preferences.json"
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    preferences_path.write_text(
        """
{
  "preferences_file_version": 1,
  "program_settings": {
    "language": "zh-CN",
    "resource_language": "zh-CN",
    "theme": "light",
    "default_window_size": {
      "width": 1280,
      "height": 720
    },
    "startup_action": "restore_last_workspace",
    "default_project_directory": null,
    "recent_project_limit": 10,
    "preferences_auto_save": true,
    "font_scale": 100
  },
  "compile_settings": {
    "default_source_kind": "graph_workspace",
    "diagnostic_level": "error",
    "block_on_disabled_components": true,
    "allow_degraded_compile": true,
    "stop_on_first_error": true,
    "emit_runtime_plan": true,
    "emit_debug_plan": true
  },
  "security_settings": {
    "confirm_high_risk_actions": true,
    "allow_external_programs": false,
    "allow_file_access": true,
    "allow_browser_executor": false,
    "allow_local_network_access": false
  },
  "python_runtime_settings": {
    "python_executable_path": null,
    "timeout_seconds": 60,
    "sandbox_mode": "restricted",
    "capture_stdout_stderr": true
  },
  "graph_settings": {
    "auto_sync_mode": "responsive",
    "show_node_id_on_node": true,
    "show_disabled_resource_badge": true,
    "snap_to_grid": true,
    "grid_enabled": true,
    "auto_open_node_on_drop": true,
    "confirm_delete_node": true,
    "show_inline_config_summary": true
  },
  "other_settings": {
    "workspace_draft_recovery_enabled": true,
    "workspace_draft_recovery_ttl_minutes": 30
  }
}
""".strip(),
        encoding="utf-8",
    )

    class FakeWebView:
        def __init__(self) -> None:
            self.window = object()
            self.created_width = None
            self.created_height = None

        def create_window(self, title, url, width, height):
            self.created_width = width
            self.created_height = height
            return self.window

        def start(self):
            return None

    fake_webview = FakeWebView()

    result = launch_desktop_shell(
        DesktopShellOptions(
            host="127.0.0.1",
            port=0,
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=preferences_path,
            ui_dist_path=ui_dist_path,
        ),
        webview_module=fake_webview,
    )

    assert result["preferences_path"].endswith("preferences.json")
    assert fake_webview.created_width == 1280
    assert fake_webview.created_height == 720
