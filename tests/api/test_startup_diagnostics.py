import json
from pathlib import Path
from threading import Thread
import urllib.error
import urllib.request

from weconduct.api import build_api_server
from weconduct.api.server import (
    build_startup_diagnostics,
    recover_startup_target,
)


def _get_json(url: str, *, api_token: str | None = None) -> dict:
    headers = {"X-WeConduct-Token": api_token} if api_token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, *, api_token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["X-WeConduct-Token"] = api_token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_invalid_workspace_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Missing required keys (last_compile, compile_history, workbench) → invalid.
    path.write_text(json.dumps({"workspace_state_version": 1}), encoding="utf-8")


def _write_legacy_preferences(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 0.8.0-style legacy format (top-level security_settings) → incompatible.
    path.write_text(
        json.dumps({"preferences_file_version": 1, "security_settings": {}}),
        encoding="utf-8",
    )


# ===== Unit-level (pure function) =====


def test_build_startup_diagnostics_classifies_workspace_state_fault(tmp_path: Path) -> None:
    prefs = tmp_path / "preferences.json"
    ws = tmp_path / "workspace-state.json"
    _write_invalid_workspace_state(ws)
    _write_legacy_preferences(prefs)

    report = build_startup_diagnostics(prefs, ws)

    assert report["overall_severity"] == "fault"
    assert "workspace_state" in report["recoverable_targets"]
    ws_sub = next(s for s in report["subsystems"] if s["subsystem"] == "workspace_state")
    assert ws_sub["severity"] == "fault"
    assert ws_sub["error_code"] == "workspace_state_invalid"
    assert ws_sub["location"] == str(ws)
    prefs_sub = next(s for s in report["subsystems"] if s["subsystem"] == "preferences")
    assert prefs_sub["severity"] == "anomaly"


def test_build_startup_diagnostics_all_clean(tmp_path: Path) -> None:
    report = build_startup_diagnostics(
        tmp_path / "preferences.json", tmp_path / "workspace-state.json"
    )
    assert report["overall_severity"] == "ok"
    assert report["recoverable_targets"] == []


def test_recover_workspace_state_backs_up_and_removes(tmp_path: Path) -> None:
    prefs = tmp_path / "preferences.json"
    ws = tmp_path / "workspace-state.json"
    _write_invalid_workspace_state(ws)

    result = recover_startup_target("workspace_state", prefs, ws)

    assert result["status"] == "reset"
    assert result["backup_path"] is not None
    assert Path(result["backup_path"]).exists()
    # Corrupt file removed so the service rebuilds a default on next load.
    assert not ws.exists()
    # Re-diagnosing is now clean.
    report = build_startup_diagnostics(prefs, ws)
    assert report["overall_severity"] == "ok"


def test_recover_preferences_resets_to_current_format(tmp_path: Path) -> None:
    prefs = tmp_path / "preferences.json"
    _write_legacy_preferences(prefs)

    result = recover_startup_target("preferences", prefs)

    assert result["status"] == "reset"
    assert Path(result["backup_path"]).exists()
    payload = json.loads(prefs.read_text(encoding="utf-8"))
    assert payload["configuration_format_version"] == 1
    assert payload["scope"] == "program"


# ===== HTTP endpoint integration =====


def test_startup_diagnostics_endpoint_reachable_when_service_is_dead(tmp_path: Path) -> None:
    ws = tmp_path / "runtime" / "workspace-state.json"
    prefs = tmp_path / "runtime" / "preferences.json"
    _write_invalid_workspace_state(ws)

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=ws,
        preferences_path=prefs,
        ui_dist_path=tmp_path / "ui-dist",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

        # Sanity: the normal snapshot endpoint fails because the service can't build.
        try:
            _get_json(f"{base_url}/api/workbench/snapshot", api_token=server.api_token)
            raise AssertionError("snapshot should have failed with invalid workspace state")
        except urllib.error.HTTPError as exc:
            assert exc.code == 500

        # But diagnostics stays reachable and explains the fault.
        report = _get_json(f"{base_url}/api/startup/diagnostics", api_token=server.api_token)
        assert report["overall_severity"] == "fault"
        assert "workspace_state" in report["recoverable_targets"]

        # /api/health degrades gracefully (HTTP 200) instead of a bare error.
        health = _get_json(f"{base_url}/api/health", api_token=server.api_token)
        assert health["status"] == "degraded"
        assert health["startup_diagnostics"]["overall_severity"] == "fault"

        # Recover, then the service can build and snapshot succeeds.
        recover = _post_json(f"{base_url}/api/startup/recover", {}, api_token=server.api_token)
        assert recover["status"] == "recovered"
        assert any(r["target"] == "workspace_state" for r in recover["results"])

        snapshot = _get_json(f"{base_url}/api/workbench/snapshot", api_token=server.api_token)
        assert "workbench" in snapshot
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
