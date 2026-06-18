from pathlib import Path

from weconduct.application.preview_smoke import run_preview_smoke


def test_preview_smoke_runs_full_preview_gate_successfully(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html><body>preview</body></html>", encoding="utf-8")

    result = run_preview_smoke(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )

    assert result["status"] == "passed"
    assert result["base_url"].startswith("http://127.0.0.1:")
    assert result["checks"]["root_ui_served"]["ok"] is True
    assert result["checks"]["graph_saved"]["ok"] is True
    assert result["checks"]["graph_compiled"]["ok"] is True
    assert result["checks"]["runtime_prepare"]["ok"] is True
    assert result["checks"]["debug_prepare"]["ok"] is True
    assert result["checks"]["host_info"]["ok"] is True


def test_preview_smoke_reports_failure_when_ui_dist_entrypoint_is_missing(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "missing-ui-dist"

    result = run_preview_smoke(
        host="127.0.0.1",
        port=0,
        workspace_state_path=tmp_path / "runtime" / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )

    assert result["status"] == "failed"
    assert result["checks"]["root_ui_served"]["ok"] is False
    assert "404" in result["checks"]["root_ui_served"]["detail"]


def test_preview_smoke_is_repeatable_with_same_workspace_state_file(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html><body>preview</body></html>", encoding="utf-8")
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"

    first = run_preview_smoke(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )
    second = run_preview_smoke(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )

    assert first["status"] == "passed"
    assert second["status"] == "passed"
    assert first["checks"]["graph_saved"]["ok"] is True
    assert second["checks"]["graph_saved"]["ok"] is True
