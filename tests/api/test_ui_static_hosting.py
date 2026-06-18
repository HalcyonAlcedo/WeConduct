import threading
import urllib.request
from pathlib import Path
from socketserver import TCPServer

from weconduct.api.server import WeConductApiHandler


class UiHostingTestServer(TCPServer):
    allow_reuse_address = True


def _start_test_server(
    *,
    workspace_state_path: Path,
    ui_dist_path: Path | None = None,
) -> tuple[UiHostingTestServer, threading.Thread]:
    server = UiHostingTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = workspace_state_path
    if ui_dist_path is not None:
        server.ui_dist_path = ui_dist_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_http_server_serves_ui_index_from_configured_dist_path(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html><body><div id='app'>WeConduct UI</div></body></html>",
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=tmp_path / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/") as response:
            body = response.read().decode("utf-8")
            content_type = response.headers["Content-Type"]

        assert response.status == 200
        assert "text/html" in content_type
        assert "WeConduct UI" in body
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_ui_static_assets_from_configured_dist_path(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    assets_path = ui_dist_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html><body><script src='/assets/app.js'></script></body></html>",
        encoding="utf-8",
    )
    (assets_path / "app.js").write_text("console.log('weconduct-ui');", encoding="utf-8")
    server, thread = _start_test_server(
        workspace_state_path=tmp_path / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/assets/app.js") as response:
            body = response.read().decode("utf-8")
            content_type = response.headers["Content-Type"]

        assert response.status == 200
        assert "javascript" in content_type
        assert "weconduct-ui" in body
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_falls_back_to_ui_index_for_unknown_frontend_route(tmp_path: Path) -> None:
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text(
        "<!doctype html><html><body><div id='app'>SPA Shell</div></body></html>",
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=tmp_path / "workspace-state.json",
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/workbench/summary") as response:
            body = response.read().decode("utf-8")

        assert response.status == 200
        assert "SPA Shell" in body
    finally:
        server.shutdown()
        server.server_close()
