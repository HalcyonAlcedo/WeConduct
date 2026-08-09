from __future__ import annotations

import errno
import sys

import pytest

from weconduct.api.server import ExternalApiBindError
from weconduct.cli import main as cli_main


class _FakeApiServer:
    server_address = ("0.0.0.0", 8000)
    workspace_state_path = "workspace-state.json"
    ui_dist_path = "ui-dist"
    api_token = "generated-token-for-test"

    def serve_forever(self) -> None:
        return None

    def server_close(self) -> None:
        return None


class _FailingServeApiServer(_FakeApiServer):
    def serve_forever(self) -> None:
        raise OSError(errno.EINVAL, "Invalid argument")


def test_cli_initializes_multiprocessing_before_parsing_arguments(monkeypatch) -> None:
    calls: list[None] = []

    monkeypatch.setattr(
        cli_main,
        "_initialize_multiprocessing",
        lambda: calls.append(None),
    )
    monkeypatch.setattr(sys, "argv", ["weconduct", "--help"])

    with pytest.raises(SystemExit, match="0"):
        cli_main.main()

    assert calls == [None]


def test_serve_api_passes_explicit_non_loopback_confirmation(monkeypatch, capsys) -> None:
    captured_arguments: dict[str, object] = {}

    def build_server(**kwargs: object) -> _FakeApiServer:
        captured_arguments.update(kwargs)
        server = _FakeApiServer()
        server.api_token = str(kwargs["api_token"])
        return server

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


def test_serve_api_generates_and_prints_ephemeral_token_when_argument_is_missing(
    monkeypatch,
    capsys,
) -> None:
    captured_arguments: dict[str, object] = {}

    def build_server(**kwargs: object) -> _FakeApiServer:
        captured_arguments.update(kwargs)
        server = _FakeApiServer()
        server.api_token = str(kwargs["api_token"])
        return server

    monkeypatch.setattr(cli_main, "build_api_server", build_server)
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "serve-api", "--host", "127.0.0.1", "--port", "0"],
    )

    assert cli_main.main() == 0

    output = capsys.readouterr().out
    generated_token = captured_arguments["api_token"]
    assert isinstance(generated_token, str)
    assert generated_token.strip()
    assert len(generated_token) >= 43
    assert output.count(generated_token) == 1
    assert "仅本次启动有效" in output


def test_serve_api_does_not_print_explicit_token(monkeypatch, capsys) -> None:
    explicit_token = "explicit-cli-token"

    def build_server(**kwargs: object) -> _FakeApiServer:
        assert kwargs["api_token"] == explicit_token
        return _FakeApiServer()

    monkeypatch.setattr(cli_main, "build_api_server", build_server)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "serve-api",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--api-token",
            explicit_token,
        ],
    )

    assert cli_main.main() == 0
    assert explicit_token not in capsys.readouterr().out


def test_serve_api_bind_error_does_not_crash_when_stderr_is_unavailable(monkeypatch) -> None:
    def raise_bind_error(**kwargs: object) -> _FakeApiServer:
        raise ExternalApiBindError(
            host="127.0.0.1",
            configured_port=63241,
            cause=OSError(errno.EADDRINUSE, "address already in use"),
        )

    monkeypatch.setattr(cli_main, "build_api_server", raise_bind_error)
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "serve-api", "--host", "127.0.0.1", "--port", "63241"],
    )
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)

    assert cli_main.main() == 1


def test_serve_api_raw_os_error_does_not_escape_cli_entrypoint(monkeypatch, capsys) -> None:
    def raise_raw_os_error(**kwargs: object) -> _FakeApiServer:
        raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(cli_main, "build_api_server", raise_raw_os_error)
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "serve-api", "--host", "127.0.0.1", "--port", "63241"],
    )

    assert cli_main.main() == 1
    assert "Invalid argument" in capsys.readouterr().err


def test_serve_api_serve_forever_os_error_returns_failure(monkeypatch, capsys) -> None:
    def build_server(**kwargs: object) -> _FailingServeApiServer:
        return _FailingServeApiServer()

    monkeypatch.setattr(cli_main, "build_api_server", build_server)
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "serve-api", "--host", "127.0.0.1", "--port", "63241"],
    )

    assert cli_main.main() == 1
    assert "Invalid argument" in capsys.readouterr().err
