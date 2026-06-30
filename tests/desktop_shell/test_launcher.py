from pathlib import Path
import json
import urllib.request

import pytest

from weconduct.desktop_shell.launcher import (
    DesktopEnvironmentProbeResult,
    DesktopShellDependencyError,
    DesktopShellOptions,
    launch_limited_browser_session,
    launch_desktop_shell,
    probe_desktop_environment,
    resolve_default_workspace_state_path,
    shutdown_limited_browser_session,
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
        self.evaluate_js_calls: list[str] = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.file_dialog_requests.append({"dialog_type": dialog_type, **kwargs})
        return ("I:\\picked\\graph.json",)

    def evaluate_js(self, script: str):
        self.evaluate_js_calls.append(script)
        return None


def _build_ui_dist(tmp_path: Path) -> Path:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html></html>",
        encoding="utf-8",
    )
    return ui_dist_path


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
            preferences_path=tmp_path / "state" / "preferences.json",
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
            preferences_path=tmp_path / "state" / "preferences.json",
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


def test_launch_desktop_shell_exposes_host_open_path_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html></html>",
        encoding="utf-8",
    )
    fake_webview = FakeWebView()
    project_dir = tmp_path / "demo-project"
    project_dir.mkdir()
    opened_paths: list[str] = []

    monkeypatch.setattr(
        "weconduct.desktop_shell.launcher.os.startfile",
        lambda path: opened_paths.append(path),
    )

    def post_open_path_during_window_lifetime() -> None:
        fake_webview.started = True
        base_url = fake_webview.created_windows[0]["url"]
        request = urllib.request.Request(
            f"{base_url}/api/host/open-path",
            data=json.dumps({"path": str(project_dir)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            fake_webview.open_path_response = json.loads(response.read().decode("utf-8"))

    fake_webview.start = post_open_path_during_window_lifetime

    launch_desktop_shell(
        DesktopShellOptions(
            host="127.0.0.1",
            port=0,
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=tmp_path / "state" / "preferences.json",
            ui_dist_path=ui_dist_path,
        ),
        webview_module=fake_webview,
    )

    assert fake_webview.open_path_response == {
        "status": "opened",
        "path": str(project_dir.resolve()),
        "target_kind": "directory",
    }
    assert opened_paths == [str(project_dir.resolve())]
    assert fake_webview.window.evaluate_js_calls == []


def test_launch_desktop_shell_reports_missing_pywebview(tmp_path: Path) -> None:
    with pytest.raises(DesktopShellDependencyError, match="pywebview"):
        launch_desktop_shell(
            DesktopShellOptions(
                workspace_state_path=tmp_path / "state" / "workspace-state.json",
                preferences_path=tmp_path / "state" / "preferences.json",
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


def test_limited_browser_session_reuses_existing_server(tmp_path: Path) -> None:
    shutdown_limited_browser_session()
    session = launch_limited_browser_session(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "state" / "workspace-state.json",
        preferences_path=tmp_path / "state" / "preferences.json",
        ui_dist_path=_build_ui_dist(tmp_path),
    )
    reopened = launch_limited_browser_session(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "state" / "workspace-state.json",
        preferences_path=tmp_path / "state" / "preferences.json",
        ui_dist_path=_build_ui_dist(tmp_path),
    )

    assert reopened.base_url == session.base_url
    assert reopened.server_id == session.server_id
    shutdown_limited_browser_session()


def test_limited_browser_session_exposes_open_path_provider_without_webview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shutdown_limited_browser_session()
    session = launch_limited_browser_session(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "state" / "workspace-state.json",
        preferences_path=tmp_path / "state" / "preferences.json",
        ui_dist_path=_build_ui_dist(tmp_path),
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    opened_paths: list[str] = []

    monkeypatch.setattr(
        "weconduct.desktop_shell.launcher.os.startfile",
        lambda path: opened_paths.append(path),
    )

    request = urllib.request.Request(
        f"{session.base_url}/api/host/open-path",
        data=json.dumps({"path": str(project_dir)}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))

    assert payload["status"] == "opened"
    assert opened_paths == [str(project_dir.resolve())]
    shutdown_limited_browser_session()


def test_probe_desktop_environment_returns_missing_runtime_when_checker_reports_missing() -> None:
    result = probe_desktop_environment(
        runtime_checker=lambda: (False, "webview2 runtime missing"),
    )

    assert result.status == "missing_runtime"
    assert "webview2" in result.message.lower()


def test_launch_desktop_shell_returns_limited_prompt_state_when_runtime_missing(
    tmp_path: Path,
) -> None:
    shutdown_limited_browser_session()
    result = launch_desktop_shell(
        DesktopShellOptions(
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=tmp_path / "state" / "preferences.json",
            ui_dist_path=_build_ui_dist(tmp_path),
        ),
        webview_module=FakeWebView(),
        desktop_environment_probe=lambda: DesktopEnvironmentProbeResult(
            status="missing_runtime",
            message="missing webview2",
        ),
        fallback_prompt_runner=lambda payload: {"action": "dismissed"},
    )

    assert result["status"] == "desktop_runtime_missing"
    assert result["desktop_environment"]["status"] == "missing_runtime"


def test_missing_runtime_prompt_can_start_limited_mode_and_then_open_program(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shutdown_limited_browser_session()
    opened_urls: list[str] = []
    monkeypatch.setattr(
        "weconduct.desktop_shell.launcher._open_url_in_default_browser",
        lambda url: opened_urls.append(url),
    )
    prompt_calls: list[dict] = []

    def prompt_runner(payload: dict) -> dict:
        prompt_calls.append(payload)
        if len(prompt_calls) == 1:
            return {"action": "start_limited_browser"}
        return {"action": "dismissed"}

    first = launch_desktop_shell(
        DesktopShellOptions(
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=tmp_path / "state" / "preferences.json",
            ui_dist_path=_build_ui_dist(tmp_path),
        ),
        webview_module=FakeWebView(),
        desktop_environment_probe=lambda: DesktopEnvironmentProbeResult(
            status="missing_runtime",
            message="missing webview2",
        ),
        fallback_prompt_runner=prompt_runner,
    )
    second = launch_desktop_shell(
        DesktopShellOptions(
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=tmp_path / "state" / "preferences.json",
            ui_dist_path=_build_ui_dist(tmp_path),
        ),
        webview_module=FakeWebView(),
        desktop_environment_probe=lambda: DesktopEnvironmentProbeResult(
            status="missing_runtime",
            message="missing webview2",
        ),
        fallback_prompt_runner=prompt_runner,
    )

    assert first["status"] == "limited_browser_running"
    assert second["status"] == "limited_browser_running"
    assert opened_urls == []
    shutdown_limited_browser_session()


def test_missing_runtime_prompt_can_open_program_in_same_launch_cycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    shutdown_limited_browser_session()
    opened_urls: list[str] = []
    monkeypatch.setattr(
        "weconduct.desktop_shell.launcher._open_url_in_default_browser",
        lambda url: opened_urls.append(url),
    )
    prompt_calls: list[dict] = []

    def prompt_runner(payload: dict) -> dict:
        prompt_calls.append(payload)
        if len(prompt_calls) == 1:
            assert payload["limited_browser"]["status"] == "stopped"
            return {"action": "start_limited_browser"}
        assert payload["limited_browser"]["status"] == "running"
        assert payload["limited_browser"]["base_url"].startswith("http://127.0.0.1:")
        return {"action": "open_program"}

    result = launch_desktop_shell(
        DesktopShellOptions(
            workspace_state_path=tmp_path / "state" / "workspace-state.json",
            preferences_path=tmp_path / "state" / "preferences.json",
            ui_dist_path=_build_ui_dist(tmp_path),
        ),
        webview_module=FakeWebView(),
        desktop_environment_probe=lambda: DesktopEnvironmentProbeResult(
            status="missing_runtime",
            message="missing webview2",
        ),
        fallback_prompt_runner=prompt_runner,
    )

    assert len(prompt_calls) == 2
    assert result["status"] == "limited_browser_opened"
    assert opened_urls == [result["base_url"]]
    shutdown_limited_browser_session()


def test_limited_browser_session_exposes_mode_metadata(tmp_path: Path) -> None:
    shutdown_limited_browser_session()
    session = launch_limited_browser_session(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "state" / "workspace-state.json",
        preferences_path=tmp_path / "state" / "preferences.json",
        ui_dist_path=_build_ui_dist(tmp_path),
    )

    with urllib.request.urlopen(f"{session.base_url}/api/health") as response:
        payload = json.loads(response.read().decode("utf-8"))

    assert payload["ui_hosting"]["ui_mode"] == "limited_browser"
    shutdown_limited_browser_session()
