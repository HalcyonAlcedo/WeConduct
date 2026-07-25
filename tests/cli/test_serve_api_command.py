from __future__ import annotations

import sys

from weconduct.cli import main as cli_main


class _FakeApiServer:
    server_address = ("0.0.0.0", 8000)
    workspace_state_path = "workspace-state.json"
    ui_dist_path = "ui-dist"

    def serve_forever(self) -> None:
        return None

    def server_close(self) -> None:
        return None


def test_serve_api_passes_explicit_non_loopback_confirmation(monkeypatch, capsys) -> None:
    captured_arguments: dict[str, object] = {}

    def build_server(**kwargs: object) -> _FakeApiServer:
        captured_arguments.update(kwargs)
        return _FakeApiServer()

    monkeypatch.setattr(cli_main, "build_api_server", build_server)
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "serve-api", "--host", "0.0.0.0", "--allow-non-loopback"],
    )

    assert cli_main.main() == 0
    assert captured_arguments["host"] == "0.0.0.0"
    assert captured_arguments["allow_non_loopback"] is True
    assert "firewall" in capsys.readouterr().err.lower()
