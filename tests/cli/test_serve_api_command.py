import os
from pathlib import Path
import signal
import subprocess
import sys


def test_cli_serve_api_starts_server_and_prints_runtime_binding(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "state" / "workspace-state.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "weconduct.cli.main",
            "serve-api",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--workspace-state-path",
            str(workspace_state_path),
            "--ui-dist-path",
            str(ui_dist_path),
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        startup_line = process.stdout.readline().strip()

        assert "WeConduct API server listening on http://127.0.0.1:" in startup_line
        assert str(workspace_state_path) in startup_line
        assert str(ui_dist_path) in startup_line
    finally:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
