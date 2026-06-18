import sys
from pathlib import Path

from weconduct.cli import main as cli_main
from weconduct.desktop_shell import DesktopShellDependencyError


def test_cli_desktop_shell_passes_arguments_to_launcher(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    captured_options = {}

    def fake_launch_desktop_shell(options):
        captured_options["options"] = options
        return {"status": "closed", "base_url": "http://127.0.0.1:43210"}

    monkeypatch.setattr(cli_main, "launch_desktop_shell", fake_launch_desktop_shell)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "desktop-shell",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--workspace-state-path",
            str(tmp_path / "state" / "workspace-state.json"),
            "--ui-dist-path",
            str(tmp_path / "ui-dist"),
            "--title",
            "WeConduct",
            "--width",
            "1400",
            "--height",
            "900",
        ],
    )

    exit_code = cli_main.main()
    output = capsys.readouterr().out
    options = captured_options["options"]

    assert exit_code == 0
    assert "WeConduct desktop shell closed" in output
    assert options.host == "127.0.0.1"
    assert options.port == 0
    assert options.workspace_state_path == (
        tmp_path / "state" / "workspace-state.json"
    ).resolve()
    assert options.ui_dist_path == (tmp_path / "ui-dist").resolve()
    assert options.title == "WeConduct"
    assert options.width == 1400
    assert options.height == 900


def test_cli_desktop_shell_returns_one_when_pywebview_is_missing(
    monkeypatch,
    capsys,
) -> None:
    def fake_launch_desktop_shell(options):
        raise DesktopShellDependencyError("pywebview is required")

    monkeypatch.setattr(cli_main, "launch_desktop_shell", fake_launch_desktop_shell)
    monkeypatch.setattr(sys, "argv", ["weconduct", "desktop-shell"])

    exit_code = cli_main.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "pywebview is required" in captured.err
