import json
import sys
from pathlib import Path

from weconduct.cli import main as cli_main


def test_cli_preview_smoke_prints_json_report_and_returns_zero(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html><body>preview</body></html>", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weconduct",
            "preview-smoke",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--workspace-state-path",
            str(tmp_path / "state" / "workspace-state.json"),
            "--ui-dist-path",
            str(ui_dist_path),
        ],
    )

    exit_code = cli_main.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["checks"]["snapshot"]["ok"] is True
    assert payload["checks"]["host_info"]["ok"] is True
