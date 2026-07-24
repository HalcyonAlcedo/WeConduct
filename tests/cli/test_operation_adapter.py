from __future__ import annotations

import json
import sys

from weconduct.cli.main import main


def test_cli_operation_uses_operation_registry_and_json_contract(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "operation", "host.capabilities", "--payload", "{}"],
    )

    exit_code = main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation_id"] == "host.capabilities"
    assert "capabilities" in payload["result"]


def test_cli_operation_returns_nonzero_for_invalid_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "operation", "project.create", "--payload", "{}"],
    )

    exit_code = main()
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert payload["error_code"] == "operation.input_invalid"
