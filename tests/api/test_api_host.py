from pathlib import Path

from weconduct.api import build_api_server


def test_build_api_server_applies_host_port_and_workspace_state_path(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "runtime" / "workspace-state.json"
    ui_dist_path = tmp_path / "ui-dist"

    server = build_api_server(
        host="127.0.0.1",
        port=0,
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
        assert server.workspace_state_path == workspace_state_path
        assert server.ui_dist_path == ui_dist_path
    finally:
        server.server_close()
