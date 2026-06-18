from pathlib import Path
import json
import urllib.request

import pytest

from weconduct.desktop_shell.launcher import (
    DesktopShellDependencyError,
    DesktopShellOptions,
    launch_desktop_shell,
    resolve_default_workspace_state_path,
)


class FakeWebView:
    def __init__(self) -> None:
        self.created_windows: list[dict] = []
        self.started = False
        self.window = FakeWindow()

    def create_window(self, title: str, url: str, width: int, height: int):
        self.created_windows.append(
            {"title": title, "url": url, "width": width, "height": height}
        )
        return self.window

    def start(self) -> None:
        self.started = True


class FakeWindow:
    def __init__(self) -> None:
        self.file_dialog_requests: list[dict] = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.file_dialog_requests.append({"dialog_type": dialog_type, **kwargs})
        return ("I:\\picked\\graph.json",)


def test_launch_desktop_shell_starts_api_and_opens_window(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html></html>",
        encoding="utf-8",
    )
    fake_webview = FakeWebView()

    result = launch_desktop_shell(
        DesktopShellOptions(
            host="127.0.0.1",
            port=0,
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            ui_dist_path=ui_dist_path,
            title="WeConduct",
            width=1280,
            height=800,
        ),
        webview_module=fake_webview,
    )

    assert result["status"] == "closed"
    assert result["base_url"].startswith("http://127.0.0.1:")
    assert fake_webview.started is True
    assert fake_webview.created_windows == [
        {
            "title": "WeConduct",
            "url": result["base_url"],
            "width": 1280,
            "height": 800,
        }
    ]


def test_launch_desktop_shell_exposes_host_file_dialog_provider(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html></html>",
        encoding="utf-8",
    )
    fake_webview = FakeWebView()

    def post_file_dialog_during_window_lifetime() -> None:
        fake_webview.started = True
        base_url = fake_webview.created_windows[0]["url"]
        request = urllib.request.Request(
            f"{base_url}/api/host/file-dialog",
            data=json.dumps(
                {
                    "mode": "open_file",
                    "title": "选择节点图",
                    "file_types": ["JSON Files (*.json)"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            fake_webview.file_dialog_response = json.loads(response.read().decode("utf-8"))

    fake_webview.start = post_file_dialog_during_window_lifetime

    launch_desktop_shell(
        DesktopShellOptions(
            host="127.0.0.1",
            port=0,
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            ui_dist_path=ui_dist_path,
        ),
        webview_module=fake_webview,
    )

    assert fake_webview.file_dialog_response == {
        "status": "selected",
        "mode": "open_file",
        "paths": ["I:\\picked\\graph.json"],
    }
    assert fake_webview.window.file_dialog_requests == [
        {
            "dialog_type": "open",
            "directory": "",
            "allow_multiple": False,
            "file_types": ("JSON Files (*.json)",),
        }
    ]


def test_launch_desktop_shell_reports_missing_pywebview(tmp_path: Path) -> None:
    with pytest.raises(DesktopShellDependencyError, match="pywebview"):
        launch_desktop_shell(
            DesktopShellOptions(
                workspace_state_path=tmp_path / "state" / "workspace-state.json",
                ui_dist_path=tmp_path / "ui-dist",
            ),
            webview_module=None,
        )


def test_default_workspace_state_path_uses_local_app_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    path = resolve_default_workspace_state_path()

    assert path == (
        tmp_path
        / "LocalAppData"
        / "WeConduct"
        / ""
        / "workspace-state.json"
    )
