import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Callable
import zipfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from openpyxl import Workbook
import pytest

from weconduct.api.server import WeConductApiHandler
from weconduct.packaging.msgpack_codec import packb, unpackb


class ApiTestServer(TCPServer):
    allow_reuse_address = True


class RuntimeEchoHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/echo":
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            response_body = json.dumps(
                {
                    "ok": True,
                    "method": "POST",
                    "body": json.loads(raw_body.decode("utf-8")),
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class RuntimeEchoServer(TCPServer):
    allow_reuse_address = True


class BrowserMockSiteHandler(BaseHTTPRequestHandler):
    clicked = False
    last_form_value = ""
    ambiguous_last_action = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/dashboard":
            body = b"""
<!doctype html>
<html>
  <body>
    <div id="dashboard-status">dashboard-ready</div>
  </body>
</html>
""".strip()
        elif self.path == "/frame":
            body = b"""
<!doctype html>
<html>
  <body>
    <div id="frame-status">frame-ready</div>
    <button id="frame-submit" type="button" onclick="window.location='/frame-details'">Open Frame Details</button>
  </body>
</html>
""".strip()
        elif self.path == "/frame-details":
            body = b"""
<!doctype html>
<html>
  <body>
    <div id="frame-details">frame-details-ready</div>
  </body>
</html>
""".strip()
        elif self.path.startswith("/ambiguous"):
            body = f"""
<!doctype html>
<html>
  <body>
    <div id="ambiguous-status">{self.ambiguous_last_action or "ready"}</div>
    <form method="post" action="/submit-main">
      <button class="btn-success" type="submit">提交表单</button>
    </form>
    <form method="post" action="/submit-alert">
      <button class="btn-success" type="submit">Alert 对话框</button>
    </form>
    <form method="post" action="/submit-download">
      <button class="btn-success" type="submit">下载 TXT 文件</button>
    </form>
  </body>
</html>
""".strip().encode("utf-8")
        else:
            body = f"""
<!doctype html>
<html>
  <body>
    <form method="post" action="/submit">
      <input id="name" name="name" value="{self.last_form_value}">
      <button id="submit" type="submit">Submit</button>
    </form>
    <select id="city">
      <option value="">pick</option>
      <option value="beijing">Beijing</option>
      <option value="shanghai">Shanghai</option>
    </select>
    <div id="hover-target" onmouseover="document.getElementById('hover-result').style.display='block'">hover-me</div>
    <div id="hover-result" style="display:none">hovered</div>
    <button id="go-dashboard" type="button" onclick="window.location='/dashboard'">Go Dashboard</button>
    <iframe id="content-frame" name="contentFrame" src="/frame"></iframe>
    <div id="status">{"clicked" if self.clicked else "ready"}</div>
  </body>
</html>
""".strip().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path in {"/submit-main", "/submit-alert", "/submit-download"}:
            action = self.path.removeprefix("/submit-")
            type(self).ambiguous_last_action = action
            self.send_response(303)
            self.send_header("Location", "/ambiguous")
            self.end_headers()
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        form_value = ""
        for part in raw_body.split("&"):
            if part.startswith("name="):
                form_value = part.split("=", 1)[1].replace("+", " ")
        type(self).clicked = True
        type(self).last_form_value = form_value
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class BrowserMockSiteServer(TCPServer):
    allow_reuse_address = True


def _rewrite_wcrun_manifest(
    package_path: Path,
    mutate_manifest: Callable[[dict], None],
) -> None:
    with zipfile.ZipFile(package_path, mode="r") as archive:
        package_contents = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    manifest_payload = unpackb(package_contents["manifest.msgpack"])
    mutate_manifest(manifest_payload)
    package_contents["manifest.msgpack"] = packb(manifest_payload)
    checksums_payload = {
        "checksum_schema_version": 1,
        "algorithm": "sha256",
        "entries": [
            {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
            for path, content in sorted(package_contents.items(), key=lambda item: item[0])
        ],
    }
    temp_path = package_path.with_suffix(f"{package_path.suffix}.tmp")
    with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(package_contents.items(), key=lambda item: item[0]):
            archive.writestr(path, content)
        archive.writestr(
            "meta/checksums.json",
            json.dumps(checksums_payload, ensure_ascii=False, indent=2),
        )
    temp_path.replace(package_path)


def _rewrite_wcrun_project_settings(
    package_path: Path,
    mutate_project_settings: Callable[[dict], None],
) -> None:
    with zipfile.ZipFile(package_path, mode="r") as archive:
        package_contents = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "meta/checksums.json"
        }
    project_settings_payload = json.loads(package_contents["project-settings.json"].decode("utf-8"))
    mutate_project_settings(project_settings_payload)
    package_contents["project-settings.json"] = json.dumps(
        project_settings_payload,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    checksums_payload = {
        "checksum_schema_version": 1,
        "algorithm": "sha256",
        "entries": [
            {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
            for path, content in sorted(package_contents.items(), key=lambda item: item[0])
        ],
    }
    temp_path = package_path.with_suffix(f"{package_path.suffix}.tmp")
    with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(package_contents.items(), key=lambda item: item[0]):
            archive.writestr(path, content)
        archive.writestr(
            "meta/checksums.json",
            json.dumps(checksums_payload, ensure_ascii=False, indent=2),
        )
    temp_path.replace(package_path)


def _start_test_server(
    *,
    workspace_state_path: Path | None = None,
    preferences_path: Path | None = None,
    ui_dist_path: Path | None = None,
) -> tuple[ApiTestServer, threading.Thread]:
    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    if workspace_state_path is not None:
        server.workspace_state_path = workspace_state_path
    if preferences_path is not None:
        server.preferences_path = preferences_path
    if ui_dist_path is not None:
        server.ui_dist_path = ui_dist_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_runtime_echo_server() -> tuple[RuntimeEchoServer, threading.Thread]:
    server = RuntimeEchoServer(("127.0.0.1", 0), RuntimeEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _start_browser_mock_site_server() -> tuple[BrowserMockSiteServer, threading.Thread]:
    BrowserMockSiteHandler.clicked = False
    BrowserMockSiteHandler.last_form_value = ""
    BrowserMockSiteHandler.ambiguous_last_action = ""
    server = BrowserMockSiteServer(("127.0.0.1", 0), BrowserMockSiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _build_valid_graph_document_payload() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-1",
                "lowered_kind": "execution",
                "source_anchor_ref": "n1",
                "expansion_role": "action:request",
                "node_kind": "http.request",
                "ports": [
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "data",
                        "semantic_slot": "out.default",
                    }
                ],
            },
            {
                "node_id": "node-2",
                "lowered_kind": "execution",
                "source_anchor_ref": "n2",
                "expansion_role": "transform:map",
                "node_kind": "data.map",
                "ports": [
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "data",
                        "semantic_slot": "in.default",
                    }
                ],
            },
        ],
        "edges": [
            {
                "edge_id": "edge-1",
                "relation_layer": "data",
                "from_node_id": "node-1",
                "to_node_id": "node-2",
                "from_port_id": "out",
                "to_port_id": "in",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_ui_authoring_graph_document_payload() -> dict:
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "node-ui-1",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-ui-1",
                "expansion_role": "http.request",
                "display_name": "HTTP Request",
                "node_kind": "http.request",
                "position": {"x": 120, "y": 80},
            },
            {
                "node_id": "node-ui-2",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-node-ui-2",
                "expansion_role": "data.map",
                "display_name": "Data Map",
                "node_kind": "data.map",
                "position": {"x": 360, "y": 80},
            },
        ],
        "edges": [
            {
                "edge_id": "edge-ui-1",
                "relation_layer": "data",
                "from_node_id": "node-ui-1",
                "to_node_id": "node-ui-2",
            }
        ],
        "graph_effective_diagnostic_anchor_refs": [],
    }


def _build_ui_authoring_graph_document_payload_with_http_url(url: str) -> dict:
    payload = _build_ui_authoring_graph_document_payload()
    payload["nodes"][0]["node_config"] = {
        "method": "POST",
        "url": url,
        "body": {"ok": True},
    }
    return payload


def test_http_api_exposes_snapshot_and_compile(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.json"
    workspace_state_path = tmp_path / "workspace-state.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    source_file.write_text(
        '{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": str(source_file),
                "source_text": source_file.read_text(encoding="utf-8"),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            recent_snapshot = json.loads(response.read().decode("utf-8"))

        assert snapshot["project"]["loaded"] is True
        assert snapshot["project"]["project_id"] == "weconduct-workspace"
        assert snapshot["project"]["project_status"] == "ready"
        assert snapshot["project"]["workspace_root"] == str(Path(__file__).resolve().parents[2])
        assert snapshot["project"]["has_persisted_workspace_state"] is False
        assert snapshot["project"]["last_compile_status"] is None
        assert snapshot["project"]["last_runtime_status"] is None
        assert snapshot["project"]["last_debug_status"] is None
        assert snapshot["workbench"]["host_mode"] == "python_core"
        assert snapshot["workbench"]["workspace_session_id"].startswith("ws-")
        assert snapshot["workbench"]["service_started_at"]
        assert snapshot["workbench"]["compile_counter"] == 0
        assert snapshot["capabilities"]["graph_workspace_available"] is True
        assert snapshot["capabilities"]["runtime_available"] is True
        assert snapshot["capabilities"]["debug_available"] is True
        assert snapshot["entrypoints"]["graph_document"] == "/api/workbench/graph"
        assert snapshot["entrypoints"]["graph_validate_action"] == "/api/workbench/graph/validate"
        assert snapshot["entrypoints"]["graph_compile_action"] == "/api/workbench/graph/compile"
        assert snapshot["entrypoints"]["project_settings"] == "/api/workbench/project/settings"
        assert snapshot["entrypoints"]["project_runtime_defaults"] == "/api/workbench/project/runtime-defaults"
        assert snapshot["entrypoints"]["project_package_preflight_action"] == "/api/workbench/project/package/preflight"
        assert snapshot["entrypoints"]["project_package_build_action"] == "/api/workbench/project/package/build"
        assert snapshot["entrypoints"]["project_package_inspect"] == "/api/workbench/project/package/inspect"
        assert snapshot["entrypoints"]["project_package_load_action"] == "/api/workbench/project/package/load"
        assert snapshot["entrypoints"]["project_package_unload_action"] == "/api/workbench/project/package/unload"
        assert (
            snapshot["entrypoints"]["project_package_external_resource_bind_action"]
            == "/api/workbench/project/package/external-resources/bind"
        )
        assert snapshot["entrypoints"]["runtime_prepare_action"] == "/api/workbench/runtime/prepare"
        assert snapshot["entrypoints"]["debug_prepare_action"] == "/api/workbench/debug/prepare"
        assert snapshot["entrypoints"]["host_info"] == "/api/host/info"
        assert snapshot["ui_hosting"]["ui_hosted"] is True
        assert snapshot["ui_hosting"]["ui_dist_available"] is True
        assert snapshot["ui_hosting"]["ui_entrypoint"] == "/"
        assert snapshot["ui_hosting"]["ui_dist_path"] == str(ui_dist_path.resolve())
        assert snapshot["compiler"]["available_source_kinds"] == [
            "graph_workspace",
            "native_flow",
            "webcontrol_main_flow",
            "webcontrol_blueprint",
        ]
        assert snapshot["compiler"]["default_source_kind"] == "graph_workspace"
        assert snapshot["compiler"]["compile_history_limit"] == 5
        assert snapshot["compiler"]["source_templates"]["graph_workspace"]["entry_document"] == "graph:workspace"
        assert snapshot["compiler"]["source_templates"]["native_flow"]["entry_document"] == "examples/native-flow.json"
        assert (
            snapshot["compiler"]["source_templates"]["native_flow"]["source_text"]
            == '{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}'
        )
        assert (
            snapshot["compiler"]["source_templates"]["webcontrol_main_flow"]["entry_document"]
            == "examples/webcontrol-main-flow.json"
        )
        assert (
            snapshot["compiler"]["source_templates"]["webcontrol_blueprint"]["entry_document"]
            == "examples/webcontrol-blueprint.json"
        )
        assert snapshot["last_compile"] is None
        assert snapshot["compile_history"] == []
        assert result["status"] == "succeeded"
        assert result["view"]["status"] == "succeeded"
        assert result["view"]["graph_stats"]["node_count"] == 1
        assert result["view"]["duration_ms"] is not None
        assert isinstance(result["view"]["duration_ms"], int)
        assert result["view"]["duration_ms"] >= 0
        assert result["outcome"]["compilation_summary"]["duration_ms"] == result["view"]["duration_ms"]
        assert recent_snapshot["workbench"]["workspace_session_id"] == snapshot["workbench"]["workspace_session_id"]
        assert recent_snapshot["workbench"]["service_started_at"] == snapshot["workbench"]["service_started_at"]
        assert recent_snapshot["workbench"]["compile_counter"] == 1
        assert recent_snapshot["project"]["project_status"] == "ready"
        assert recent_snapshot["project"]["has_persisted_workspace_state"] is True
        assert recent_snapshot["project"]["last_compile_status"] == "succeeded"
        assert recent_snapshot["project"]["last_compile_request_sequence"] == 1
        assert recent_snapshot["last_compile"]["status"] == "succeeded"
        assert recent_snapshot["last_compile"]["request_sequence"] == 1
        assert recent_snapshot["last_compile"]["compiled_at"]
        assert recent_snapshot["last_compile"]["duration_ms"] is not None
        assert isinstance(recent_snapshot["last_compile"]["duration_ms"], int)
        assert recent_snapshot["last_compile"]["duration_ms"] >= 0
        assert recent_snapshot["last_compile"]["entry_document"] == str(source_file)
        assert len(recent_snapshot["compile_history"]) == 1
        assert recent_snapshot["compile_history"][0] == recent_snapshot["last_compile"]
        assert result["outcome"]["graph_model"]["nodes"][0]["source_anchor_ref"] == "n1"
        emit_entries = [
            entry
            for entry in result["outcome"]["diagnostic_catalog"]["entries"]
            if entry["stage"] == "emit"
        ]
        assert emit_entries[0]["stage_extension"]["graph_model_id"].startswith("graph:")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_project_document_and_can_create_new_project(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            initial_payload = json.loads(response.read().decode("utf-8"))

        assert initial_payload["project"]["project_id"] == "weconduct-workspace"
        assert initial_payload["project"]["project_name"] == "WeConduct Workspace"
        assert initial_payload["project"]["project_schema_version"] == "project-v1"
        assert initial_payload["project"]["source_of_truth"] == "graph_document"
        assert initial_payload["project"]["execution_overview"]["runtime_run_count"] == 0

        seed_graph_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "ports": [],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        seed_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=seed_graph_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(seed_graph_request) as response:
            json.loads(response.read().decode("utf-8"))

        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compile_request) as response:
            json.loads(response.read().decode("utf-8"))

        create_payload = json.dumps({"project_name": "Project From API"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request) as response:
            created_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/graph") as response:
            graph_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert created_payload["status"] == "created"
        assert created_payload["project"]["project_name"] == "Project From API"
        assert created_payload["project"]["project_schema_version"] == "project-v1"
        assert project_payload["project"]["project_name"] == "Project From API"
        assert graph_payload["graph_model"]["nodes"] == []
        assert snapshot_payload["workbench"]["compile_counter"] == 0
        assert snapshot_payload["last_compile"] is None
        assert snapshot_payload["compile_history"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_documents_and_graph_endpoint_support_custom_node_graph_documents(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        seed_graph_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-input",
                        "lowered_kind": "bridge",
                        "source_anchor_ref": "n-input",
                        "expansion_role": "component.input",
                        "display_name": "输入",
                        "node_kind": "component.input",
                        "position": {"x": 40, "y": 40},
                        "ports": [],
                        "node_config": {
                            "name": "username",
                            "value_type": "string",
                            "required": True,
                        },
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        seed_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=seed_graph_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(seed_graph_request):
            pass

        create_resource_payload = json.dumps({"resource_name": "登录流程组件"}).encode("utf-8")
        create_resource_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=create_resource_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_resource_request) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        resource_id = resource_payload["resource"]["resource_id"]
        document_id = f"custom_node_graph:{resource_id}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/documents") as response:
            documents_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/graph?document_id={urllib.parse.quote(document_id, safe='')}"
        ) as response:
            graph_payload = json.loads(response.read().decode("utf-8"))

        custom_document = next(
            item
            for item in documents_payload["documents"]
            if item["document_id"] == document_id
        )
        assert custom_document["document_role"] == "custom_node_graph"
        assert custom_document["resource_id"] == resource_id
        assert graph_payload["graph_model"]["graph_model_id"] == document_id
        assert graph_payload["graph_model"]["nodes"][0]["node_kind"] == "component.input"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_create_empty_custom_node_graph_resource_and_save_its_document(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps({"resource_name": "空白用户组件"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs/create-empty",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request) as response:
            created_payload = json.loads(response.read().decode("utf-8"))

        resource_id = created_payload["resource"]["resource_id"]
        document_id = f"custom_node_graph:{resource_id}"
        updated_document_payload = json.dumps(
            {
                "document_id": document_id,
                "graph_model_id": document_id,
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-output",
                        "lowered_kind": "bridge",
                        "source_anchor_ref": "n-output",
                        "expansion_role": "component.output",
                        "display_name": "输出",
                        "node_kind": "component.output",
                        "position": {"x": 100, "y": 80},
                        "ports": [],
                        "node_config": {
                            "name": "done",
                            "value_type": "boolean",
                            "required": True,
                        },
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=updated_document_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request) as response:
            saved_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        resource = next(
            item for item in registry_payload["resources"] if item["resource_id"] == resource_id
        )
        assert created_payload["status"] == "created"
        assert saved_payload["graph_model"]["graph_model_id"] == document_id
        assert resource["output_schema"]["done"]["type"] == "boolean"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_snapshot_exposes_preferences_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {
                    "language": "en-US",
                    "theme": "dark",
                    "startup_action": "restore_last_workspace",
                    "default_project_directory": str((tmp_path / "default-project-home").resolve()),
                    "recent_project_limit": 7,
                },
                "compile_settings": {
                    "default_source_kind": "graph_workspace",
                    "diagnostic_level": "error",
                    "block_on_disabled_components": True,
                    "allow_degraded_compile": True,
                },
                "security_settings": {
                    "confirm_high_risk_actions": True,
                    "allow_external_programs": False,
                    "allow_file_access": True,
                },
                "python_runtime_settings": {
                    "python_executable_path": None,
                    "timeout_seconds": 60,
                    "sandbox_mode": "restricted",
                },
                "graph_settings": {
                    "auto_sync_mode": "responsive",
                    "show_node_id_on_node": True,
                    "show_disabled_resource_badge": True,
                    "snap_to_grid": True,
                    "grid_enabled": True,
                },
                "other_settings": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["preferences"]["program_settings"]["language"] == "en-US"
        assert payload["preferences"]["program_settings"]["default_project_directory"] == str((tmp_path / "default-project-home").resolve())
        assert payload["preferences"]["graph_settings"]["show_node_id_on_node"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_and_updates_project_settings_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_payload = json.dumps({"project_name": "HTTP Settings Project"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            initial_payload = json.loads(response.read().decode("utf-8"))

        assert initial_payload["project_settings"]["project_identity"]["name"] == "HTTP Settings Project"
        assert initial_payload["project_settings"]["packaging"]["default_output_name"] == "http-settings-project.wcrun"

        update_payload = json.dumps(
            {
                "project_settings": {
                    **initial_payload["project_settings"],
                    "project_identity": {
                        **initial_payload["project_settings"]["project_identity"],
                        "name": "HTTP Settings Project Renamed",
                    },
                    "runtime_defaults": {
                        "initial_variables": {"base_url": "http://api.test"},
                        "browser_config": {"headless": False, "slow_mo_ms": 200},
                        "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                    },
                }
            }
        ).encode("utf-8")
        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request) as response:
            updated_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            persisted_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert updated_payload["project_settings"]["runtime_defaults"]["initial_variables"]["base_url"] == "http://api.test"
        assert updated_payload["project_settings"]["project_identity"]["name"] == "HTTP Settings Project Renamed"
        assert persisted_payload["project_settings"]["runtime_defaults"]["browser_config"]["slow_mo_ms"] == 200
        assert project_payload["project"]["project_name"] == "HTTP Settings Project Renamed"
        assert snapshot_payload["project_settings"]["loaded"] is True
        assert snapshot_payload["project_settings"]["state_source"] == "workspace_state"
        assert snapshot_payload["project_settings"]["project_file_path"] is None
        assert snapshot_payload["project_settings"]["project_settings_path"] is None
        assert snapshot_payload["project_settings"]["session_dir"] is None
        assert snapshot_payload["project_settings"]["is_dirty"] is True
        assert snapshot_payload["project_settings"]["package_default_output_name"] == "http-settings-project.wcrun"
        assert snapshot_payload["project"]["project_name"] == "HTTP Settings Project Renamed"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_settings_exposes_python_runtime_summary(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps({"project_name": "HTTP Python Runtime Summary"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert "python_runtime_profile" in payload["project_settings"]
        assert "python_runtime_summary" in payload
        assert payload["python_runtime_summary"]["enabled"] is False
        assert payload["python_runtime_summary"]["health_status"] == "disabled"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_prepare_health_check_and_clear_project_python_runtime(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps(
            {
                "project_name": "HTTP Python Runtime Actions",
                "project_directory": str(tmp_path),
            }
        ).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        **settings_payload["project_settings"],
                        "python_runtime_profile": {
                            **settings_payload["project_settings"]["python_runtime_profile"],
                            "runtime_enabled": True,
                            "cache_location_mode": "project_cache",
                            "project_cache_mode": "wheelhouse_rebuild",
                            "requirements_inline": [],
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request):
            pass

        def _post_runtime_action(path: str) -> dict:
            request = urllib.request.Request(
                f"{base_url}{path}",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))

        prepare_payload = _post_runtime_action("/api/workbench/project/python-runtime/prepare")
        health_payload = _post_runtime_action("/api/workbench/project/python-runtime/health-check")
        clear_payload = _post_runtime_action("/api/workbench/project/python-runtime/clear")

        assert prepare_payload["python_runtime_profile"]["runtime_enabled"] is True
        assert prepare_payload["runtime_status"]["health_status"] == "ready"
        assert prepare_payload["runtime_status"]["runtime_root"]
        assert health_payload["runtime_status"]["health_status"] == "ready"
        assert clear_payload["runtime_status"]["health_status"] == "missing"
        assert clear_payload["diagnostics"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_get_and_rebuild_project_python_runtime(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps(
            {
                "project_name": "HTTP Python Runtime Rebuild",
                "project_directory": str(tmp_path),
            }
        ).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        **settings_payload["project_settings"],
                        "python_runtime_profile": {
                            **settings_payload["project_settings"]["python_runtime_profile"],
                            "runtime_enabled": True,
                            "cache_location_mode": "project_cache",
                            "project_cache_mode": "wheelhouse_rebuild",
                            "requirements_inline": [],
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/python-runtime") as response:
            initial_payload = json.loads(response.read().decode("utf-8"))

        prepare_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/python-runtime/prepare",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(prepare_request) as response:
            prepare_payload = json.loads(response.read().decode("utf-8"))

        rebuild_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/python-runtime/rebuild",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(rebuild_request) as response:
            rebuild_payload = json.loads(response.read().decode("utf-8"))

        assert initial_payload["python_runtime_profile"]["runtime_enabled"] is True
        assert initial_payload["runtime_status"]["health_status"] in {"missing", "broken", "stale", "ready"}
        assert prepare_payload["runtime_status"]["health_status"] == "ready"
        assert rebuild_payload["runtime_status"]["health_status"] == "ready"
        assert rebuild_payload["runtime_status"]["runtime_root"] == prepare_payload["runtime_status"]["runtime_root"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_export_project_python_runtime_bundle(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        output_path = tmp_path / "exports" / "python-runtime-export.zip"
        create_payload = json.dumps(
            {
                "project_name": "HTTP Python Runtime Export",
                "project_directory": str(tmp_path),
            }
        ).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        **settings_payload["project_settings"],
                        "python_runtime_profile": {
                            **settings_payload["project_settings"]["python_runtime_profile"],
                            "runtime_enabled": True,
                            "cache_location_mode": "project_cache",
                            "project_cache_mode": "wheelhouse_rebuild",
                            "requirements_source_mode": "inline",
                            "requirements_inline": ["samplepkg==0.1.0"],
                            "package_embed_mode": "wheelhouse_rebuild",
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request):
            pass

        export_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/python-runtime/export-bundle",
            data=json.dumps({"output_path": str(output_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(export_request) as response:
            export_payload = json.loads(response.read().decode("utf-8"))

        assert export_payload["status"] == "exported"
        assert export_payload["export_bundle"]["bundle_mode"] == "wheelhouse_rebuild"
        assert export_payload["export_bundle"]["bundle_root"] == "wheelhouse"
        assert export_payload["export_bundle"]["output_path"] == str(output_path.resolve())
        assert export_payload["export_bundle"]["entry_count"] >= 2
        assert output_path.exists() is True
        with zipfile.ZipFile(output_path, mode="r") as archive:
            archive_names = set(archive.namelist())
            assert "wheelhouse/requirements.txt" in archive_names
            assert "wheelhouse/runtime-manifest.json" in archive_names
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_export_project_python_runtime_bundle_rejects_none_mode(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        output_path = tmp_path / "exports" / "python-runtime-export-none.zip"
        create_payload = json.dumps(
            {
                "project_name": "HTTP Python Runtime Export None",
                "project_directory": str(tmp_path),
            }
        ).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        **settings_payload["project_settings"],
                        "python_runtime_profile": {
                            **settings_payload["project_settings"]["python_runtime_profile"],
                            "runtime_enabled": True,
                            "cache_location_mode": "project_cache",
                            "package_embed_mode": "none",
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request):
            pass

        export_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/python-runtime/export-bundle",
            data=json.dumps({"output_path": str(output_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(export_request)

        assert exc_info.value.code == 400
        error_payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert error_payload["error"] == "invalid_request"
        assert (
            error_payload["message"]
            == "python runtime bundle export requires package_embed_mode other than none"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_create_project_uses_default_preferences_directory_when_missing(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    default_project_directory = tmp_path / "preferred-project-home"
    expected_project_path = default_project_directory / "Project From Preferences.weconduct.json"
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {
                    "language": "zh-CN",
                    "theme": "light",
                    "startup_action": "restore_last_workspace",
                    "default_project_directory": str(default_project_directory.resolve()),
                    "recent_project_limit": 10,
                },
                "compile_settings": {
                    "default_source_kind": "graph_workspace",
                    "diagnostic_level": "error",
                    "block_on_disabled_components": True,
                    "allow_degraded_compile": True,
                },
                "security_settings": {
                    "confirm_high_risk_actions": True,
                    "allow_external_programs": False,
                    "allow_file_access": True,
                },
                "python_runtime_settings": {
                    "python_executable_path": None,
                    "timeout_seconds": 60,
                    "sandbox_mode": "restricted",
                },
                "graph_settings": {
                    "auto_sync_mode": "responsive",
                    "show_node_id_on_node": True,
                    "show_disabled_resource_badge": True,
                    "snap_to_grid": True,
                    "grid_enabled": True,
                },
                "other_settings": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps({"project_name": "Project From Preferences"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request) as response:
            created_payload = json.loads(response.read().decode("utf-8"))

        assert created_payload["project"]["project_file_path"] == str(expected_project_path.resolve())
        assert created_payload["project"]["workspace_root"] == str(default_project_directory.resolve())
        assert expected_project_path.exists() is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_create_project_into_selected_directory(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_directory = tmp_path / "custom-project-home" / "demo-project"
    expected_project_path = project_directory / "Project From API.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        create_payload = json.dumps(
            {
                "project_name": "Project From API",
                "project_directory": str(project_directory),
            }
        ).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request) as response:
            created_payload = json.loads(response.read().decode("utf-8"))

        assert created_payload["status"] == "created"
        assert created_payload["project"]["project_name"] == "Project From API"
        assert created_payload["project"]["project_file_path"] == str(expected_project_path.resolve())
        assert created_payload["project"]["workspace_root"] == str(project_directory.resolve())
        assert expected_project_path.exists() is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_save_open_and_list_recent_projects(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    first_project_path = tmp_path / "first-project.weconduct.json"
    second_project_path = tmp_path / "second-project.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_first_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "First Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_first_request):
            pass

        save_as_first_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(first_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_first_request) as response:
            first_save_payload = json.loads(response.read().decode("utf-8"))

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request) as response:
            save_payload = json.loads(response.read().decode("utf-8"))
        first_storage_root = first_project_path.parent / f"{first_project_path.stem}.data"
        first_graph_payload = json.loads(
            (first_storage_root / "graphs" / "workspace.graph.json").read_text(
                encoding="utf-8"
            )
        )

        create_second_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Second Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_second_request):
            pass

        save_as_second_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(second_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_second_request) as response:
            second_save_payload = json.loads(response.read().decode("utf-8"))

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(first_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/recent-projects") as response:
            recent_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert first_save_payload["status"] == "saved"
        assert first_save_payload["project"]["project_file_path"] == str(first_project_path.resolve())
        assert save_payload["status"] == "saved"
        assert save_payload["project"]["is_dirty"] is False
        assert first_graph_payload["nodes"][0]["node_id"] == "node-1"
        assert second_save_payload["project"]["project_file_path"] == str(second_project_path.resolve())
        assert open_payload["status"] == "opened"
        assert open_payload["project"]["project_name"] == "First Project"
        assert open_payload["project"]["project_file_path"] == str(first_project_path.resolve())
        assert open_payload["graph_document"]["nodes"][0]["node_id"] == "node-1"
        assert project_payload["project"]["project_name"] == "First Project"
        assert project_payload["project"]["is_dirty"] is False
        assert recent_payload["recent_projects"][0]["project_path"] == str(first_project_path.resolve())
        assert recent_payload["recent_projects"][1]["project_path"] == str(second_project_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_save_and_open_project_supports_split_storage_layout(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "demo" / "demo.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request) as response:
            save_payload = json.loads(response.read().decode("utf-8"))

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        storage_root = project_path.parent / f"{project_path.stem}.data"
        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_payload = json.loads(
            (storage_root / "graphs" / "workspace.graph.json").read_text(
                encoding="utf-8"
            )
        )

        assert save_payload["status"] == "saved"
        assert open_payload["status"] == "opened"
        assert open_payload["project"]["project_file_path"] == str(project_path.resolve())
        assert project_manifest["project_file_schema_version"] == 2
        assert (
            project_manifest["project"]["main_graph_path"]
            == f"{project_path.stem}.data/graphs/workspace.graph.json"
        )
        assert graph_payload["graph_model_id"] == "graph:workspace"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_open_project_exposes_pending_graph_upgrade(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-upgrade" / "legacy-upgrade.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        assert open_payload["status"] == "opened"
        assert open_payload["project"]["pending_graph_upgrade"] is not None
        assert open_payload["project"]["pending_graph_upgrade"]["status"] == "upgrade_available"
        assert (
            open_payload["project"]["pending_graph_upgrade"]["compatibility"]["graph_data_version"]
            == "0.5.2"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_apply_pending_graph_upgrade(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-apply" / "legacy-apply.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        apply_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "upgrade_and_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(apply_request) as response:
            apply_payload = json.loads(response.read().decode("utf-8"))

        snapshot_request = urllib.request.urlopen(f"{base_url}/api/workbench/snapshot")
        with snapshot_request as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert apply_payload["status"] == "upgraded"
        assert apply_payload["project"]["pending_graph_upgrade"] is None
        assert snapshot_payload["project"]["pending_graph_upgrade"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_apply_pending_graph_upgrade_for_legacy_main_graph_document_id(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-main-graph-id" / "legacy-main-graph-id.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["graph_model_id"] = "graph:legacy-main-api"
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        assert open_payload["project"]["pending_graph_upgrade"] is not None
        assert open_payload["project"]["pending_graph_upgrade"]["document_id"] == "graph:legacy-main-api"

        apply_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "upgrade_and_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(apply_request) as response:
            apply_payload = json.loads(response.read().decode("utf-8"))

        assert apply_payload["status"] == "upgraded"
        assert apply_payload["project"]["pending_graph_upgrade"] is None
        assert apply_payload["graph_document"]["graph_model_id"] == "graph:legacy-main-api"
        assert (
            apply_payload["graph_document"]["root_metadata"]["graph_compatibility"]["graph_data_version"]
            == "0.6.2"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_apply_pending_graph_upgrade_when_workspace_draft_is_empty_but_pending_recovery_keeps_main_graph(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-pending-recovery" / "legacy-pending-recovery.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["graph_model_id"] = "graph:legacy-pending-recovery-api"
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        assert open_payload["project"]["pending_graph_upgrade"] is not None
        assert (
            open_payload["project"]["pending_graph_upgrade"]["document_id"]
            == "graph:legacy-pending-recovery-api"
        )

        state_payload = json.loads(workspace_state_path.read_text(encoding="utf-8"))
        pending_recovery_workspace_state = deepcopy(state_payload)
        pending_recovery_workspace_state["pending_recovery"] = None
        pending_recovery_workspace_state["pending_graph_upgrade"] = None
        pending_recovery_workspace_state["project_runtime"]["is_dirty"] = False

        state_payload["project_runtime"]["is_dirty"] = True
        state_payload["graph_document"] = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [],
            "edges": [],
            "viewport": None,
            "root_metadata": {
                "graph_compatibility": {
                    "graph_data_version": "0.6.2",
                    "built_with_app_version": "0.7.0",
                    "minimum_loader_app_version": "0.5.2",
                    "last_upgraded_by_app_version": "0.7.0",
                    "upgrade_history": [],
                }
            },
            "graph_effective_diagnostic_anchor_refs": [],
        }
        state_payload["graph_document_meta"] = {
            "save_revision": 4,
            "saved_at": "2026-06-24T12:19:45.224045+08:00",
        }
        state_payload["pending_recovery"] = {
            "status": "pending",
            "project_id": state_payload["project"]["project_id"],
            "project_name": state_payload["project"]["project_name"],
            "project_file_path": str(project_path.resolve()),
            "workspace_state": pending_recovery_workspace_state,
        }
        workspace_state_path.write_text(
            json.dumps(state_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        restarted_server, restarted_thread = _start_test_server(workspace_state_path=workspace_state_path)
        restarted_base_url = f"http://127.0.0.1:{restarted_server.server_address[1]}"
        try:
            apply_request = urllib.request.Request(
                f"{restarted_base_url}/api/workbench/project/graph-upgrade/apply",
                data=json.dumps({"decision": "upgrade_and_load"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(apply_request) as response:
                apply_payload = json.loads(response.read().decode("utf-8"))

            assert apply_payload["status"] == "upgraded"
            assert apply_payload["project"]["pending_graph_upgrade"] is None
            assert apply_payload["graph_document"]["graph_model_id"] == "graph:legacy-pending-recovery-api"
            assert (
                apply_payload["graph_document"]["root_metadata"]["graph_compatibility"][
                    "graph_data_version"
                ]
                == "0.6.2"
            )
        finally:
            restarted_server.shutdown()
            restarted_server.server_close()
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_force_loaded_legacy_graph_is_detected_again_after_server_restart(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-force-restart" / "legacy-force-restart.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        force_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "force_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(force_request) as response:
            force_payload = json.loads(response.read().decode("utf-8"))

        assert force_payload["status"] == "force_loaded"
        assert force_payload["project"]["pending_graph_upgrade"] is None
    finally:
        server.shutdown()
        server.server_close()

    restarted_server, restarted_thread = _start_test_server(workspace_state_path=workspace_state_path)
    restarted_base_url = f"http://127.0.0.1:{restarted_server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{restarted_base_url}/api/workbench/snapshot") as response:
            restarted_snapshot = json.loads(response.read().decode("utf-8"))

        assert restarted_snapshot["project"]["pending_graph_upgrade"] is not None
        assert restarted_snapshot["project"]["pending_graph_upgrade"]["status"] == "upgrade_available"
    finally:
        restarted_server.shutdown()
        restarted_server.server_close()


def test_http_api_force_loaded_legacy_graph_can_be_rechecked_without_server_restart(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-force-recheck" / "legacy-force-recheck.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        assert open_payload["project"]["pending_graph_upgrade"] is not None

        force_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "force_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(force_request) as response:
            force_payload = json.loads(response.read().decode("utf-8"))

        assert force_payload["status"] == "force_loaded"
        assert force_payload["project"]["pending_graph_upgrade"] is None

        recheck_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/recheck",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(recheck_request) as response:
            recheck_payload = json.loads(response.read().decode("utf-8"))

        assert recheck_payload["status"] == "rechecked"
        assert recheck_payload["project"]["pending_graph_upgrade"] is not None
        assert recheck_payload["project"]["pending_graph_upgrade"]["status"] == "upgrade_available"
        assert recheck_payload["pending_graph_upgrade"]["document_id"] == "graph:workspace"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_upgraded_graph_persists_after_save_and_reopen(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-persist" / "legacy-persist.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        apply_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "upgrade_and_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(apply_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request) as response:
            save_payload = json.loads(response.read().decode("utf-8"))

        reopen_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(reopen_request) as response:
            reopen_payload = json.loads(response.read().decode("utf-8"))

        saved_graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))

        assert save_payload["status"] == "saved"
        assert (
            saved_graph_payload["root_metadata"]["graph_compatibility"]["graph_data_version"]
            == "0.6.2"
        )
        assert reopen_payload["project"]["pending_graph_upgrade"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_apply_graph_upgrade_persists_without_manual_save(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "legacy-upgrade-no-save" / "legacy-upgrade-no-save.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {}
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        apply_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/graph-upgrade/apply",
            data=json.dumps({"decision": "upgrade_and_load"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(apply_request) as response:
            apply_payload = json.loads(response.read().decode("utf-8"))

        reopen_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(reopen_request) as response:
            reopen_payload = json.loads(response.read().decode("utf-8"))

        saved_graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))

        assert open_payload["project"]["pending_graph_upgrade"] is not None
        assert apply_payload["status"] == "upgraded"
        assert (
            saved_graph_payload["root_metadata"]["graph_compatibility"]["graph_data_version"]
            == "0.6.2"
        )
        assert reopen_payload["project"]["pending_graph_upgrade"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_restart_clears_stale_pending_graph_upgrade_when_project_and_recovery_graph_are_already_upgraded(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "stale-pending-http" / "stale-pending-http.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        create_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs/create-empty",
            data=json.dumps({"resource_name": "HTTP 已升级子图"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_component_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        resource_index_path = (
            project_path.parent
            / project_manifest["project"]["project_resources_index_path"]
        )
        resource_index = json.loads(resource_index_path.read_text(encoding="utf-8"))
        custom_source_ref = resource_index["resources"][0]["source_ref"]
        custom_graph_path = project_path.parent / custom_source_ref / "graph.json"
        custom_graph_payload = json.loads(custom_graph_path.read_text(encoding="utf-8"))
        custom_graph_payload["graph_model_id"] = "custom_node_graph:custom_node_graph:984cc1b4429c"
        custom_graph_path.write_text(
            json.dumps(custom_graph_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            resources_payload = json.loads(response.read().decode("utf-8"))
        custom_resource = next(
            item
            for item in resources_payload["resources"]
            if item["resource_type"] == "custom_node_graph"
        )
        assert open_payload["project"]["pending_graph_upgrade"] is None

        state_payload = json.loads(workspace_state_path.read_text(encoding="utf-8"))
        pending_recovery_workspace_state = deepcopy(state_payload)
        pending_recovery_workspace_state["pending_recovery"] = None
        pending_recovery_workspace_state["pending_graph_upgrade"] = None
        pending_recovery_workspace_state["project_runtime"]["is_dirty"] = True

        state_payload["project_runtime"]["is_dirty"] = True
        state_payload["pending_recovery"] = {
            "status": "pending",
            "project_id": state_payload["project"]["project_id"],
            "project_name": state_payload["project"]["project_name"],
            "project_file_path": str(project_path.resolve()),
            "workspace_state": pending_recovery_workspace_state,
        }
        state_payload["pending_graph_upgrade"] = {
            "status": "upgrade_available",
            "document_id": "graph:workspace",
            "documents": [
                {
                    "document_id": "graph:workspace",
                    "document_role": "main_graph",
                    "display_name": state_payload["project"]["project_name"],
                    "compatibility": {
                        "status": "upgrade_available",
                        "graph_data_version": "0.5.2",
                        "current_app_version": "0.7.0",
                        "minimum_loader_app_version": "0.5.2",
                        "built_with_app_version": "0.5.2",
                        "last_upgraded_by_app_version": "0.5.2",
                        "upgrade_history": [],
                        "is_legacy_unversioned": True,
                        "available_upgrade_path": [
                            {
                                "from_version": "0.5.2",
                                "to_version": "0.6.2",
                                "upgrader_id": "p18d-baseline-052-to-061",
                            }
                        ],
                    },
                },
                {
                    "document_id": "custom_node_graph:custom_node_graph:984cc1b4429c",
                    "document_role": "custom_node_graph",
                    "display_name": custom_resource["display_name"],
                    "compatibility": {
                        "status": "upgrade_available",
                        "graph_data_version": "0.5.2",
                        "current_app_version": "0.7.0",
                        "minimum_loader_app_version": "0.5.2",
                        "built_with_app_version": "0.5.2",
                        "last_upgraded_by_app_version": "0.5.2",
                        "upgrade_history": [],
                        "is_legacy_unversioned": True,
                        "available_upgrade_path": [
                            {
                                "from_version": "0.5.2",
                                "to_version": "0.6.2",
                                "upgrader_id": "p18d-baseline-052-to-061",
                            }
                        ],
                    },
                },
            ],
        }
        workspace_state_path.write_text(
            json.dumps(state_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        server.shutdown()
        server.server_close()

    restarted_server, restarted_thread = _start_test_server(workspace_state_path=workspace_state_path)
    restarted_base_url = f"http://127.0.0.1:{restarted_server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{restarted_base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert project_payload["project"]["pending_recovery"] is not None
        assert project_payload["project"]["pending_graph_upgrade"] is None
    finally:
        restarted_server.shutdown()
        restarted_server.server_close()


def test_http_api_open_project_exposes_loader_older_than_graph_status(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "future-open" / "future-open.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {
            "graph_compatibility": {
                "graph_data_version": "0.7.0",
                "built_with_app_version": "0.7.0",
                "minimum_loader_app_version": "0.7.0",
                "last_upgraded_by_app_version": "0.7.0",
                "upgrade_history": [],
            }
        }
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        assert open_payload["project"]["pending_graph_upgrade"] is not None
        assert open_payload["project"]["pending_graph_upgrade"]["status"] == "loader_older_than_graph"
        assert (
            open_payload["project"]["pending_graph_upgrade"]["compatibility"]["minimum_loader_app_version"]
            == "0.7.0"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_settings_expose_main_graph_compatibility_summary(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "settings-compat" / "settings-compat.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        project_manifest = json.loads(project_path.read_text(encoding="utf-8"))
        graph_path = project_path.parent / project_manifest["project"]["main_graph_path"]
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_payload["root_metadata"] = {
            "graph_compatibility": {
                "graph_data_version": "0.7.0",
                "built_with_app_version": "0.7.0",
                "minimum_loader_app_version": "0.7.0",
                "last_upgraded_by_app_version": "0.7.0",
                "upgrade_history": [],
            }
        }
        graph_path.write_text(json.dumps(graph_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        assert settings_payload["state"]["main_graph_compatibility"]["graph_data_version"] == "0.7.0"
        assert settings_payload["state"]["main_graph_compatibility"]["built_with_app_version"] == "0.7.0"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_convert_webcontrol_project_and_auto_open_result(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    source_path = tmp_path / "legacy-main.json"
    blueprint_dir = tmp_path / "blueprints"
    blueprint_dir.mkdir(parents=True, exist_ok=True)
    (blueprint_dir / "bp-login.yaml").write_text(
        """
blueprint_info:
  id: bp-login
  name: 登录蓝图
input_schema:
  username:
    type: string
output_schema:
  logged_in:
    type: boolean
automation_steps:
  - step: 1
    action: open_url
    url: "https://example.com/form"
""".strip(),
        encoding="utf-8",
    )
    source_path.write_text(
        json.dumps(
            {
                "project_info": {"name": "HTTP 转换项目"},
                "automation_steps": [
                    {
                        "step": 1,
                        "action": "open_url",
                        "url": "https://example.com/login",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_project_path = tmp_path / "converted" / "http-converted.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        convert_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/convert-webcontrol",
            data=json.dumps(
                {
                    "source_path": str(source_path),
                    "blueprint_directory": str(blueprint_dir),
                    "output_project_path": str(output_project_path),
                    "auto_open_project": True,
                    "write_conversion_report": True,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(convert_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "converted"
        assert payload["output_project_path"] == str(output_project_path.resolve())
        assert payload["report"]["imported_blueprint_count"] == 1
        assert payload["report"]["generated_resource_count"] == 1
        assert payload["project"]["project_file_path"] == str(output_project_path.resolve())
        assert payload["graph_document"]["graph_model_id"] == "graph:workspace"
        assert project_payload["project"]["project_name"] == "HTTP 转换项目"
        assert project_payload["project"]["project_file_path"] == str(output_project_path.resolve())
        assert (
            snapshot_payload["entrypoints"]["project_convert_webcontrol_action"]
            == "/api/workbench/project/convert-webcontrol"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_save_persists_provided_graph_document_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "payload-save.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Payload Save"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=json.dumps(
                {
                    "graph_document": {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-http-save",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n-http-save",
                                "expansion_role": "action:set_variable",
                                "node_kind": "data.set_variable",
                                "node_config": {"name": "username", "value": "http-user"},
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        storage_root = project_path.parent / f"{project_path.stem}.data"
        project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        graph_payload = json.loads(
            (storage_root / "graphs" / "workspace.graph.json").read_text(
                encoding="utf-8"
            )
        )

        assert payload["status"] == "saved"
        assert payload["graph_document"]["nodes"][0]["node_id"] == "node-http-save"
        assert project_payload["project_file_schema_version"] == 2
        assert graph_payload["nodes"][0]["node_id"] == "node-http-save"
        assert graph_payload["nodes"][0]["node_config"]["value"] == "http-user"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_save_as_persists_provided_graph_document_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "payload-save-as.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Payload Save As"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps(
                {
                    "project_path": str(project_path),
                    "graph_document": {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-http-save-as",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n-http-save-as",
                                "expansion_role": "action:set_variable",
                                "node_kind": "data.set_variable",
                                "node_config": {"name": "password", "value": "http-secret"},
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        storage_root = project_path.parent / f"{project_path.stem}.data"
        project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        graph_payload = json.loads(
            (storage_root / "graphs" / "workspace.graph.json").read_text(
                encoding="utf-8"
            )
        )

        assert payload["status"] == "saved"
        assert payload["graph_document"]["nodes"][0]["node_id"] == "node-http-save-as"
        assert project_payload["project_file_schema_version"] == 2
        assert graph_payload["nodes"][0]["node_id"] == "node-http-save-as"
        assert graph_payload["nodes"][0]["node_config"]["value"] == "http-secret"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_rejects_project_save_without_existing_project_path(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(save_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload == {
                "error": "project.needs_save_as",
                "message": "project_file_path is not set; use save_project_as first",
                "recovery_action": "save_as",
            }
        else:
            raise AssertionError("expected HTTPError for save without project path")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_resource_registry_and_supports_user_component_save_and_toggle(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            initial_registry = json.loads(response.read().decode("utf-8"))

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-1",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n1",
                                "expansion_role": "action:set_variable",
                                "node_kind": "data.set_variable",
                                "node_config": {"name": "message", "value": "hello"},
                                "ports": [],
                            }
                        ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_user_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/user-components",
            data=json.dumps({"resource_name": "Saved From API"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_user_component_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        builtin_resource_id = initial_registry["resources"][0]["resource_id"]
        toggle_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/{builtin_resource_id}/enabled",
            data=json.dumps({"enabled": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(toggle_request) as response:
            toggled_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert initial_registry["registry_revision"] == 0
        initial_registry_by_key = {
            item["resource_key"]: item for item in initial_registry["resources"]
        }
        navigate_resource = initial_registry_by_key["browser.navigate"]
        assert initial_registry_by_key["browser.navigate"]["node_taxonomy"] == "builtin_component"
        assert initial_registry_by_key["browser.navigate"]["resource_manager_visible"] is True
        assert navigate_resource["display_name_i18n"]["zh-CN"] == "导航"
        assert navigate_resource["display_name_i18n"]["en-US"] == "Navigate"
        assert navigate_resource["description_i18n"]["zh-CN"] == "导航浏览器到目标 URL。"
        assert navigate_resource["description_i18n"]["en-US"] == "Navigate browser to target URL."
        assert "control.foreach" not in initial_registry_by_key
        assert "control.jump_to_step" not in initial_registry_by_key
        assert saved_resource_payload["status"] == "saved"
        assert saved_resource_payload["resource"]["resource_type"] == "user_component"
        assert saved_resource_payload["resource"]["node_taxonomy"] == "user_component"
        assert saved_resource_payload["resource"]["resource_manager_visible"] is True
        assert saved_resource_payload["resource"]["component_library_visible"] is True
        assert saved_resource_payload["resource"]["display_name"] == "Saved From API"
        assert saved_resource_payload["resource"]["display_name_i18n"]["en-US"] == "Saved From API"
        assert saved_resource_payload["resource"]["description_i18n"]["en-US"] == (
            "User component captured from current graph document."
        )
        assert toggled_payload["status"] == "updated"
        assert toggled_payload["resource"]["resource_id"] == builtin_resource_id
        assert toggled_payload["resource"]["enabled"] is False
        assert registry_payload["registry_revision"] == 2
        assert registry_payload["summary"]["user_resource_count"] == 1
        assert project_payload["project"]["resource_registry_revision"] == 2
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_resource_registry_and_supports_custom_node_graph_save(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                    {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "root_metadata": {
                            "input_schema": {
                                "incoming": {"type": "string", "required": True},
                            },
                            "output_schema": {
                                "message": {"type": "string"},
                            },
                        },
                        "nodes": [
                            {
                                "node_id": "node-1",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n1",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "message", "value": "hello"},
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_subgraph_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "Saved From API Graph"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_subgraph_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        assert saved_resource_payload["status"] == "saved"
        assert saved_resource_payload["resource"]["resource_type"] == "custom_node_graph"
        assert saved_resource_payload["resource"]["node_taxonomy"] == "user_component"
        assert saved_resource_payload["resource"]["resource_manager_visible"] is True
        assert saved_resource_payload["resource"]["component_library_visible"] is True
        assert saved_resource_payload["resource"]["display_name"] == "Saved From API Graph"
        assert saved_resource_payload["resource"]["input_schema"] == {
            "incoming": {"type": "string", "required": True},
        }
        assert saved_resource_payload["resource"]["output_schema"] == {
            "message": {"type": "string"},
        }
        assert registry_payload["summary"]["user_resource_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_filters_component_library_and_resources_by_query_and_tags(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/component-library?query=captcha&tags=domain:browser"
        ) as response:
            library_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/resources?query=dialog&tags=origin:builtin&enabled=true"
        ) as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        assert any(
            item["resource_key"] == "browser.recognize_captcha"
            for item in library_payload["items"]
        )
        captcha_item = next(
            item
            for item in library_payload["items"]
            if item["resource_key"] == "browser.recognize_captcha"
        )
        assert captcha_item["display_name_i18n"]["zh-CN"] == "识别验证码"
        assert captcha_item["display_name_i18n"]["en-US"] == "Recognize Captcha"
        assert captcha_item["description_i18n"]["zh-CN"] == "使用 captcha_ocr 识别验证码图片。"
        assert captcha_item["description_i18n"]["en-US"] == "Recognize captcha image with captcha_ocr."
        assert registry_payload["resources"]
        assert all("origin:builtin" in item["tags"] for item in registry_payload["resources"])
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_resource_facets_and_supports_project_resource_tag_updates(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "message", "value": "hello"},
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_user_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/user-components",
            data=json.dumps({"resource_name": "Shared API Component"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_user_component_request) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        update_tags_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/{resource_payload['resource']['resource_id']}/tags",
            data=json.dumps({"tags": ["team:api", "folder:shared"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_tags_request) as response:
            updated_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources?query=shared") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/component-library") as response:
            library_payload = json.loads(response.read().decode("utf-8"))

        updated_resource = next(
            item
            for item in registry_payload["resources"]
            if item["resource_id"] == resource_payload["resource"]["resource_id"]
        )

        assert updated_payload["resource"]["category_path"] == ["project", "user_component", "shared"]
        assert "team:api" in updated_payload["resource"]["tags"]
        assert "folder:shared" in updated_payload["resource"]["tags"]
        assert updated_resource["search_tokens"]
        assert any(
            item["path"] == ["project", "user_component", "shared"]
            for item in registry_payload["facets"]["category_paths"]
        )
        assert "team:api" in registry_payload["facets"]["user_tags"]
        assert any(
            item["path"] == ["builtin", "control_structure", "if"]
            for item in library_payload["facets"]["category_paths"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_rejects_resource_toggle_for_unknown_resource(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        toggle_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/missing-resource/enabled",
            data=json.dumps({"enabled": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(toggle_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload == {
                "error": "invalid_request",
                "message": "resource not found: missing-resource",
            }
        else:
            raise AssertionError("expected HTTPError for missing resource")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_supports_remaining_p5b_project_and_resource_endpoints(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    first_project_path = tmp_path / "first.weconduct.json"
    export_path = tmp_path / "resource-export.wecresource.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "P5B Complete"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(first_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_user_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/user-components",
            data=json.dumps({"resource_name": "HTTP Block"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_user_component_request) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        export_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/export",
            data=json.dumps(
                {
                    "resource_id": resource_payload["resource"]["resource_id"],
                    "export_path": str(export_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(export_request) as response:
            exported_payload = json.loads(response.read().decode("utf-8"))

        remove_recent_request = urllib.request.Request(
            f"{base_url}/api/workbench/recent-projects/remove",
            data=json.dumps({"project_path": str(first_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(remove_recent_request) as response:
            removed_recent_payload = json.loads(response.read().decode("utf-8"))

        editor_history_request = urllib.request.Request(
            f"{base_url}/api/workbench/editor/history/record",
            data=json.dumps(
                {
                    "operation_kind": "graph.node.added",
                    "label": "Add HTTP Node",
                    "payload": {"node_id": "node-1"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(editor_history_request) as response:
            editor_history_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/editor/history") as response:
            editor_history_document = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project/documents") as response:
            documents_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/component-library") as response:
            component_library_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/graph/source-projection") as response:
            source_projection_payload = json.loads(response.read().decode("utf-8"))
        import_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/import",
            data=json.dumps({"import_path": str(export_path), "replace_existing": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(import_request) as response:
            imported_payload = json.loads(response.read().decode("utf-8"))

        assert exported_payload["status"] == "exported"
        assert export_path.exists() is True
        assert removed_recent_payload["status"] == "removed"
        assert removed_recent_payload["recent_projects"] == []
        assert editor_history_payload["status"] == "recorded"
        assert editor_history_document["undo_depth"] == 1
        assert documents_payload["documents"][0]["document_role"] == "main_graph"
        assert any(item["display_name"] == "HTTP Block" for item in component_library_payload["items"])
        component_library_by_key = {
            item["resource_key"]: item for item in component_library_payload["items"]
        }
        assert component_library_by_key["control.foreach"]["node_taxonomy"] == "control_structure"
        assert component_library_by_key["control.foreach"]["resource_manager_visible"] is False
        assert component_library_by_key["data.create_list"]["node_taxonomy"] == "logic_expression"
        assert "control.jump_to_step" not in component_library_by_key
        assert "control.foreach_break" not in component_library_by_key
        assert source_projection_payload["status"] == "ready"
        assert source_projection_payload["source_kind"] == "native_flow"
        assert source_projection_payload["graph_document_save_revision"] == 1
        assert source_projection_payload["source_text"] == (
            '{"nodes":[{"id":"n1","role":"action","capability_domain":"http",'
            '"action_kind":"request"}],"edges":[]}'
        )
        assert imported_payload["status"] == "imported"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_persisted_execution_history_and_user_component_runtime_bridge(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "runtime-history.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        initial_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "message", "value": "hello"},
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(initial_graph_request):
            pass

        save_user_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/user-components",
            data=json.dumps({"resource_name": "Reusable HTTP Block"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_user_component_request) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        graph_using_component_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-user-1",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "user1",
                                "expansion_role": "module:user-component",
                                "node_kind": resource_payload["resource"]["resource_id"],
                                "node_config": {
                                    "outputs": {"message": "greeting"},
                                },
                                "ports": [],
                            }
                        ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_using_component_request):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_start_request) as response:
            runtime_started_payload = json.loads(response.read().decode("utf-8"))

        runtime_session_id = runtime_started_payload["runtime_session"]["session_id"]
        runtime_run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{runtime_session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_run_request) as response:
            runtime_completed_payload = json.loads(response.read().decode("utf-8"))

        debug_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(debug_start_request) as response:
            debug_started_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/execution-history") as response:
            history_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/execution-history") as response:
            reopened_history_payload = json.loads(response.read().decode("utf-8"))

        assert runtime_started_payload["runtime_plan"]["executable_nodes"][0]["resolved_resource_id"] == (
            resource_payload["resource"]["resource_id"]
        )
        assert runtime_started_payload["runtime_plan"]["executable_nodes"][0]["resource_type"] == (
            "user_component"
        )
        assert runtime_started_payload["runtime_plan"]["executable_nodes"][0]["component_source_graph_document"]["nodes"][0]["node_id"] == (
            "node-1"
        )
        assert runtime_completed_payload["status"] == "completed"
        assert runtime_completed_payload["result"]["variables"]["greeting"] == "hello"
        assert debug_started_payload["status"] == "started"
        assert history_payload["summary"]["runtime_run_count"] == 1
        assert history_payload["summary"]["debug_session_count"] == 1
        assert history_payload["summary"]["runtime_status_counts"]["completed"] == 1
        assert history_payload["summary"]["debug_status_counts"]["prepared"] == 1
        assert history_payload["runtime_runs"][0]["session_id"] == runtime_session_id
        user_component_resource = next(
            item
            for item in registry_payload["resources"]
            if item["resource_id"] == resource_payload["resource"]["resource_id"]
        )
        assert user_component_resource["source_graph_document"]["nodes"][0]["node_id"] == "node-1"
        assert reopened_history_payload["summary"]["runtime_run_count"] == 1
        assert reopened_history_payload["summary"]["debug_session_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_execution_history_supports_status_filters(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-start",
                            "expansion_role": "flow:start",
                            "node_kind": "flow.start",
                            "node_config": {},
                            "ports": [
                                {
                                    "port_id": "out-control",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "out.control",
                                }
                            ],
                        },
                        {
                            "node_id": "node-set",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-set",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "api_filter", "value": "ok"},
                            "ports": [],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "control",
                            "from_node_id": "node-start",
                            "to_node_id": "node-set",
                            "from_port_id": "out-control",
                            "to_port_id": None,
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_runtime_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_runtime_request) as response:
            runtime_started = json.loads(response.read().decode("utf-8"))
        run_runtime_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{runtime_started['runtime_session']['session_id']}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_runtime_request):
            pass

        start_debug_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_debug_request):
            pass

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/execution-history?runtime_status=completed"
        ) as response:
            runtime_history_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(
            f"{base_url}/api/workbench/execution-history?debug_status=prepared"
        ) as response:
            debug_history_payload = json.loads(response.read().decode("utf-8"))

        assert runtime_history_payload["summary"]["runtime_run_count"] == 1
        assert runtime_history_payload["runtime_runs"][0]["status"] == "completed"
        assert debug_history_payload["summary"]["debug_session_count"] == 1
        assert debug_history_payload["debug_sessions"][0]["status"] == "prepared"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_start_run_and_query_runtime_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    echo_server, echo_thread = _start_runtime_echo_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "node_config": {
                                "method": "POST",
                                "url": f"http://127.0.0.1:{echo_server.server_address[1]}/echo",
                                "body": {"runtime": True},
                            },
                            "ports": [
                                {
                                    "port_id": "out",
                                    "direction": "output",
                                    "relation_layer": "data",
                                    "semantic_slot": "out.default",
                                }
                            ],
                        },
                        {
                            "node_id": "node-2",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n2",
                            "expansion_role": "transform:map",
                            "node_kind": "data.map",
                            "ports": [
                                {
                                    "port_id": "in",
                                    "direction": "input",
                                    "relation_layer": "data",
                                    "semantic_slot": "in.default",
                                }
                            ],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "data",
                            "from_node_id": "node-1",
                            "to_node_id": "node-2",
                            "from_port_id": "out",
                            "to_port_id": "in",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/sessions") as response:
            sessions_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert started_payload["status"] == "started"
        assert started_payload["runtime_session"]["status"] == "running"
        assert started_payload["runtime_session"]["execution_supported"] is True
        assert run_payload["status"] == "completed"
        assert run_payload["result"]["status"] == "succeeded"
        assert run_payload["result"]["completed_node_ids"] == ["node-1", "node-2"]
        assert run_payload["result"]["outputs"]["node-1"]["status_code"] == 200
        assert run_payload["result"]["outputs"]["node-1"]["body"]["body"]["runtime"] is True
        assert session_payload["runtime_session"]["status"] == "completed"
        assert session_payload["execution_summary"]["status"] == "succeeded"
        assert session_payload["execution_summary"]["event_count"] == len(session_payload["event_log"])
        assert session_payload["execution_summary"]["node_status_counts"]["completed"] == 2
        assert session_payload["event_log"][-1]["event_kind"] == "session.completed"
        assert sessions_payload["sessions"][0]["completed_node_count"] == 2
        assert sessions_payload["sessions"][0]["event_count"] == len(session_payload["event_log"])
        assert sessions_payload["sessions"][0]["session_id"] == session_id
        assert project_payload["project"]["last_runtime_status"] == "completed"
        assert project_payload["project"]["last_runtime_session_id"] == session_id
        assert project_payload["project"]["execution_overview"]["runtime_status_counts"]["completed"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_delete_project_resource(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "Disposable From API"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_graph_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        resource_id = saved_resource_payload["resource"]["resource_id"]
        delete_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/delete",
            data=json.dumps({"resource_id": resource_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(delete_request) as response:
            deleted_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        assert deleted_payload["status"] == "deleted"
        assert all(item["resource_id"] != resource_id for item in registry_payload["resources"])
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_rename_project_resource(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "Old Name"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_graph_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        resource_id = saved_resource_payload["resource"]["resource_id"]
        rename_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/rename",
            data=json.dumps(
                {"resource_id": resource_id, "display_name": "New Name"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(rename_request) as response:
            renamed_payload = json.loads(response.read().decode("utf-8"))

        assert renamed_payload["resource"]["resource_id"] == resource_id
        assert renamed_payload["resource"]["display_name"] == "New Name"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_project_resource_audit_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "audit-api-project.weconduct.json"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps(
                {
                    "project_name": "Audit API Project",
                    "project_directory": str(tmp_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "Audit Resource"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_graph_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        save_project_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_project_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/documents") as response:
            documents_payload = json.loads(response.read().decode("utf-8"))
        resource_ref = next(
            item
            for item in documents_payload["project_owned_resources_index"]["resources"]
            if item["resource_id"] == saved_resource_payload["resource"]["resource_id"]
        )
        manifest_path = project_path.parent / resource_ref["manifest_path"]
        manifest_path.unlink()

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/resource-audit") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "ready"
        assert payload["summary"]["issue_count"] == 1
        assert payload["issues"][0]["category"] == "project.resource.manifest_missing"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_update_custom_node_graph_resource_metadata(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs/create-empty",
            data=json.dumps({"resource_name": "待更新组件"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request) as response:
            created_payload = json.loads(response.read().decode("utf-8"))

        resource_id = created_payload["resource"]["resource_id"]
        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/metadata",
            data=json.dumps(
                {
                    "resource_id": resource_id,
                    "display_name": "登录组件",
                    "description": "用于登录流程的用户组件。",
                    "display_name_i18n": {
                        "zh-CN": "登录组件",
                        "en-US": "Login Component",
                    },
                    "description_i18n": {
                        "zh-CN": "用于登录流程的用户组件。",
                        "en-US": "Reusable component for login flow.",
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request) as response:
            updated_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))

        updated_resource = next(
            item for item in registry_payload["resources"] if item["resource_id"] == resource_id
        )
        assert updated_payload["status"] == "updated"
        assert updated_payload["resource"]["display_name"] == "登录组件"
        assert updated_payload["resource"]["display_name_i18n"]["en-US"] == "Login Component"
        assert updated_payload["resource"]["description_i18n"]["zh-CN"] == "用于登录流程的用户组件。"
        assert updated_resource["description"] == "用于登录流程的用户组件。"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_documents_returns_split_project_layout_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "documents-api-project.weconduct.json"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps(
                {
                    "project_name": "Documents API Project",
                    "project_directory": str(tmp_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/documents") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["project_file"]["project"]["main_graph_path"].endswith(
            "Documents API Project.weconduct.data/graphs/workspace.graph.json"
        )
        assert "project_owned_resources_index" in payload
        assert "resource_overrides" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_open_project_with_missing_resource_manifest_stays_openable(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "api-missing-resource.weconduct.json"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "API Missing Resource"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        graph_update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_update_request):
            pass

        save_graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "Broken API Resource"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_graph_request) as response:
            saved_resource_payload = json.loads(response.read().decode("utf-8"))

        save_project_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_project_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/documents") as response:
            documents_payload = json.loads(response.read().decode("utf-8"))
        resource_ref = next(
            item
            for item in documents_payload["project_owned_resources_index"]["resources"]
            if item["resource_id"] == saved_resource_payload["resource"]["resource_id"]
        )
        manifest_path = project_path.parent / resource_ref["manifest_path"]
        manifest_path.unlink()

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request) as response:
            open_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/resource-audit") as response:
            audit_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            registry_payload = json.loads(response.read().decode("utf-8"))
        reopened_resource = next(
            item
            for item in registry_payload["resources"]
            if item["resource_id"] == saved_resource_payload["resource"]["resource_id"]
        )

        assert open_payload["status"] == "opened"
        assert audit_payload["summary"]["issue_count"] == 1
        assert audit_payload["issues"][0]["category"] == "project.resource.manifest_missing"
        assert reopened_resource["enabled"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_runtime_run_returns_accepted_while_session_continues(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-start",
                            "expansion_role": "flow:start",
                            "node_kind": "flow.start",
                            "node_config": {},
                            "ports": [],
                        },
                        {
                            "node_id": "node-timeout",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-timeout",
                            "expansion_role": "action:wait_for_timeout",
                            "node_kind": "browser.wait_for_timeout",
                            "node_config": {"timeout": 300},
                            "ports": [],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-start-timeout",
                            "relation_layer": "control",
                            "from_node_id": "node-start",
                            "to_node_id": "node-timeout",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started_at = time.monotonic()
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))
        elapsed_ms = (time.monotonic() - started_at) * 1000

        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))

        assert elapsed_ms < 250
        assert run_payload["status"] == "accepted"
        assert run_payload["runtime_session"]["status"] == "running"
        assert session_payload["runtime_session"]["status"] in {"running", "completed"}
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_write_request_requires_token_when_server_token_is_configured(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = workspace_state_path
    server.api_token = "phase17-secret"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(_build_valid_graph_document_payload()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)

        assert exc_info.value.code == 401
        error_payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert error_payload["error"] == "unauthorized"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_write_request_accepts_valid_token_when_server_token_is_configured(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = workspace_state_path
    server.api_token = "phase17-secret"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(_build_valid_graph_document_payload()).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-WeConduct-Token": "phase17-secret",
            },
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "saved"
        assert payload["view"]["graph_document_save_revision"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_health_request_does_not_require_token_when_server_token_is_configured(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = workspace_state_path
    server.api_token = "phase17-secret"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/health") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_runtime_stream_emits_snapshot_summary_and_completed(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-start",
                            "expansion_role": "flow:start",
                            "node_kind": "flow.start",
                            "node_config": {},
                            "ports": [],
                        },
                        {
                            "node_id": "node-timeout",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-timeout",
                            "expansion_role": "action:wait_for_timeout",
                            "node_kind": "browser.wait_for_timeout",
                            "node_config": {"timeout": 50},
                            "ports": [],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-start-timeout",
                            "relation_layer": "control",
                            "from_node_id": "node-start",
                            "to_node_id": "node-timeout",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(run_request).read()

        request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/stream",
            headers={"Accept": "text/event-stream"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            stream_text = response.read(8192).decode("utf-8")

        assert "event: runtime.snapshot" in stream_text
        assert "event: runtime.summary" in stream_text
        assert "event: runtime.completed" in stream_text
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_blocks_runtime_session_start_when_required_resource_is_disabled(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        disable_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/builtin:data.map/enabled",
            data=json.dumps({"enabled": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(disable_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "ports": [
                                {
                                    "port_id": "out",
                                    "direction": "output",
                                    "relation_layer": "data",
                                    "semantic_slot": "out.default",
                                }
                            ],
                        },
                        {
                            "node_id": "node-2",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n2",
                            "expansion_role": "transform:map",
                            "node_kind": "data.map",
                            "ports": [
                                {
                                    "port_id": "in",
                                    "direction": "input",
                                    "relation_layer": "data",
                                    "semantic_slot": "in.default",
                                }
                            ],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "data",
                            "from_node_id": "node-1",
                            "to_node_id": "node-2",
                            "from_port_id": "out",
                            "to_port_id": "in",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["runtime_session"]["session_id"] is None
            assert payload["runtime_session"]["status"] == "diagnostic_blocked"
            assert payload["runtime_plan"] is None
            assert payload["diagnostics"]["entries"][0]["category"] == "graph.node.resource_disabled"
        else:
            raise AssertionError("expected HTTPError for disabled resource diagnostic block")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_exposes_and_persists_graph_workspace_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/graph") as response:
            initial_payload = json.loads(response.read().decode("utf-8"))

        assert initial_payload["graph_model"]["graph_model_id"] == "graph:workspace"
        assert initial_payload["graph_model"]["compilation_id"] is None
        assert initial_payload["graph_model"]["graph_schema_version"] == "graph-v1"
        assert initial_payload["view"]["authority_mode"] == "workspace_graph_draft"
        assert initial_payload["view"]["is_editable"] is True
        assert initial_payload["view"]["graph_document_save_revision"] == 0
        assert initial_payload["view"]["graph_document_saved_at"] is None

        update_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "display_name": "HTTP Request",
                        "node_kind": "http.request",
                        "position": {"x": 120, "y": 80},
                        "ports": [
                            {
                                "port_id": "out-main",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.result",
                            }
                        ],
                        "node_config": {"method": "GET"},
                    }
                ],
                "edges": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1.1},
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(update_request) as response:
            saved_payload = json.loads(response.read().decode("utf-8"))

        assert saved_payload["status"] == "saved"
        assert saved_payload["graph_model"]["nodes"][0]["display_name"] == "HTTP Request"
        assert saved_payload["graph_model"]["nodes"][0]["ports"][0]["port_id"] == "out-main"
        assert saved_payload["view"]["node_count"] == 1
        assert saved_payload["view"]["graph_document_save_revision"] == 1
        assert saved_payload["view"]["graph_document_saved_at"]
    finally:
        server.shutdown()
        server.server_close()

    restored_server, restored_thread = _start_test_server(
        workspace_state_path=workspace_state_path
    )
    try:
        restored_base_url = f"http://127.0.0.1:{restored_server.server_address[1]}"
        with urllib.request.urlopen(f"{restored_base_url}/api/workbench/graph") as response:
            restored_payload = json.loads(response.read().decode("utf-8"))

        assert restored_payload["graph_model"]["nodes"][0]["display_name"] == "HTTP Request"
        assert restored_payload["graph_model"]["nodes"][0]["node_config"]["method"] == "GET"
        assert restored_payload["graph_model"]["viewport"]["zoom"] == 1.1
        assert restored_payload["view"]["graph_document_save_revision"] == 1
        assert restored_payload["view"]["graph_document_saved_at"]
    finally:
        restored_server.shutdown()
        restored_server.server_close()


def test_http_api_exposes_graph_node_draft_endpoint(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/graph/node-draft?resource_key=flow.start"
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["resource"]["resource_key"] == "flow.start"
        assert payload["node"]["node_kind"] == "flow.start"
        assert payload["node"]["lowered_kind"] == "control"
        assert payload["node"]["display_name"] == "开始"
        assert payload["node"]["ports"] == [
            {
                "port_id": "out",
                "direction": "output",
                "relation_layer": "control",
                "semantic_slot": "out.control",
            },
            {
                "port_id": "out:variables",
                "direction": "output",
                "relation_layer": "data",
                "semantic_slot": "out.variables",
            }
        ]
        assert payload["node"]["node_config"] == {
            "initial_variables": {},
            "browser_config": {
                "headless": True,
                "slow_mo_ms": 0,
            },
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_updates_project_runtime_defaults_and_returns_projection_refresh(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_payload = json.dumps({"project_name": "Projection Project"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        runtime_defaults_payload = json.dumps(
            {
                "runtime_defaults": {
                    "initial_variables": {"username": "api-user", "base_url": "http://projection.test"},
                    "browser_config": {"headless": False, "slow_mo_ms": 220},
                    "execution_defaults": {"default_timeout_ms": 50000, "default_retry_count": 1},
                }
            }
        ).encode("utf-8")
        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/runtime-defaults",
            data=runtime_defaults_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "updated"
        assert payload["runtime_defaults"]["initial_variables"]["username"] == "api-user"
        assert payload["graph_projection_refresh"]["node_id"] == "node-start"
        assert payload["graph_projection_refresh"]["node_config"]["browser_config"]["slow_mo_ms"] == 220
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_preflight_returns_blocking_diagnostics(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "preflight-api.weconduct.json"

        create_payload = json.dumps({"project_name": "Preflight API Project"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            current_settings_payload = json.loads(response.read().decode("utf-8"))

        project_settings_payload = json.dumps(
            {
                "project_settings": {
                    **current_settings_payload["project_settings"],
                    "external_resources": [
                        {
                            "resource_id": "ext_required_file",
                            "bind_key": "upload_path",
                            "kind": "file",
                            "required": True,
                            "picker": "file",
                            "description": "上传文件",
                            "example_value": "C:\\data\\upload.txt",
                            "target": {"type": "initial_variable", "name": "upload_path"},
                            "validation": {"must_exist": True},
                        }
                    ],
                }
            }
        ).encode("utf-8")
        update_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=project_settings_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(update_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        preflight_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/preflight",
            data=json.dumps({"mode": "wcrun", "source_of_truth": "saved_project_only"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(preflight_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["summary"]["blocking"] is True
            assert any(entry["resource_id"] == "ext_required_file" for entry in payload["entries"])
        else:
            raise AssertionError("expected HTTPError for blocking package preflight diagnostics")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_build_returns_archive_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "package-api.weconduct.json"
        output_path = tmp_path / "dist" / "package-api.wcrun"

        create_payload = json.dumps({"project_name": "Package API Project"}).encode("utf-8")
        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        runtime_defaults_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/runtime-defaults",
            data=json.dumps(
                {
                    "runtime_defaults": {
                        "initial_variables": {"base_url": "http://api-package.test"},
                        "browser_config": {"headless": True, "slow_mo_ms": 0},
                        "execution_defaults": {},
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_defaults_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "node_config": {
                                "initial_variables": {
                                    "base_url": "http://api-package.test",
                                },
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                            },
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        build_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/build",
            data=json.dumps(
                {
                    "mode": "wcrun",
                    "source_of_truth": "saved_project_only",
                    "output_path": str(output_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "built"
        assert payload["package"]["mode"] == "wcrun"
        assert payload["package"]["output_path"] == str(output_path.resolve())
        assert payload["package_info"]["package_name"] == "package-api"
        assert payload["package_info"]["package_version"] == "0.1.0"
        assert payload["summary"]["embedded_resource_count"] == 0
        assert payload["summary"]["external_resource_count"] == 0
        assert payload["summary"]["graph_count"] == 1
        assert payload["diagnostics"]["total_count"] == 0
        assert payload["diagnostics"]["highest_severity"] is None
        assert payload["diagnostics"]["entries"] == []
        with zipfile.ZipFile(output_path) as archive:
            manifest_payload = unpackb(archive.read("manifest.msgpack"))
            package_info_payload = json.loads(archive.read("meta/package-info.json").decode("utf-8"))
        assert manifest_payload["manifest_version"] == 1
        assert manifest_payload["package_identity"]["package_name"] == "package-api"
        assert manifest_payload["source_project"]["project_name"] == "Package API Project"
        assert manifest_payload["entrypoint"]["graph_path"] == "graphs/main.graph.msgpack"
        assert manifest_payload["runtime_requirements"]["required_browser"] == "msedge"
        assert package_info_payload["manifest_version"] == 1
        assert package_info_payload["builder_app_version"] == "0.7.1"
        assert package_info_payload["source_project_schema_version"] == "project-v2"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_build_returns_blocking_diagnostics(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "package-api-failed.weconduct.json"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Package API Failed Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        save_updated_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_updated_request):
            pass

        build_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/build",
            data=json.dumps({"mode": "wcrun", "source_of_truth": "saved_project_only"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(build_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["summary"]["blocking"] is True
            assert payload["diagnostics"]["total_count"] >= 1
            assert payload["diagnostics"]["highest_severity"] == "fatal"
            assert any(
                entry["category"] == "graph.flow_start.invalid_entry_count"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected HTTPError for blocking package build diagnostics")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_open_legacy_v1_project_allows_package_preflight_and_build_with_flow_start_backfill(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        legacy_project_path = tmp_path / "legacy-http-package.weconduct.json"
        output_path = tmp_path / "dist" / "legacy-http-package.wcrun"
        legacy_payload = {
            "project_file_schema_version": 1,
            "saved_at": "2026-06-18T00:00:00Z",
            "project": {
                "project_id": "legacy-http-package",
                "project_name": "Legacy HTTP Package",
                "project_schema_version": "project-v1",
                "project_status": "ready",
                "workspace_root": str(tmp_path),
                "source_of_truth": "graph_document",
                "main_graph_document_id": "graph:workspace",
                "resource_registry_revision": 0,
            },
            "resource_registry": [],
            "editor_history": {"undo_stack": [], "redo_stack": []},
            "execution_history": {"runtime_runs": [], "debug_sessions": []},
            "graph_document": {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-start",
                        "lowered_kind": "control",
                        "source_anchor_ref": "n-node-start",
                        "expansion_role": "flow.start",
                        "display_name": "流程入口",
                        "node_kind": "flow.start",
                        "node_config": {
                            "initial_variables": {"base_url": "http://legacy-http-package.test"},
                            "browser_config": {"headless": True, "slow_mo_ms": 0},
                        },
                        "ports": [
                            {
                                "port_id": "control-out",
                                "direction": "output",
                                "relation_layer": "control",
                                "semantic_slot": "control.next",
                            }
                        ],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            },
            "graph_document_meta": {"save_revision": 0, "saved_at": None},
        }
        legacy_project_path.write_text(
            json.dumps(legacy_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        open_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/open",
            data=json.dumps({"project_path": str(legacy_project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(open_request):
            pass

        preflight_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/preflight",
            data=json.dumps({"mode": "wcrun", "source_of_truth": "saved_project_only"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(preflight_request) as response:
            preflight_payload = json.loads(response.read().decode("utf-8"))

        build_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/build",
            data=json.dumps(
                {
                    "mode": "wcrun",
                    "source_of_truth": "saved_project_only",
                    "output_path": str(output_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_request) as response:
            build_payload = json.loads(response.read().decode("utf-8"))

        assert preflight_payload["status"] == "ok"
        assert preflight_payload["summary"]["blocking"] is False
        assert build_payload["status"] == "built"
        assert build_payload["package"]["output_path"] == str(output_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_package_preflight_and_build_backfill_stale_workspace_runtime_defaults(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "stale-http-workspace.weconduct.json"
        output_path = tmp_path / "dist" / "stale-http-workspace.wcrun"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Stale HTTP Workspace"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "node_config": {
                                "initial_variables": {
                                    "base_url": "http://stale-http-workspace.test",
                                    "username": "http-user",
                                },
                                "browser_config": {"headless": True, "slow_mo_ms": 90},
                            },
                            "ports": [
                                {
                                    "port_id": "control-out",
                                    "direction": "output",
                                    "relation_layer": "control",
                                    "semantic_slot": "control.next",
                                }
                            ],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass
    finally:
        server.shutdown()
        server.server_close()

    stale_workspace_state = json.loads(workspace_state_path.read_text(encoding="utf-8"))
    stale_workspace_state["project_settings"]["runtime_defaults"] = {
        "initial_variables": {},
        "browser_config": {},
        "execution_defaults": {},
    }
    workspace_state_path.write_text(
        json.dumps(stale_workspace_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    restored_server, restored_thread = _start_test_server(workspace_state_path=workspace_state_path)
    try:
        restored_base_url = f"http://127.0.0.1:{restored_server.server_address[1]}"

        with urllib.request.urlopen(
            f"{restored_base_url}/api/workbench/project/settings"
        ) as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        preflight_request = urllib.request.Request(
            f"{restored_base_url}/api/workbench/project/package/preflight",
            data=json.dumps({"mode": "wcrun", "source_of_truth": "saved_project_only"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(preflight_request) as response:
            preflight_payload = json.loads(response.read().decode("utf-8"))

        build_request = urllib.request.Request(
            f"{restored_base_url}/api/workbench/project/package/build",
            data=json.dumps(
                {
                    "mode": "wcrun",
                    "source_of_truth": "saved_project_only",
                    "output_path": str(output_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_request) as response:
            build_payload = json.loads(response.read().decode("utf-8"))

        assert settings_payload["project_settings"]["runtime_defaults"]["initial_variables"]["base_url"] == (
            "http://stale-http-workspace.test"
        )
        assert settings_payload["state"]["source"] == "project_settings_file"
        assert preflight_payload["status"] == "ok"
        assert preflight_payload["summary"]["blocking"] is False
        assert build_payload["status"] == "built"
        assert build_payload["package"]["output_path"] == str(output_path.resolve())
    finally:
        restored_server.shutdown()
        restored_server.server_close()


def test_http_api_project_package_build_persists_resource_archive_and_manifest_summary(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    embedded_file = tmp_path / "fixtures" / "api-upload.txt"
    embedded_file.parent.mkdir(parents=True, exist_ok=True)
    embedded_file.write_text("api-embedded-content", encoding="utf-8")
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "package-api-resource.weconduct.json"
        output_path = tmp_path / "dist" / "package-api-resource.wcrun"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Package API Resource Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:api-resource-source",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        save_custom_resource_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/custom-node-graphs",
            data=json.dumps({"resource_name": "API Shared Login"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_custom_resource_request) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        settings_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        "project_identity": {"name": "Package API Resource Project"},
                        "runtime_defaults": {
                            "initial_variables": {"base_url": "http://api-package.test"},
                            "browser_config": {"headless": True, "slow_mo_ms": 0},
                            "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                        },
                        "packaging": {
                            "default_output_name": "package-api-resource.wcrun",
                            "include_embedded_resources": True,
                            "staged_execution": True,
                            "include_execution_history": False,
                            "include_editor_history": False,
                        },
                        "external_resources": [],
                        "resource_policy": {
                            "embedded_resources": [str(embedded_file)],
                            "external_resource_bindings": [],
                        },
                        "compile_profile": {
                            "source_of_truth": "saved_project_only",
                            "inject_project_runtime_defaults_into_main_flow_start": True,
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(settings_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        build_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/build",
            data=json.dumps(
                {
                    "mode": "wcrun",
                    "source_of_truth": "saved_project_only",
                    "output_path": str(output_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "built"
        with zipfile.ZipFile(output_path) as archive:
            manifest_payload = unpackb(archive.read("manifest.msgpack"))
            package_info_payload = json.loads(archive.read("meta/package-info.json").decode("utf-8"))
            assert any(
                item["resource_id"] == resource_payload["resource"]["resource_id"]
                for item in manifest_payload["dependencies"]["custom_components"]
            )
            assert manifest_payload["resources"]["embedded"][0]["archive_path"] == "resources/embedded/api-upload.txt"
            assert package_info_payload["msgpack_encoding"]["status"] == "msgpack"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_inspect_and_load_returns_session_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    embedded_file = tmp_path / "fixtures" / "inspect-api.txt"
    embedded_file.parent.mkdir(parents=True, exist_ok=True)
    embedded_file.write_text("inspect-api-content", encoding="utf-8")
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "inspect-api.weconduct.json"
        output_path = tmp_path / "dist" / "inspect-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Inspect API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:inspect-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/resources/custom-node-graphs",
                data=json.dumps({"resource_name": "Inspect API Resource"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "Inspect API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://inspect-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "inspect-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [],
                            "resource_policy": {
                                "embedded_resources": [str(embedded_file)],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/project/package/inspect?package_path={urllib.parse.quote(str(output_path))}"
        ) as response:
            inspect_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            load_payload = json.loads(response.read().decode("utf-8"))

        assert inspect_payload["status"] == "ok"
        assert inspect_payload["package"]["manifest"]["source_project"]["project_name"] == "Inspect API Project"
        assert inspect_payload["package"]["manifest"]["entrypoint"]["graph_path"] == "graphs/main.graph.msgpack"
        assert inspect_payload["package_summary"]["package_identity"]["package_name"] == "inspect-api"
        assert inspect_payload["package_summary"]["runtime_requirements"]["required_browser"] == "msedge"
        assert inspect_payload["package_summary"]["graph_summary"]["graph_count"] == 2
        assert inspect_payload["project_settings_summary"]["project_identity"]["name"] == "Inspect API Project"
        assert (
            inspect_payload["project_settings_summary"]["runtime_defaults"]["initial_variables"]["base_url"]
            == "http://inspect-api.test"
        )
        assert inspect_payload["project_settings_summary"]["packaging"]["default_output_name"] == "inspect-api.wcrun"
        assert inspect_payload["resource_summary"]["embedded_resource_count"] == 1
        assert inspect_payload["resource_summary"]["custom_component_count"] == 1
        assert (
            inspect_payload["dependency_summary"]["builtin_component_count"]
            == len(inspect_payload["package"]["dependencies"]["builtin_components"])
        )
        assert inspect_payload["dependency_summary"]["custom_component_count"] == 1
        assert inspect_payload["graph_detail_summary"]["entrypoint_graph_id"] == "graph:inspect-api"
        assert inspect_payload["graph_detail_summary"]["main_graph"]["graph_id"] == "graph:inspect-api"
        assert inspect_payload["graph_detail_summary"]["graph_count"] == 2
        assert inspect_payload["external_binding_summary"]["declared_count"] == 0
        assert inspect_payload["external_binding_summary"]["required_count"] == 0
        assert inspect_payload["runtime_requirement_summary"]["required_browser"] == "msedge"
        assert inspect_payload["runtime_requirement_summary"]["blocking_count"] == 0
        assert inspect_payload["runtime_readiness_summary"]["ready"] is True
        assert inspect_payload["runtime_readiness_summary"]["runtime_requirement_status"]["blocking_count"] == 0
        assert load_payload["status"] == "loaded"
        assert load_payload["package"]["session_dir"] is not None
        assert load_payload["project"]["source_of_truth"] == "wcrun_package"
        assert load_payload["package_summary"]["package_identity"]["package_name"] == "inspect-api"
        assert load_payload["package_summary"]["entrypoint"]["graph_path"] == "graphs/main.graph.msgpack"
        assert load_payload["package_summary"]["graph_summary"]["main_graph_id"] == "graph:inspect-api"
        assert load_payload["package_summary"]["graph_summary"]["graph_count"] == 2
        assert load_payload["project_settings_summary"]["project_identity"]["name"] == "Inspect API Project"
        assert load_payload["project_settings_summary"]["compile_profile"]["source_of_truth"] == "saved_project_only"
        assert load_payload["resource_summary"]["embedded_resource_count"] == 1
        assert load_payload["resource_summary"]["custom_component_count"] == 1
        assert (
            load_payload["dependency_summary"]["builtin_component_count"]
            == len(load_payload["package"]["dependencies"]["builtin_components"])
        )
        assert load_payload["dependency_summary"]["custom_component_count"] == 1
        assert load_payload["graph_detail_summary"]["entrypoint_graph_path"] == "graphs/main.graph.msgpack"
        assert load_payload["graph_detail_summary"]["custom_component_graph_count"] == 1
        assert load_payload["session_restore_summary"]["source_of_truth"] == "wcrun_package"
        assert load_payload["session_restore_summary"]["project_status"] == "loaded_from_package"
        assert load_payload["session_restore_summary"]["session_dir"] == load_payload["package"]["session_dir"]
        assert load_payload["session_restore_summary"]["graph_workspace_graph_id"] == "graph:inspect-api"
        assert load_payload["external_binding_summary"]["declared_count"] == 0
        assert load_payload["external_binding_summary"]["bound_count"] == 0
        assert load_payload["runtime_requirement_summary"]["required_platform"] == "windows"
        assert load_payload["runtime_requirement_summary"]["requires_captcha_ocr"] is False
        assert load_payload["runtime_readiness_summary"]["ready"] is True
        assert load_payload["runtime_readiness_summary"]["external_resource_binding_status"]["required_count"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_package_load_rewrites_embedded_runtime_default_paths(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        builder = CompilationWorkbenchService()
        project_path = tmp_path / "embedded-api-rewrite.weconduct.json"
        output_path = tmp_path / "dist" / "embedded-api-rewrite.wcrun"
        embedded_file = tmp_path / "input" / "upload-sample.txt"
        embedded_file.parent.mkdir(parents=True, exist_ok=True)
        embedded_file.write_text("embedded-api-content", encoding="utf-8")

        builder.create_project(project_name="Embedded API Rewrite Project")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:embedded-api-rewrite",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "runtime_defaults": {
                    "initial_variables": {
                        "base_url": "http://embedded-api.test",
                        "upload_file_path": "input/upload-sample.txt",
                    },
                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                    "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                },
                "resource_policy": {
                    "embedded_resources": ["input/upload-sample.txt"],
                    "external_resource_bindings": [],
                },
                "packaging": {
                    **builder.get_project_settings_document()["project_settings"]["packaging"],
                    "include_embedded_resources": True,
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        build_result = builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )
        assert build_result["status"] == "built"

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            load_payload = json.loads(response.read().decode("utf-8"))

        session_dir = Path(load_payload["package"]["session_dir"])
        expected_runtime_path = session_dir / "resources" / "embedded" / "upload-sample.txt"
        actual_runtime_path = (
            load_payload["project_settings"]["runtime_defaults"]["initial_variables"]["upload_file_path"]
        )

        assert load_payload["status"] == "loaded"
        assert expected_runtime_path.exists() is True
        assert actual_runtime_path == str(expected_runtime_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_sensitive_get_requires_token_when_server_token_is_configured(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server = ApiTestServer(("127.0.0.1", 0), WeConductApiHandler)
    server.workspace_state_path = workspace_state_path
    server.api_token = "phase17-secret"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/workbench/project")
        assert exc_info.value.code == 401

        request = urllib.request.Request(
            f"{base_url}/api/workbench/project",
            headers={"X-WeConduct-Token": "phase17-secret"},
            method="GET",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["project"]["loaded"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_build_allows_non_browser_project_without_base_url(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "package-api-non-browser.weconduct.json"
        output_path = tmp_path / "dist" / "package-api-non-browser.wcrun"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Package API Non Browser Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-start",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-node-start",
                            "expansion_role": "flow.start",
                            "display_name": "流程入口",
                            "node_kind": "flow.start",
                            "node_config": {
                                "initial_variables": {},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                            },
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        save_updated_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_updated_request):
            pass

        build_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/package/build",
            data=json.dumps(
                {
                    "mode": "wcrun",
                    "source_of_truth": "saved_project_only",
                    "output_path": str(output_path),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "built"
        assert output_path.exists() is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_inspect_package_reports_missing_python_runtime_manifest(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        builder = CompilationWorkbenchService()
        project_path = tmp_path / "python-runtime-api.weconduct.json"
        output_path = tmp_path / "dist" / "python-runtime-api.wcrun"

        builder.create_project(project_name="Python Runtime API Inspect")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:python-runtime-api",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-start",
                        "lowered_kind": "control",
                        "source_anchor_ref": "n-node-start",
                        "expansion_role": "flow.start",
                        "display_name": "流程入口",
                        "node_kind": "flow.start",
                        "node_config": {
                            "initial_variables": {"base_url": "http://python-runtime-api.test"},
                            "browser_config": {"headless": True, "slow_mo_ms": 0},
                        },
                        "ports": [],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "python_runtime_profile": {
                    **builder.get_project_settings_document()["project_settings"]["python_runtime_profile"],
                    "runtime_enabled": True,
                    "cache_location_mode": "project_cache",
                    "package_embed_mode": "wheelhouse_rebuild",
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        build_result = builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )
        assert build_result["status"] == "built"

        tampered_path = tmp_path / "dist" / "python-runtime-api-tampered.wcrun"
        with zipfile.ZipFile(output_path, "r") as source_archive, zipfile.ZipFile(
            tampered_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as target_archive:
            for info in source_archive.infolist():
                payload = source_archive.read(info.filename)
                if info.filename == "python-runtime/manifest.json":
                    payload = b"{}"
                if info.filename == "meta/checksums.json":
                    checksums_payload = json.loads(payload.decode("utf-8"))
                    for entry in checksums_payload["entries"]:
                        if entry["path"] == "python-runtime/manifest.json":
                            entry["sha256"] = hashlib.sha256(b"{}").hexdigest()
                            entry["size"] = len(b"{}")
                    payload = json.dumps(
                        checksums_payload,
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8")
                target_archive.writestr(info, payload)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        inspect_url = (
            f"{base_url}/api/workbench/project/package/inspect"
            f"?package_path={urllib.parse.quote(str(tampered_path))}"
        )
        with urllib.request.urlopen(inspect_url) as response:
            inspect_payload = json.loads(response.read().decode("utf-8"))

        assert inspect_payload["status"] == "ok"
        assert inspect_payload["runtime_readiness_summary"]["ready"] is False
        assert inspect_payload["runtime_readiness_summary"]["python_runtime_status"]["required"] is True
        assert any(
            entry["category"] == "package.python_runtime.manifest_hash_mismatch"
            for entry in inspect_payload["runtime_readiness_summary"]["diagnostics"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_wcrun_package_rejects_graph_save_and_project_save_as(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        builder = CompilationWorkbenchService()
        project_path = tmp_path / "readonly-api.weconduct.json"
        output_path = tmp_path / "dist" / "readonly-api.wcrun"

        builder.create_project(project_name="Readonly API Project")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:readonly-api",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "runtime_defaults": {
                    "initial_variables": {"base_url": "http://readonly-api-source.test"},
                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                    "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        build_result = builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )
        assert build_result["status"] == "built"

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        graph_save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:readonly-api",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            urllib.request.urlopen(graph_save_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "project_package_read_only"
        else:
            raise AssertionError("expected graph save to be rejected for loaded wcrun package")

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(tmp_path / 'copy.weconduct.json')}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(save_as_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "project_package_read_only"
        else:
            raise AssertionError("expected project save-as to be rejected for loaded wcrun package")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_wcrun_package_allows_runtime_defaults_but_rejects_project_settings(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        builder = CompilationWorkbenchService()
        project_path = tmp_path / "readonly-settings-api.weconduct.json"
        output_path = tmp_path / "dist" / "readonly-settings-api.wcrun"

        builder.create_project(project_name="Readonly Settings API Project")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:readonly-settings-api",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "runtime_defaults": {
                    "initial_variables": {"base_url": "http://readonly-settings-api-source.test"},
                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                    "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        build_result = builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )
        assert build_result["status"] == "built"

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/project/settings") as response:
            settings_payload = json.loads(response.read().decode("utf-8"))

        project_settings_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/settings",
            data=json.dumps(
                {
                    "project_settings": {
                        **settings_payload["project_settings"],
                        "project_identity": {
                            **settings_payload["project_settings"]["project_identity"],
                            "description": "blocked",
                        },
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(project_settings_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "project_package_read_only"
        else:
            raise AssertionError("expected project settings update to be rejected for loaded wcrun package")

        runtime_defaults_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/runtime-defaults",
            data=json.dumps(
                {
                    "runtime_defaults": {
                        "initial_variables": {"base_url": "http://readonly-settings-api.test"},
                        "browser_config": {"headless": False, "slow_mo_ms": 0},
                        "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_defaults_request) as response:
            runtime_defaults_payload = json.loads(response.read().decode("utf-8"))

        assert runtime_defaults_payload["status"] == "updated"
        assert runtime_defaults_payload["runtime_defaults"]["browser_config"]["headless"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_wcrun_package_rejects_runtime_start_with_graph_document_payload(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        builder = CompilationWorkbenchService()
        project_path = tmp_path / "readonly-runtime-payload-api.weconduct.json"
        output_path = tmp_path / "dist" / "readonly-runtime-payload-api.wcrun"

        builder.create_project(project_name="Readonly Runtime Payload API Project")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:readonly-runtime-payload-api",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "runtime_defaults": {
                    "initial_variables": {"base_url": "http://readonly-runtime-payload-api-source.test"},
                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                    "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        build_result = builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )
        assert build_result["status"] == "built"

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/graph") as response:
            graph_payload = json.loads(response.read().decode("utf-8"))

        assert graph_payload["view"]["is_editable"] is False

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps(
                {
                    "graph_document": {
                        "graph_model_id": "graph:readonly-runtime-payload-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "project_package_read_only"
        else:
            raise AssertionError("expected runtime start with graph payload to be rejected for loaded wcrun package")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_inspect_reports_runtime_readiness_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "inspect-readiness-api.weconduct.json"
        output_path = tmp_path / "dist" / "inspect-readiness-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Inspect Readiness API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:inspect-readiness-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-start",
                                "lowered_kind": "control",
                                "source_anchor_ref": "n-node-start",
                                "expansion_role": "flow.start",
                                "display_name": "流程入口",
                                "node_kind": "flow.start",
                                "node_config": {
                                    "initial_variables": {"base_url": "http://inspect-readiness-api.test"},
                                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                                },
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "Inspect Readiness API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://inspect-readiness-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "inspect-readiness-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        _rewrite_wcrun_manifest(
            output_path,
            lambda manifest_payload: manifest_payload["runtime_requirements"].update(
                {
                    "minimum_app_version": "9.9.9",
                    "required_browser": "chrome",
                }
            ),
        )
        _rewrite_wcrun_project_settings(
            output_path,
            lambda project_settings_payload: project_settings_payload.__setitem__(
                "external_resources",
                [
                    {
                        "resource_id": "ext-required-file",
                        "resource_key": "external.required_file",
                        "display_name": "Required File",
                        "description": "外部文件",
                        "target": {"type": "initial_variable", "name": "upload_path"},
                        "required": True,
                    }
                ],
            ),
        )
        monkeypatch.setattr(
            CompilationWorkbenchService,
            "_probe_captcha_ocr_runtime_requirement",
            lambda self: (True, "captcha_ocr runtime available"),
            raising=False,
        )

        with urllib.request.urlopen(
            f"{base_url}/api/workbench/project/package/inspect?package_path={urllib.parse.quote(str(output_path))}"
        ) as response:
            inspect_payload = json.loads(response.read().decode("utf-8"))

        assert inspect_payload["runtime_readiness_summary"]["ready"] is False
        assert inspect_payload["runtime_readiness_summary"]["runtime_requirement_status"]["blocking_count"] == 2
        assert (
            inspect_payload["runtime_readiness_summary"]["external_resource_binding_status"]["missing_required_count"]
            == 1
        )
        assert inspect_payload["runtime_requirement_summary"]["blocking_count"] == 2
        assert "package.runtime_requirement.minimum_app_version_unsupported" in (
            inspect_payload["runtime_requirement_summary"]["blocking_categories"]
        )
        assert inspect_payload["external_binding_summary"]["declared_count"] == 1
        assert inspect_payload["external_binding_summary"]["missing_required_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_load_restores_full_custom_component_resource_record(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "load-resource-api.weconduct.json"
        output_path = tmp_path / "dist" / "load-resource-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Load Resource API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        input_graph_payload = {
            "graph_model_id": "graph:load-resource-api",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-component-input-text",
                    "lowered_kind": "bridge",
                    "source_anchor_ref": "n-node-component-input-text",
                    "expansion_role": "component.input",
                    "display_name": "输入参数",
                    "node_kind": "component.input",
                    "node_config": {
                        "name": "username",
                        "value_type": "string",
                        "required": True,
                        "default_value": "demo-user",
                        "description": "用户名",
                    },
                    "ports": [],
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(input_graph_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/resources/custom-node-graphs",
                data=json.dumps({"resource_name": "Restored Resource API"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            resource_payload = json.loads(response.read().decode("utf-8"))

        main_graph_payload = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-start",
                    "lowered_kind": "control",
                    "source_anchor_ref": "n-node-start",
                    "expansion_role": "flow.start",
                    "display_name": "流程入口",
                    "node_kind": "flow.start",
                    "node_config": {
                        "initial_variables": {"base_url": "http://restore-api.test"},
                        "browser_config": {"headless": True, "slow_mo_ms": 0},
                    },
                    "ports": [
                        {
                            "port_id": "control-out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "control.next",
                        }
                    ],
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(main_graph_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "Load Resource API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://restore-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "load-resource-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [],
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/resources") as response:
            resources_payload = json.loads(response.read().decode("utf-8"))

        restored = next(
            item
            for item in resources_payload["resources"]
            if item["resource_id"] == resource_payload["resource"]["resource_id"]
        )
        assert restored["display_name"] == "Restored Resource API"
        assert restored["origin"] == "package"
        assert restored["source_graph_document"]["nodes"][0]["node_id"] == "node-component-input-text"
        assert restored["source_graph_document"]["nodes"][0]["node_config"]["name"] == "username"
        assert restored["source_graph_document"]["nodes"][0]["node_config"]["value_type"] == "string"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_project_package_unload_cleans_session_dir_and_resets_workspace(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "unload-api.weconduct.json"
        output_path = tmp_path / "dist" / "unload-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Unload API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "Unload API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://unload-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "unload-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [],
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            load_payload = json.loads(response.read().decode("utf-8"))

        session_dir = Path(load_payload["package"]["session_dir"])
        assert session_dir.exists() is True

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/unload",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            unload_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert unload_payload["status"] == "unloaded"
        assert session_dir.exists() is False
        assert snapshot_payload["project"]["source_of_truth"] == "graph_document"
        assert snapshot_payload["project_settings"]["source_of_truth"] == "graph_document"
        assert snapshot_payload["project"]["project_file_path"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_requires_external_resource_binding_before_runtime_start(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "external-required-api.weconduct.json"
        output_path = tmp_path / "dist" / "external-required-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "External Required API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:external-required-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-request",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n-node-request",
                                "expansion_role": "action:request",
                                "display_name": "请求",
                                "node_kind": "http.request",
                                "node_config": {"url": "http://example.test", "method": "GET"},
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "External Required API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://external-required-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "external-required-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [
                                    {
                                        "resource_id": "ext-upload-file",
                                        "bind_key": "upload_path",
                                        "kind": "file",
                                        "required": False,
                                        "picker": "file",
                                        "description": "上传文件",
                                        "example_value": "C:\\data\\upload.txt",
                                        "target": {"type": "initial_variable", "name": "upload_path"},
                                        "validation": {"must_exist": False},
                                }
                            ],
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.external_resource.runtime_binding_required"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure for missing external resource binding")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_can_bind_external_resource_and_start_runtime(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    provided_file = tmp_path / "provided" / "upload.txt"
    provided_file.parent.mkdir(parents=True, exist_ok=True)
    provided_file.write_text("payload", encoding="utf-8")
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "external-bind-api.weconduct.json"
        output_path = tmp_path / "dist" / "external-bind-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "External Bind API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:external-bind-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-request",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n-node-request",
                                "expansion_role": "action:request",
                                "display_name": "请求",
                                "node_kind": "http.request",
                                "node_config": {"url": "http://example.test", "method": "GET"},
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "External Bind API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://external-bind-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "external-bind-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [
                                    {
                                        "resource_id": "ext-upload-file",
                                        "bind_key": "upload_path",
                                        "kind": "file",
                                        "required": False,
                                        "picker": "file",
                                        "description": "上传文件",
                                        "example_value": "C:\\data\\upload.txt",
                                        "target": {"type": "initial_variable", "name": "upload_path"},
                                        "validation": {"must_exist": False},
                                }
                            ],
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/external-resources/bind",
                data=json.dumps(
                    {
                        "resource_id": "ext-upload-file",
                        "value": str(provided_file),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            bind_payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/runtime/start",
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ) as response:
            runtime_payload = json.loads(response.read().decode("utf-8"))

        assert bind_payload["status"] == "bound"
        assert bind_payload["runtime_defaults"]["initial_variables"]["upload_path"] == str(provided_file.resolve())
        assert runtime_payload["status"] == "started"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_snapshot_project_settings_exposes_wcrun_state(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "snapshot-loaded-api.weconduct.json"
        output_path = tmp_path / "dist" / "snapshot-loaded-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Snapshot Loaded API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:snapshot-loaded-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-start",
                                "lowered_kind": "control",
                                "source_anchor_ref": "n-node-start",
                                "expansion_role": "flow.start",
                                "display_name": "流程入口",
                                "node_kind": "flow.start",
                                "node_config": {
                                    "initial_variables": {"base_url": "http://snapshot-loaded-api.test"},
                                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                                },
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/settings",
                data=json.dumps(
                    {
                        "project_settings": {
                            "project_identity": {"name": "Snapshot Loaded API Project"},
                            "runtime_defaults": {
                                "initial_variables": {"base_url": "http://snapshot-loaded-api.test"},
                                "browser_config": {"headless": True, "slow_mo_ms": 0},
                                "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                            },
                            "packaging": {
                                "default_output_name": "snapshot-loaded-api.wcrun",
                                "include_embedded_resources": True,
                                "staged_execution": True,
                                "include_execution_history": False,
                                "include_editor_history": False,
                            },
                            "external_resources": [
                                {
                                    "resource_id": "ext-upload-file",
                                    "bind_key": "upload_path",
                                    "kind": "file",
                                    "required": False,
                                    "picker": "file",
                                    "description": "上传文件",
                                    "example_value": "C:\\data\\upload.txt",
                                    "target": {"type": "initial_variable", "name": "upload_path"},
                                    "validation": {"must_exist": False},
                                }
                            ],
                            "resource_policy": {
                                "embedded_resources": [],
                                "external_resource_bindings": [],
                            },
                            "compile_profile": {
                                "source_of_truth": "saved_project_only",
                                "inject_project_runtime_defaults_into_main_flow_start": True,
                            },
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot_payload = json.loads(response.read().decode("utf-8"))

        assert snapshot_payload["project"]["source_of_truth"] == "wcrun_package"
        assert snapshot_payload["project_settings"]["loaded"] is True
        assert snapshot_payload["project_settings"]["source_of_truth"] == "wcrun_package"
        assert snapshot_payload["project_settings"]["state_source"] == "workspace_state"
        assert snapshot_payload["project_settings"]["project_file_path"] is None
        assert snapshot_payload["project_settings"]["project_settings_path"] is None
        assert isinstance(snapshot_payload["project_settings"]["session_dir"], str)
        assert snapshot_payload["project_settings"]["is_dirty"] is False
        assert snapshot_payload["project_settings"]["has_external_resources"] is True
        assert snapshot_payload["project_settings"]["external_resource_count"] == 1
        assert snapshot_payload["project_settings"]["package_default_output_name"] == "snapshot-loaded-api.wcrun"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_blocks_runtime_start_when_runtime_requirements_mismatch(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "runtime-requirements-api.weconduct.json"
        output_path = tmp_path / "dist" / "runtime-requirements-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Runtime Requirements API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:runtime-requirements-api",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-request",
                                "lowered_kind": "execution",
                                "source_anchor_ref": "n-node-request",
                                "expansion_role": "action:request",
                                "display_name": "请求",
                                "node_kind": "http.request",
                                "node_config": {"url": "http://example.test", "method": "GET"},
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/runtime-defaults",
                data=json.dumps(
                    {
                        "runtime_defaults": {
                            "initial_variables": {"base_url": "http://runtime-requirements-api.test"},
                            "browser_config": {"headless": True, "slow_mo_ms": 0},
                            "execution_defaults": {"default_timeout_ms": 30000, "default_retry_count": 0},
                        }
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        _rewrite_wcrun_manifest(
            output_path,
            lambda manifest_payload: manifest_payload["runtime_requirements"].__setitem__(
                "minimum_app_version",
                "9.9.9",
            ),
        )

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.runtime_requirement.minimum_app_version_unsupported"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure for incompatible package runtime requirements")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_blocks_runtime_start_when_required_platform_is_unsupported(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "required-platform-api.weconduct.json"
        output_path = tmp_path / "dist" / "required-platform-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Required Platform API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-start",
                                "lowered_kind": "control",
                                "source_anchor_ref": "n-node-start",
                                "expansion_role": "flow.start",
                                "display_name": "流程入口",
                                "node_kind": "flow.start",
                                "node_config": {
                                    "initial_variables": {"base_url": "http://required-platform-api.test"},
                                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                                },
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        _rewrite_wcrun_manifest(
            output_path,
            lambda manifest_payload: manifest_payload["runtime_requirements"].__setitem__(
                "required_platform",
                "linux",
            ),
        )
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.runtime_requirement.required_platform_unsupported"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure for unsupported package platform requirement")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_blocks_runtime_start_when_required_browser_is_unavailable(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "required-browser-api.weconduct.json"
        output_path = tmp_path / "dist" / "required-browser-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Required Browser API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-start",
                                "lowered_kind": "control",
                                "source_anchor_ref": "n-node-start",
                                "expansion_role": "flow.start",
                                "display_name": "流程入口",
                                "node_kind": "flow.start",
                                "node_config": {
                                    "initial_variables": {"base_url": "http://required-browser-api.test"},
                                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                                },
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        _rewrite_wcrun_manifest(
            output_path,
            lambda manifest_payload: manifest_payload["runtime_requirements"].__setitem__(
                "required_browser",
                "chrome",
            ),
        )
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.runtime_requirement.required_browser_unsupported"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure for unsupported package browser requirement")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_blocks_runtime_start_when_captcha_ocr_is_required_but_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "required-captcha-api.weconduct.json"
        output_path = tmp_path / "dist" / "required-captcha-api.wcrun"

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/new",
                data=json.dumps({"project_name": "Required Captcha API Project"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/graph",
                data=json.dumps(
                    {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [
                            {
                                "node_id": "node-start",
                                "lowered_kind": "control",
                                "source_anchor_ref": "n-node-start",
                                "expansion_role": "flow.start",
                                "display_name": "流程入口",
                                "node_kind": "flow.start",
                                "node_config": {
                                    "initial_variables": {"base_url": "http://required-captcha-api.test"},
                                    "browser_config": {"headless": True, "slow_mo_ms": 0},
                                },
                                "ports": [],
                            }
                        ],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/save-as",
                data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/build",
                data=json.dumps(
                    {
                        "mode": "wcrun",
                        "source_of_truth": "saved_project_only",
                        "output_path": str(output_path),
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass
        _rewrite_wcrun_manifest(
            output_path,
            lambda manifest_payload: manifest_payload["runtime_requirements"].__setitem__(
                "requires_captcha_ocr",
                True,
            ),
        )
        monkeypatch.setattr(
            CompilationWorkbenchService,
            "_probe_captcha_ocr_runtime_requirement",
            lambda self: (False, "captcha_ocr runtime not found"),
            raising=False,
        )
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(output_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.runtime_requirement.captcha_ocr_unavailable"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure when captcha_ocr runtime is unavailable")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_rejects_unknown_graph_node_draft_resource_key(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        try:
            urllib.request.urlopen(
                f"{base_url}/api/workbench/graph/node-draft?resource_key=missing.node"
            )
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "invalid_request"
            assert payload["message"] == "resource not found for graph node draft: missing.node"
        else:
            raise AssertionError("expected HTTPError for unknown graph node draft resource_key")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_graph_save_updates_open_project_file_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "graph-save-sync.weconduct.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Graph Save Sync"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        graph_save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-project-sync",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-project-sync",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "message", "value": "from-http-graph-save"},
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_save_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        storage_root = project_path.parent / f"{project_path.stem}.data"
        project_payload = json.loads(project_path.read_text(encoding="utf-8"))
        graph_payload = json.loads(
            (storage_root / "graphs" / "workspace.graph.json").read_text(
                encoding="utf-8"
            )
        )

        assert payload["status"] == "saved"
        assert payload["view"]["graph_document_save_revision"] == 1
        assert project_payload["project_file_schema_version"] == 2
        assert graph_payload["nodes"][0]["node_id"] == "node-project-sync"
        assert graph_payload["nodes"][0]["node_config"]["value"] == "from-http-graph-save"
        assert project_payload["graph_document_meta"]["save_revision"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_rejects_graph_save_when_expected_revision_is_stale(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {},
                "compile_settings": {},
                "security_settings": {},
                "python_runtime_settings": {},
                "graph_settings": {
                    "save_conflict_policy": "strict",
                },
                "other_settings": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        initial_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        initial_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=initial_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(initial_request):
            pass

        stale_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
                "expected_graph_document_save_revision": 0,
            }
        ).encode("utf-8")
        stale_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=stale_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )

        try:
            urllib.request.urlopen(stale_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 409
            assert payload == {
                "error": "graph_revision_conflict",
                "message": "graph document save revision conflict: expected 0, current 1",
            }
        else:
            raise AssertionError("expected HTTPError for stale graph save revision")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_prefers_current_graph_when_stale_save_revision_and_policy_allows(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {},
                "compile_settings": {},
                "security_settings": {},
                "python_runtime_settings": {},
                "graph_settings": {
                    "save_conflict_policy": "prefer_current_graph",
                },
                "other_settings": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        initial_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-first",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n-first",
                        "expansion_role": "action:set_variable",
                        "node_kind": "data.set_variable",
                        "node_config": {"name": "message", "value": "first"},
                        "ports": [],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        initial_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=initial_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(initial_request):
            pass

        stale_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-second",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n-second",
                        "expansion_role": "action:set_variable",
                        "node_kind": "data.set_variable",
                        "node_config": {"name": "message", "value": "second"},
                        "ports": [],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
                "expected_graph_document_save_revision": 0,
            }
        ).encode("utf-8")
        stale_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=stale_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )

        with urllib.request.urlopen(stale_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "saved"
        assert payload["view"]["graph_document_save_revision"] == 2
        assert payload["graph_model"]["nodes"][0]["node_id"] == "node-second"
        assert project_payload["graph_workspace"]["graph_document_save_revision"] == 2
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_validates_graph_workspace_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        validate_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    }
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "relation_layer": "data",
                        "from_node_id": "node-1",
                        "to_node_id": "missing-node",
                        "from_port_id": "out",
                        "to_port_id": "in",
                    }
                ],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        validate_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/validate",
            data=validate_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(validate_request) as response:
            validation_payload = json.loads(response.read().decode("utf-8"))

        assert validation_payload["status"] == "invalid"
        assert validation_payload["summary"]["error_count"] == 1
        assert validation_payload["diagnostics"][0]["diagnostic_id"].startswith("graph-validate-")
        assert validation_payload["diagnostics"][0]["stage"] == "validate"
        assert validation_payload["diagnostics"][0]["severity"] == "fatal"
        assert validation_payload["diagnostics"][0]["category"] == "graph.edge.missing_target_node"
        assert validation_payload["diagnostics"][0]["stage_extension"] == {
            "subject_ref": "edge-1",
            "action": "validated graph document",
            "rule": "graph.edge.target_node_exists",
            "result": "failed",
            "graph_ref": {
                "graph_model_id": "graph:workspace",
                "edge_id": "edge-1",
                "from_node_id": "node-1",
                "to_node_id": "missing-node",
                "from_port_id": "out",
                "to_port_id": "in",
            },
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_records_failed_graph_compile_in_snapshot(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    }
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "relation_layer": "data",
                        "from_node_id": "node-1",
                        "to_node_id": "missing-node",
                        "from_port_id": "out",
                        "to_port_id": "in",
                    }
                ],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "failed"
        assert compile_result["request"]["request_origin"] == "graph_document"
        assert compile_result["request"]["requested_graph_model_id"] == "graph:workspace"
        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["request"]["requested_graph_saved_at"]
        assert snapshot["workbench"]["compile_counter"] == 1
        assert snapshot["project"]["last_compile_status"] == "failed"
        assert snapshot["last_compile"]["source_kind"] == "graph_workspace"
        assert snapshot["last_compile"]["request_origin"] == "graph_document"
        assert snapshot["last_compile"]["requested_graph_model_id"] == "graph:workspace"
        assert snapshot["last_compile"]["requested_graph_save_revision"] == 1
        assert snapshot["last_compile"]["primary_diagnostic"]["category"] == "graph.edge.missing_target_node"
        assert snapshot["last_compile"]["duration_ms"] is not None
        assert isinstance(snapshot["last_compile"]["duration_ms"], int)
        assert snapshot["last_compile"]["duration_ms"] >= 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_compiles_graph_workspace_document(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "display_name": "HTTP Request",
                        "node_kind": "http.request",
                        "position": {"x": 120, "y": 80},
                        "ports": [
                            {
                                "port_id": "out-main",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.result",
                            }
                        ],
                        "node_config": {"method": "GET"},
                    },
                    {
                        "node_id": "node-2",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n2",
                        "expansion_role": "transform:map",
                        "display_name": "Map Result",
                        "node_kind": "data.map",
                        "position": {"x": 360, "y": 80},
                        "ports": [
                            {
                                "port_id": "in-main",
                                "direction": "input",
                                "relation_layer": "data",
                                "semantic_slot": "in.default",
                            }
                        ],
                        "node_config": {"mode": "map"},
                    },
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "relation_layer": "data",
                        "from_node_id": "node-1",
                        "to_node_id": "node-2",
                        "from_port_id": "out-main",
                        "to_port_id": "in-main",
                        "edge_state": "draft",
                    }
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 1.1},
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "succeeded"
        assert compile_result["request"]["source"]["kind"] == "graph_workspace"
        assert compile_result["request"]["request_origin"] == "graph_document"
        assert compile_result["request"]["requested_graph_model_id"] == "graph:workspace"
        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["request"]["requested_graph_saved_at"]
        assert compile_result["view"]["graph_stats"]["node_count"] == 2
        assert compile_result["view"]["graph_stats"]["edge_count"] == 1
        assert compile_result["outcome"]["graph_model"]["graph_model_id"] == "graph:workspace"
        assert compile_result["outcome"]["graph_model"]["nodes"][0]["node_id"] == "node-1"
        assert compile_result["outcome"]["graph_model"]["nodes"][0]["position"]["x"] == 120
        assert compile_result["outcome"]["graph_model"]["nodes"][0]["ports"][0]["port_id"] == "out-main"
        assert compile_result["outcome"]["graph_model"]["edges"][0]["from_port_id"] == "out-main"
        assert compile_result["outcome"]["graph_model"]["edges"][0]["to_port_id"] == "in-main"
        assert compile_result["outcome"]["graph_model"]["edges"][0]["edge_state"] == "draft"
        assert compile_result["view"]["duration_ms"] is not None
        assert isinstance(compile_result["view"]["duration_ms"], int)
        assert compile_result["view"]["duration_ms"] >= 0

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        assert snapshot["last_compile"]["source_kind"] == "graph_workspace"
        assert snapshot["last_compile"]["request_origin"] == "graph_document"
        assert snapshot["last_compile"]["requested_graph_model_id"] == "graph:workspace"
        assert snapshot["last_compile"]["requested_graph_save_revision"] == 1
        assert snapshot["last_compile"]["duration_ms"] is not None
        assert isinstance(snapshot["last_compile"]["duration_ms"], int)
        assert snapshot["last_compile"]["duration_ms"] >= 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_compile_failure_includes_top_level_error_message_and_details(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "graph_workspace",
                "entry_document": "graph:workspace",
                "source_text": "",
            }
        ).encode("utf-8")
        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(compile_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "compile_failed"
            assert payload["message"] == payload["details"]["primary_diagnostic"]["message"]
            assert payload["details"]["primary_diagnostic"]["category"] in {
                "source.parse_error",
                "source.empty",
            }
            assert payload["view"]["primary_diagnostic"]["severity"] == "fatal"
        else:
            raise AssertionError("expected compile failure HTTPError")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_compiles_saved_graph_workspace_document_when_request_body_is_omitted(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        saved_graph_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "node_kind": "http.request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    },
                    {
                        "node_id": "node-2",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n2",
                        "expansion_role": "transform:map",
                        "node_kind": "data.map",
                        "ports": [
                            {
                                "port_id": "in",
                                "direction": "input",
                                "relation_layer": "data",
                                "semantic_slot": "in.default",
                            }
                        ],
                    },
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "relation_layer": "data",
                        "from_node_id": "node-1",
                        "to_node_id": "node-2",
                        "from_port_id": "out",
                        "to_port_id": "in",
                    }
                ],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=saved_graph_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request) as response:
            saved_result = json.loads(response.read().decode("utf-8"))

        assert saved_result["status"] == "saved"

        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "succeeded"
        assert compile_result["request"]["entry_document"] == "graph:workspace"
        assert compile_result["request"]["source_kind"] == "graph_workspace"
        assert compile_result["request"]["source"]["kind"] == "graph_workspace"
        assert compile_result["request"]["request_origin"] == "graph_document"
        assert compile_result["request"]["requested_graph_model_id"] == "graph:workspace"
        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["request"]["requested_graph_saved_at"]
        assert compile_result["view"]["graph_stats"]["node_count"] == 2
        assert compile_result["view"]["graph_stats"]["edge_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_returns_failed_graph_compile_envelope_for_disabled_resource(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
        disable_request = urllib.request.Request(
            f"{base_url}/api/workbench/resources/builtin:data.map/enabled",
            data=json.dumps({"enabled": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(disable_request):
            pass

        compile_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "transform:map",
                        "display_name": "Map Result",
                        "node_kind": "data.map",
                        "ports": [],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "failed"
        assert compile_result["view"]["primary_diagnostic"]["category"] == "graph.node.resource_disabled"
        assert compile_result["outcome"]["diagnostic_catalog"]["entries"][0]["stage_extension"][
            "rule"
        ] == "graph.node.resource_enabled"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_compiles_saved_graph_workspace_document_when_request_body_is_empty_object(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        saved_graph_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "node_kind": "http.request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=saved_graph_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request) as response:
            saved_result = json.loads(response.read().decode("utf-8"))

        assert saved_result["status"] == "saved"

        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "succeeded"
        assert compile_result["request"]["request_origin"] == "graph_document"
        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["view"]["graph_stats"]["node_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_snapshot_exposes_graph_workspace_saved_state_and_compile_relation(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            initial_snapshot = json.loads(response.read().decode("utf-8"))

        assert initial_snapshot["graph_workspace"]["graph_model_id"] == "graph:workspace"
        assert initial_snapshot["graph_workspace"]["graph_document_save_revision"] == 0
        assert initial_snapshot["graph_workspace"]["graph_document_saved_at"] is None
        assert initial_snapshot["graph_workspace"]["last_compile_matches_saved_graph"] is None

        save_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "node_kind": "http.request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    },
                    {
                        "node_id": "node-2",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n2",
                        "expansion_role": "transform:map",
                        "node_kind": "data.map",
                        "ports": [
                            {
                                "port_id": "in",
                                "direction": "input",
                                "relation_layer": "data",
                                "semantic_slot": "in.default",
                            }
                        ],
                    },
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "relation_layer": "data",
                        "from_node_id": "node-1",
                        "to_node_id": "node-2",
                        "from_port_id": "out",
                        "to_port_id": "in",
                    }
                ],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=save_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request) as response:
            save_result = json.loads(response.read().decode("utf-8"))

        first_saved_at = save_result["view"]["graph_document_saved_at"]
        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            compiled_snapshot = json.loads(response.read().decode("utf-8"))

        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["request"]["requested_graph_saved_at"] == first_saved_at
        assert compiled_snapshot["graph_workspace"]["graph_document_save_revision"] == 1
        assert compiled_snapshot["graph_workspace"]["graph_document_saved_at"] == first_saved_at
        assert compiled_snapshot["graph_workspace"]["last_compiled_graph_save_revision"] == 1
        assert compiled_snapshot["graph_workspace"]["last_compile_matches_saved_graph"] is True

        updated_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-1",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n1",
                        "expansion_role": "action:request",
                        "node_kind": "http.request",
                        "ports": [
                            {
                                "port_id": "out",
                                "direction": "output",
                                "relation_layer": "data",
                                "semantic_slot": "out.default",
                            }
                        ],
                    }
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        updated_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=updated_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(updated_request):
            pass

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            updated_snapshot = json.loads(response.read().decode("utf-8"))

        assert updated_snapshot["graph_workspace"]["graph_document_save_revision"] == 2
        assert updated_snapshot["graph_workspace"]["last_compiled_graph_save_revision"] == 1
        assert updated_snapshot["graph_workspace"]["last_compile_matches_saved_graph"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_records_empty_graph_workspace_compile_failure_in_snapshot(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_payload = json.dumps(
            {
                "graph_model_id": "graph:workspace",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        ).encode("utf-8")
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=save_payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        compile_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/compile",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compile_request) as response:
            compile_result = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        assert compile_result["status"] == "failed"
        assert compile_result["request"]["requested_graph_save_revision"] == 1
        assert compile_result["request"]["source_kind"] == "graph_workspace"
        assert compile_result["request"]["source"]["kind"] == "graph_workspace"
        assert compile_result["view"]["primary_diagnostic"]["category"] == "source.empty"
        assert compile_result["view"]["duration_ms"] is not None
        assert isinstance(compile_result["view"]["duration_ms"], int)
        assert compile_result["view"]["duration_ms"] >= 0
        assert snapshot["last_compile"]["source_kind"] == "graph_workspace"
        assert snapshot["last_compile"]["primary_diagnostic"]["category"] == "source.empty"
        assert snapshot["last_compile"]["requested_graph_save_revision"] == 1
        assert snapshot["graph_workspace"]["last_compiled_graph_save_revision"] == 1
        assert snapshot["graph_workspace"]["last_compile_matches_saved_graph"] is True
        assert snapshot["last_compile"]["duration_ms"] is not None
        assert isinstance(snapshot["last_compile"]["duration_ms"], int)
        assert snapshot["last_compile"]["duration_ms"] >= 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_runtime_start_failure_includes_top_level_error_message_and_details(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        start_runtime_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps(
                {
                    "graph_document": {
                        "graph_model_id": "graph:workspace",
                        "compilation_id": None,
                        "graph_schema_version": "graph-v1",
                        "nodes": [],
                        "edges": [],
                        "graph_effective_diagnostic_anchor_refs": [],
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(start_runtime_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert payload["message"] == payload["details"]["primary_diagnostic"]["message"]
            assert payload["details"]["primary_diagnostic"]["category"] in {
                "source.empty",
                "source.missing_nodes",
            }
            assert payload["details"]["primary_diagnostic"]["severity"] == "fatal"
        else:
            raise AssertionError("expected runtime start failure HTTPError")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_can_project_transient_graph_document_for_source_input_view(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        payload = json.dumps(
            {
                "target_source_kind": "native_flow",
                "graph_document": {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "display_name": "HTTP Request",
                            "node_kind": "http.request",
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/source-projection",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request) as response:
            projection = json.loads(response.read().decode("utf-8"))

        assert projection["status"] == "ready"
        assert projection["request_origin"] == "graph_document_payload"
        assert projection["graph_document_save_revision"] is None
        assert projection["source_kind"] == "native_flow"
        assert projection["source_text"] == (
            '{"nodes":[{"id":"n1","role":"action","capability_domain":"http",'
            '"action_kind":"request"}],"edges":[]}'
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_returns_structured_not_found_error(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        missing_path = "/api/missing-endpoint"
        try:
            urllib.request.urlopen(f"{base_url}{missing_path}")
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 404
            assert payload["error"] == "not_found"
            assert payload["path"] == missing_path
            assert payload["message"] == f"resource not found: {missing_path}"
        else:
            raise AssertionError("expected HTTPError for unknown API route")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_returns_structured_not_found_error_for_unknown_post_route(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        missing_path = "/api/missing-post-endpoint"
        request = urllib.request.Request(
            f"{base_url}{missing_path}",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 404
            assert payload["error"] == "not_found"
            assert payload["path"] == missing_path
            assert payload["message"] == f"resource not found: {missing_path}"
        else:
            raise AssertionError("expected HTTPError for unknown POST API route")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_not_found_error_sanitizes_control_characters(tmp_path: Path) -> None:
    from weconduct.api.server import _sanitize_path_for_error

    sanitized = _sanitize_path_for_error("/api/missing-\u0000-endpoint")

    assert "\u0000" not in sanitized
    assert sanitized == "/api/missing--endpoint"


def test_http_api_exposes_runtime_health(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    ui_dist_path = tmp_path / "missing-ui-dist"
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(f"{base_url}/api/health") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"] == "ok"
        assert payload["service"] == "weconduct-api"
        assert payload["host_mode"] == "python_core"
        assert payload["api_version"] == "0.7.1"
        assert payload["workspace_state_version"] == 1
        assert payload["workspace_session_id"].startswith("ws-")
        assert payload["service_started_at"]
        assert payload["capabilities"]["compiler_available"] is True
        assert payload["entrypoints"]["snapshot"] == "/api/workbench/snapshot"
        assert payload["entrypoints"]["compile_action"] == "/api/workbench/compile"
        assert payload["ui_hosting"]["ui_hosted"] is False
        assert payload["ui_hosting"]["ui_dist_available"] is False
        assert payload["ui_hosting"]["ui_entrypoint"] is None
        assert payload["ui_hosting"]["ui_dist_path"] == str(ui_dist_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_restores_workspace_state_from_file_store(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.json"
    source_file.write_text(
        '{"nodes":[{"id":"n1","role":"action","capability_domain":"http","action_kind":"request"}]}',
        encoding="utf-8",
    )
    workspace_state_path = tmp_path / "workspace-state.json"

    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": str(source_file),
                "source_text": source_file.read_text(encoding="utf-8"),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))

        assert result["status"] == "succeeded"
        assert workspace_state_path.exists()
    finally:
        server.shutdown()
        server.server_close()

    restored_server, restored_thread = _start_test_server(
        workspace_state_path=workspace_state_path
    )
    try:
        restored_base_url = f"http://127.0.0.1:{restored_server.server_address[1]}"
        with urllib.request.urlopen(f"{restored_base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        assert snapshot["workbench"]["compile_counter"] == 1
        assert snapshot["last_compile"]["status"] == "succeeded"
        assert snapshot["last_compile"]["entry_document"] == str(source_file)
        assert len(snapshot["compile_history"]) == 1
        assert snapshot["compile_history"][0] == snapshot["last_compile"]
    finally:
        restored_server.shutdown()
        restored_server.server_close()


def test_http_api_snapshot_exposes_pending_recovery_for_dirty_workspace_state(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_path = tmp_path / "pending-recovery.weconduct.json"

    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        create_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/new",
            data=json.dumps({"project_name": "Pending Recovery Project"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_request):
            pass

        save_as_request = urllib.request.Request(
            f"{base_url}/api/workbench/project/save-as",
            data=json.dumps({"project_path": str(project_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(save_as_request):
            pass

        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "pending-node",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-pending",
                            "expansion_role": "action:set_variable",
                            "node_kind": "data.set_variable",
                            "node_config": {"name": "message", "value": "pending"},
                            "ports": [],
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass
    finally:
        server.shutdown()
        server.server_close()

    restored_server, restored_thread = _start_test_server(
        workspace_state_path=workspace_state_path
    )
    try:
        restored_base_url = f"http://127.0.0.1:{restored_server.server_address[1]}"
        with urllib.request.urlopen(f"{restored_base_url}/api/workbench/snapshot") as response:
            snapshot = json.loads(response.read().decode("utf-8"))

        assert snapshot["project"]["is_dirty"] is False
        assert snapshot["project"]["pending_recovery"]["status"] == "pending"
        assert snapshot["project"]["pending_recovery"]["project_file_path"] == str(
            project_path.resolve()
        )
        assert snapshot["project"]["pending_recovery"]["node_count"] == 1
        assert snapshot["graph_workspace"]["node_count"] == 0
    finally:
        restored_server.shutdown()
        restored_server.server_close()


def test_http_api_returns_stable_error_when_workspace_state_file_is_invalid(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workspace_state_path.write_text(
        """
{
  "workspace_state_version": 999,
  "workbench": {},
  "last_compile": null,
  "compile_history": []
}
""".strip(),
        encoding="utf-8",
    )

    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        for path in ("/api/health", "/api/workbench/snapshot"):
            try:
                urllib.request.urlopen(f"{base_url}{path}")
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 500
                assert payload["error"] == "workspace_state_invalid"
                assert "workspace state version mismatch" in payload["message"]
            else:
                raise AssertionError("expected HTTPError for invalid workspace state file")
    finally:
        server.shutdown()
        server.server_close()


def test_http_compile_returns_stable_error_when_workspace_state_file_is_invalid(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workspace_state_path.write_text(
        """
{
  "workspace_state_version": 999,
  "workbench": {},
  "last_compile": null,
  "compile_history": []
}
""".strip(),
        encoding="utf-8",
    )

    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        compile_payload = json.dumps(
            {
                "source_kind": "native_flow",
                "entry_document": "examples/native-flow.json",
                "source_text": '{"nodes":[]}',
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/workbench/compile",
            data=compile_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 500
            assert payload["error"] == "workspace_state_invalid"
            assert "workspace state version mismatch" in payload["message"]
        else:
            raise AssertionError("expected HTTPError for invalid workspace state file on compile")
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_returns_stable_error_when_workspace_state_file_is_not_json(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workspace_state_path.write_text("{not-json", encoding="utf-8")

    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        for path in ("/api/health", "/api/workbench/snapshot", "/api/workbench/compile"):
            request: str | urllib.request.Request
            if path == "/api/workbench/compile":
                request = urllib.request.Request(
                    f"{base_url}{path}",
                    data=json.dumps(
                        {
                            "source_kind": "native_flow",
                            "entry_document": "examples/native-flow.json",
                            "source_text": '{"nodes":[]}',
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            else:
                request = f"{base_url}{path}"

            try:
                urllib.request.urlopen(request)
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 500
                assert payload["error"] == "workspace_state_invalid"
                assert "workspace state file must be valid JSON" == payload["message"]
            else:
                raise AssertionError("expected HTTPError for non-JSON workspace state file")
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_prepare_uses_saved_graph_when_request_body_is_empty(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "ports": [
                                {
                                    "port_id": "out",
                                    "direction": "output",
                                    "relation_layer": "data",
                                    "semantic_slot": "out.default",
                                }
                            ],
                        },
                        {
                            "node_id": "node-2",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n2",
                            "expansion_role": "transform:map",
                            "node_kind": "data.map",
                            "ports": [
                                {
                                    "port_id": "in",
                                    "direction": "input",
                                    "relation_layer": "data",
                                    "semantic_slot": "in.default",
                                }
                            ],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "data",
                            "from_node_id": "node-1",
                            "to_node_id": "node-2",
                            "from_port_id": "out",
                            "to_port_id": "in",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request) as response:
            save_payload = json.loads(response.read().decode("utf-8"))

        runtime_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/prepare",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert save_payload["view"]["graph_document_save_revision"] == 1
        assert payload["status"] == "ready"
        assert payload["request"]["request_origin"] == "saved_graph_document"
        assert payload["request"]["requested_graph_save_revision"] == 1
        assert payload["runtime_plan"]["graph_model_id"] == "graph:workspace"
        assert payload["runtime_plan"]["start_node_ids"] == ["node-1"]
        assert payload["runtime_plan"]["terminal_node_ids"] == ["node-2"]
        assert payload["runtime_session"]["execution_supported"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_debug_prepare_returns_failed_bundle_for_invalid_graph_payload(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        debug_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/prepare",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "ports": [
                                {
                                    "port_id": "out",
                                    "direction": "output",
                                    "relation_layer": "data",
                                    "semantic_slot": "out.default",
                                }
                            ],
                        }
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "data",
                            "from_node_id": "node-1",
                            "to_node_id": "missing-node",
                            "from_port_id": "out",
                            "to_port_id": "in",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(debug_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["status"] == "failed"
            assert payload["request"]["request_origin"] == "graph_document_payload"
            assert payload["debug_session"]["breakpoint_slots"] == []
            assert payload["diagnostic_links"][0]["category"] == "graph.edge.missing_target_node"
            assert payload["diagnostic_links"][0]["graph_ref"]["edge_id"] == "edge-1"
        else:
            raise AssertionError("expected HTTPError for invalid debug graph payload")
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_and_debug_actions_accept_wrapped_transient_graph_document_payload(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request_body = json.dumps(
            {
                "graph_document": _build_valid_graph_document_payload(),
            }
        ).encode("utf-8")
        endpoint_expectations = [
            ("/api/workbench/runtime/prepare", "ready"),
            ("/api/workbench/runtime/start", "started"),
            ("/api/workbench/debug/prepare", "ready"),
            ("/api/workbench/debug/start", "started"),
        ]

        for endpoint, expected_status in endpoint_expectations:
            request = urllib.request.Request(
                f"{base_url}{endpoint}",
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            assert payload["status"] == expected_status
            assert payload["request"]["request_origin"] == "graph_document_payload"
            assert payload["request"]["requested_graph_save_revision"] is None
            assert payload["request"]["requested_graph_saved_at"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_start_without_graph_document_uses_saved_workspace_graph(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    screenshot_path = tmp_path / "saved-graph-run-shot.png"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    site_server, site_thread = _start_browser_mock_site_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-nav",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-nav",
                            "expansion_role": "action:navigate",
                            "node_kind": "browser.navigate",
                            "node_config": {
                                "url": f"http://127.0.0.1:{site_server.server_address[1]}/",
                            },
                        },
                        {
                            "node_id": "node-shot",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n-shot",
                            "expansion_role": "action:screenshot",
                            "node_kind": "browser.screenshot",
                            "node_config": {
                                "path": str(screenshot_path),
                            },
                        },
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(graph_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        assert started_payload["status"] == "started"
        assert started_payload["request"]["request_origin"] == "saved_graph_document"
        session_id = started_payload["runtime_session"]["session_id"]

        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["request"]["request_origin"] == "saved_graph_document"
        assert run_payload["result"]["outputs"]["node-shot"]["path"] == str(screenshot_path.resolve())
        assert screenshot_path.exists() is True
    finally:
        server.shutdown()
        server.server_close()
        site_server.shutdown()
        site_server.server_close()


def test_http_ui_graph_authoring_main_path_can_project_compile_and_execute_via_transient_graph_document(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    echo_server, echo_thread = _start_runtime_echo_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = _build_ui_authoring_graph_document_payload_with_http_url(
            f"http://127.0.0.1:{echo_server.server_address[1]}/echo"
        )
        wrapped_payload = json.dumps({"graph_document": graph_document}).encode("utf-8")

        projection_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph/source-projection",
            data=json.dumps(
                {
                    "target_source_kind": "native_flow",
                    "graph_document": graph_document,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(projection_request) as response:
            projection_payload = json.loads(response.read().decode("utf-8"))

        runtime_prepare_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/prepare",
            data=wrapped_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_prepare_request) as response:
            runtime_prepare_payload = json.loads(response.read().decode("utf-8"))

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=wrapped_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_start_request) as response:
            runtime_start_payload = json.loads(response.read().decode("utf-8"))

        runtime_session_id = runtime_start_payload["runtime_session"]["session_id"]
        runtime_run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{runtime_session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(runtime_run_request) as response:
            runtime_run_payload = json.loads(response.read().decode("utf-8"))

        debug_prepare_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/prepare",
            data=wrapped_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(debug_prepare_request) as response:
            debug_prepare_payload = json.loads(response.read().decode("utf-8"))

        debug_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/start",
            data=wrapped_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(debug_start_request) as response:
            debug_start_payload = json.loads(response.read().decode("utf-8"))

        assert projection_payload["status"] == "ready"
        assert projection_payload["request_origin"] == "graph_document_payload"
        assert '"capability_domain":"http"' in projection_payload["source_text"]
        assert '"action_kind":"map"' in projection_payload["source_text"]

        assert runtime_prepare_payload["status"] == "ready"
        assert runtime_prepare_payload["request"]["request_origin"] == "graph_document_payload"
        assert runtime_prepare_payload["runtime_plan"]["graph_model_id"] == "graph:workspace"
        assert runtime_prepare_payload["runtime_plan"]["node_count"] == 2
        assert runtime_prepare_payload["runtime_plan"]["edge_count"] == 1

        assert runtime_start_payload["status"] == "started"
        assert runtime_start_payload["request"]["request_origin"] == "graph_document_payload"
        assert runtime_start_payload["runtime_session"]["status"] == "running"
        assert runtime_start_payload["runtime_plan"]["executable_nodes"][0]["node_kind"] == "http.request"
        assert runtime_start_payload["runtime_plan"]["executable_nodes"][1]["node_kind"] == "data.map"

        assert runtime_run_payload["status"] == "completed"
        assert runtime_run_payload["result"]["status"] == "succeeded"
        assert runtime_run_payload["result"]["completed_node_ids"] == ["node-ui-1", "node-ui-2"]
        assert runtime_run_payload["result"]["outputs"]["node-ui-1"]["status_code"] == 200
        assert runtime_run_payload["result"]["outputs"]["node-ui-1"]["body"]["body"]["ok"] is True
        assert runtime_run_payload["result"]["outputs"]["node-ui-2"]["mapped_from_node_id"] == "node-ui-1"

        assert debug_prepare_payload["status"] == "ready"
        assert debug_prepare_payload["request"]["request_origin"] == "graph_document_payload"
        assert debug_prepare_payload["object_index"]["nodes"][0]["node_kind"] == "http.request"
        assert debug_prepare_payload["object_index"]["nodes"][1]["node_kind"] == "data.map"

        assert debug_start_payload["status"] == "started"
        assert debug_start_payload["request"]["request_origin"] == "graph_document_payload"
        assert debug_start_payload["debug_session"]["status"] == "prepared"
        assert debug_start_payload["stage_timeline"][-1]["stage"] == "emit"
    finally:
        server.shutdown()
        server.server_close()
        echo_server.shutdown()
        echo_server.server_close()


def test_http_runtime_run_returns_data_and_file_outputs_for_transient_graph(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    output_path = tmp_path / "api-runtime-output.txt"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    echo_server, echo_thread = _start_runtime_echo_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-token",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-token",
                    "expansion_role": "transform:set_variable",
                    "node_kind": "data.set_variable",
                    "node_config": {"name": "token", "value": "api-token"},
                },
                {
                    "node_id": "node-http",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-http",
                    "expansion_role": "action:request",
                    "node_kind": "http.request",
                    "node_config": {
                        "method": "POST",
                        "url": f"http://127.0.0.1:{echo_server.server_address[1]}/echo",
                        "body": {"token": "${token}"},
                    },
                },
                {
                    "node_id": "node-map",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-map",
                    "expansion_role": "transform:map",
                    "node_kind": "data.map",
                    "node_config": {
                        "variable_name": "mapped_token",
                        "source": "${node.node-http.body.body.token}",
                    },
                },
                {
                    "node_id": "node-write",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-write",
                    "expansion_role": "action:write_text_file",
                    "node_kind": "file.write_text_file",
                    "node_config": {
                        "path": str(output_path),
                        "content": "token=${mapped_token}",
                    },
                },
                {
                    "node_id": "node-read",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-read",
                    "expansion_role": "action:read_text_file",
                    "node_kind": "file.read_text_file",
                    "node_config": {"path": str(output_path)},
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-map"]["value"] == "api-token"
        assert run_payload["result"]["variables"]["mapped_token"] == "api-token"
        assert run_payload["result"]["outputs"]["node-read"]["content"] == "token=api-token"
        assert output_path.read_text(encoding="utf-8") == "token=api-token"
    finally:
        server.shutdown()
        server.server_close()
        echo_server.shutdown()
        echo_server.server_close()


def test_http_runtime_run_returns_csv_outputs_for_transient_graph(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("name,score\nalice,10\nbob,20\n", encoding="utf-8")
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-cell",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-cell",
                    "expansion_role": "action:read_csv_cell",
                    "node_kind": "file.read_csv_cell",
                    "node_config": {
                        "path": str(csv_path),
                        "row_index": 0,
                        "column": "score",
                        "has_header": True,
                    },
                },
                {
                    "node_id": "node-table",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-table",
                    "expansion_role": "action:read_csv_table",
                    "node_kind": "file.read_csv_table",
                    "node_config": {
                        "path": str(csv_path),
                        "has_header": True,
                    },
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-cell"]["value"] == "10"
        assert run_payload["result"]["outputs"]["node-table"]["row_count"] == 2
        assert run_payload["result"]["outputs"]["node-table"]["rows"][1]["name"] == "bob"
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_builtin_custom_data_outputs(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-list",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-list",
                    "expansion_role": "action:create_list",
                    "node_kind": "data.create_list",
                    "node_config": {"variable_name": "numbers", "items": [1, 2]},
                },
                {
                    "node_id": "node-append",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-append",
                    "expansion_role": "action:list_append",
                    "node_kind": "data.list_append",
                    "node_config": {"variable_name": "numbers", "value": 3},
                },
                {
                    "node_id": "node-eval",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-eval",
                    "expansion_role": "action:evaluate_expression",
                    "node_kind": "data.evaluate_expression",
                    "node_config": {"expression": "len(numbers) * 10", "variable_name": "score"},
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-list"]["items"] == [1, 2]
        assert run_payload["result"]["outputs"]["node-append"]["items"] == [1, 2, 3]
        assert run_payload["result"]["outputs"]["node-eval"]["value"] == 30
        assert run_payload["result"]["variables"]["numbers"] == [1, 2, 3]
        assert run_payload["result"]["variables"]["score"] == 30
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_extended_builtin_custom_list_outputs(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-list",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-list",
                    "expansion_role": "action:create_list",
                    "node_kind": "data.create_list",
                    "node_config": {"variable_name": "numbers", "items": [1, 2]},
                },
                {
                    "node_id": "node-extend",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-extend",
                    "expansion_role": "action:list_extend",
                    "node_kind": "data.list_extend",
                    "node_config": {"variable_name": "numbers", "items": [3, 4]},
                },
                {
                    "node_id": "node-set",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-set",
                    "expansion_role": "action:list_set",
                    "node_kind": "data.list_set",
                    "node_config": {"variable_name": "numbers", "index": 1, "value": 20},
                },
                {
                    "node_id": "node-get",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-get",
                    "expansion_role": "action:list_get",
                    "node_kind": "data.list_get",
                    "node_config": {"variable_name": "numbers", "index": 2, "output_variable_name": "picked"},
                },
                {
                    "node_id": "node-length",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-length",
                    "expansion_role": "action:list_length",
                    "node_kind": "data.list_length",
                    "node_config": {"variable_name": "numbers", "output_variable_name": "count"},
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-extend"]["items"] == [1, 2, 3, 4]
        assert run_payload["result"]["outputs"]["node-set"]["items"] == [1, 20, 3, 4]
        assert run_payload["result"]["outputs"]["node-get"]["value"] == 3
        assert run_payload["result"]["outputs"]["node-length"]["value"] == 4
        assert run_payload["result"]["variables"]["picked"] == 3
        assert run_payload["result"]["variables"]["count"] == 4
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_remaining_builtin_custom_list_outputs(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-list",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-list",
                    "expansion_role": "action:create_list",
                    "node_kind": "data.create_list",
                    "node_config": {"variable_name": "letters", "items": ["c", "a", "b"]},
                },
                {
                    "node_id": "node-insert",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-insert",
                    "expansion_role": "action:list_insert",
                    "node_kind": "data.list_insert",
                    "node_config": {"variable_name": "letters", "index": 1, "value": "z"},
                },
                {
                    "node_id": "node-remove",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-remove",
                    "expansion_role": "action:list_remove",
                    "node_kind": "data.list_remove",
                    "node_config": {"variable_name": "letters", "value": "a"},
                },
                {
                    "node_id": "node-sort",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-sort",
                    "expansion_role": "action:list_sort",
                    "node_kind": "data.list_sort",
                    "node_config": {"variable_name": "letters"},
                },
                {
                    "node_id": "node-slice",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-slice",
                    "expansion_role": "action:list_slice",
                    "node_kind": "data.list_slice",
                    "node_config": {"variable_name": "letters", "start": 1, "end": 3, "output_variable_name": "window"},
                },
                {
                    "node_id": "node-reverse",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-reverse",
                    "expansion_role": "action:list_reverse",
                    "node_kind": "data.list_reverse",
                    "node_config": {"variable_name": "letters"},
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-insert"]["items"] == ["c", "z", "a", "b"]
        assert run_payload["result"]["outputs"]["node-remove"]["items"] == ["c", "z", "b"]
        assert run_payload["result"]["outputs"]["node-sort"]["items"] == ["b", "c", "z"]
        assert run_payload["result"]["outputs"]["node-slice"]["value"] == ["c", "z"]
        assert run_payload["result"]["outputs"]["node-reverse"]["items"] == ["z", "c", "b"]
        assert run_payload["result"]["variables"]["letters"] == ["z", "c", "b"]
        assert run_payload["result"]["variables"]["window"] == ["c", "z"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_excel_outputs_for_transient_graph(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workbook_path = tmp_path / "input.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "SheetA"
    worksheet["A1"] = "name"
    worksheet["B1"] = "score"
    worksheet["A2"] = "alice"
    worksheet["B2"] = 10
    worksheet["A3"] = "bob"
    worksheet["B3"] = 20
    workbook.save(workbook_path)
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-write",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-write",
                    "expansion_role": "action:write_excel_cell",
                    "node_kind": "excel.write_cell",
                    "node_config": {
                        "path": str(workbook_path),
                        "sheet_name": "SheetA",
                        "cell": "B3",
                        "value": 25,
                    },
                },
                {
                    "node_id": "node-cell",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-cell",
                    "expansion_role": "action:read_excel_cell",
                    "node_kind": "excel.read_cell",
                    "node_config": {
                        "path": str(workbook_path),
                        "sheet_name": "SheetA",
                        "cell": "B3",
                    },
                },
                {
                    "node_id": "node-table",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-table",
                    "expansion_role": "action:read_excel_table",
                    "node_kind": "excel.read_table",
                    "node_config": {
                        "path": str(workbook_path),
                        "sheet_name": "SheetA",
                        "has_header": True,
                    },
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-write"]["value"] == 25
        assert run_payload["result"]["outputs"]["node-cell"]["value"] == 25
        assert run_payload["result"]["outputs"]["node-table"]["rows"] == [
            {"name": "alice", "score": 10},
            {"name": "bob", "score": 25},
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_python_outputs_for_transient_graph(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {},
                "compile_settings": {},
                "security_settings": {
                    "allow_external_programs": True,
                    "allow_python_execution": True,
                },
                "python_runtime_settings": {},
                "graph_settings": {},
                "other_settings": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        preferences_path=preferences_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-start",
                    "lowered_kind": "control",
                    "source_anchor_ref": "n-start",
                    "expansion_role": "flow.start",
                    "node_kind": "flow.start",
                    "node_config": {},
                    "ports": [
                        {
                            "port_id": "control-out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "control.next",
                        }
                    ],
                },
                {
                    "node_id": "node-a",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-a",
                    "expansion_role": "transform:set_variable",
                    "node_kind": "data.set_variable",
                    "node_config": {"name": "A", "value": 7},
                    "ports": [
                        {
                            "port_id": "control-in",
                            "direction": "input",
                            "relation_layer": "control",
                            "semantic_slot": "control.in",
                        },
                        {
                            "port_id": "control-out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "control.next",
                        },
                    ],
                },
                {
                    "node_id": "node-b",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-b",
                    "expansion_role": "transform:set_variable",
                    "node_kind": "data.set_variable",
                    "node_config": {"name": "B", "value": 5},
                    "ports": [
                        {
                            "port_id": "control-in",
                            "direction": "input",
                            "relation_layer": "control",
                            "semantic_slot": "control.in",
                        },
                        {
                            "port_id": "control-out",
                            "direction": "output",
                            "relation_layer": "control",
                            "semantic_slot": "control.next",
                        },
                    ],
                },
                {
                    "node_id": "node-python",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-python",
                    "expansion_role": "action:run_python",
                    "node_kind": "python.run",
                    "node_config": {
                        "code": (
                            "result = variables.get('A', 0) + variables.get('B', 0)\n"
                            "result_variable = 'sum_value'\n"
                        ),
                        "variable_name": "default_sum",
                    },
                    "ports": [
                        {
                            "port_id": "control-in",
                            "direction": "input",
                            "relation_layer": "control",
                            "semantic_slot": "control.in",
                        }
                    ],
                },
            ],
            "edges": [
                {
                    "edge_id": "edge-start-a",
                    "relation_layer": "control",
                    "from_node_id": "node-start",
                    "to_node_id": "node-a",
                    "from_port_id": "control-out",
                    "to_port_id": "control-in",
                    "edge_state": "draft",
                },
                {
                    "edge_id": "edge-a-b",
                    "relation_layer": "control",
                    "from_node_id": "node-a",
                    "to_node_id": "node-b",
                    "from_port_id": "control-out",
                    "to_port_id": "control-in",
                    "edge_state": "draft",
                },
                {
                    "edge_id": "edge-b-python",
                    "relation_layer": "control",
                    "from_node_id": "node-b",
                    "to_node_id": "node-python",
                    "from_port_id": "control-out",
                    "to_port_id": "control-in",
                    "edge_state": "draft",
                },
            ],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        deadline = time.monotonic() + 5
        session_payload = None
        while time.monotonic() < deadline:
            with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
                session_payload = json.loads(response.read().decode("utf-8"))
            if session_payload["runtime_session"]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert run_payload["status"] == "accepted"
        assert session_payload is not None
        assert session_payload["runtime_session"]["status"] == "completed"
        assert session_payload["result"]["outputs"]["node-python"]["result"] == 12
        assert session_payload["result"]["outputs"]["node-python"]["result_variable"] == "sum_value"
        assert session_payload["result"]["variables"]["sum_value"] == 12
        assert "default_sum" not in session_payload["result"]["variables"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_loaded_package_blocks_runtime_start_when_python_runtime_manifest_is_invalid(
    tmp_path: Path,
) -> None:
    from weconduct.application import CompilationWorkbenchService

    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        project_path = tmp_path / "python-runtime-start-api.weconduct.json"
        output_path = tmp_path / "dist" / "python-runtime-start-api.wcrun"

        builder = CompilationWorkbenchService()
        builder.create_project(project_name="Python Runtime Start API")
        builder.save_graph_document(
            {
                "graph_model_id": "graph:python-runtime-start-api",
                "compilation_id": None,
                "graph_schema_version": "graph-v1",
                "nodes": [
                    {
                        "node_id": "node-start",
                        "lowered_kind": "control",
                        "source_anchor_ref": "n-node-start",
                        "expansion_role": "flow.start",
                        "display_name": "流程入口",
                        "node_kind": "flow.start",
                        "node_config": {
                            "initial_variables": {"base_url": "http://python-runtime-start-api.test"},
                            "browser_config": {"headless": True, "slow_mo_ms": 0},
                        },
                        "ports": [],
                    },
                    {
                        "node_id": "node-python",
                        "lowered_kind": "execution",
                        "source_anchor_ref": "n-node-python",
                        "expansion_role": "action:python_run",
                        "display_name": "Python",
                        "node_kind": "python.run",
                        "node_config": {"code": "result = 1"},
                        "ports": [],
                    },
                ],
                "edges": [],
                "graph_effective_diagnostic_anchor_refs": [],
            }
        )
        builder.update_project_settings(
            project_settings={
                **builder.get_project_settings_document()["project_settings"],
                "python_runtime_profile": {
                    **builder.get_project_settings_document()["project_settings"]["python_runtime_profile"],
                    "runtime_enabled": True,
                    "cache_location_mode": "project_cache",
                    "package_embed_mode": "wheelhouse_rebuild",
                },
            }
        )
        builder.save_project_as(project_path=str(project_path))
        builder.build_project_package(
            mode="wcrun",
            source_of_truth="saved_project_only",
            output_path=str(output_path),
        )

        tampered_path = tmp_path / "dist" / "python-runtime-start-api-tampered.wcrun"
        with zipfile.ZipFile(output_path, "r") as source_archive, zipfile.ZipFile(
            tampered_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as target_archive:
            for info in source_archive.infolist():
                payload = source_archive.read(info.filename)
                if info.filename == "python-runtime/manifest.json":
                    payload = b"{}"
                if info.filename == "meta/checksums.json":
                    checksums_payload = json.loads(payload.decode("utf-8"))
                    for entry in checksums_payload["entries"]:
                        if entry["path"] == "python-runtime/manifest.json":
                            entry["sha256"] = hashlib.sha256(b"{}").hexdigest()
                            entry["size"] = len(b"{}")
                    payload = json.dumps(
                        checksums_payload,
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8")
                target_archive.writestr(info, payload)

        with urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/workbench/project/package/load",
                data=json.dumps({"package_path": str(tampered_path)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ):
            pass

        runtime_start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(runtime_start_request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "runtime_start_failed"
            assert any(
                entry["category"] == "package.python_runtime.manifest_hash_mismatch"
                for entry in payload["diagnostics"]["entries"]
            )
        else:
            raise AssertionError("expected runtime start failure for invalid python runtime manifest")
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_extended_browser_outputs_for_transient_graph(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    screenshot_path = tmp_path / "api-browser-extended-shot.png"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    site_server, site_thread = _start_browser_mock_site_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        site_url = f"http://127.0.0.1:{site_server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {"node_id": "node-nav", "lowered_kind": "execution", "source_anchor_ref": "n-nav", "expansion_role": "action:navigate", "node_kind": "browser.navigate", "node_config": {"url": f"{site_url}/"}},
                {"node_id": "node-hover", "lowered_kind": "execution", "source_anchor_ref": "n-hover", "expansion_role": "action:hover", "node_kind": "browser.hover", "node_config": {"selector": "#hover-target"}},
                {"node_id": "node-wait-hover", "lowered_kind": "execution", "source_anchor_ref": "n-wait-hover", "expansion_role": "action:wait_for_element", "node_kind": "browser.wait_for_element", "node_config": {"selector": "#hover-result", "timeout": 3000}},
                {"node_id": "node-select", "lowered_kind": "execution", "source_anchor_ref": "n-select", "expansion_role": "action:select_option", "node_kind": "browser.select_option", "node_config": {"selector": "#city", "value": "beijing"}},
                {"node_id": "node-click-go", "lowered_kind": "execution", "source_anchor_ref": "n-click-go", "expansion_role": "action:click", "node_kind": "browser.click", "node_config": {"selector": "#go-dashboard"}},
                {"node_id": "node-wait-nav", "lowered_kind": "execution", "source_anchor_ref": "n-wait-nav", "expansion_role": "action:wait_for_navigation", "node_kind": "browser.wait_for_navigation", "node_config": {"url_pattern": "/dashboard", "timeout": 3000}},
                {"node_id": "node-back", "lowered_kind": "execution", "source_anchor_ref": "n-back", "expansion_role": "action:navigate", "node_kind": "browser.navigate", "node_config": {"url": f"{site_url}/"}},
                {"node_id": "node-frame", "lowered_kind": "execution", "source_anchor_ref": "n-frame", "expansion_role": "action:switch_to_frame", "node_kind": "browser.switch_to_frame", "node_config": {"selector": "#content-frame"}},
                {"node_id": "node-frame-wait", "lowered_kind": "execution", "source_anchor_ref": "n-frame-wait", "expansion_role": "action:wait_for_element", "node_kind": "browser.wait_for_element", "node_config": {"selector": "#frame-status", "timeout": 3000}},
                {"node_id": "node-parent", "lowered_kind": "execution", "source_anchor_ref": "n-parent", "expansion_role": "action:switch_to_parent_frame", "node_kind": "browser.switch_to_parent_frame", "node_config": {}},
                {"node_id": "node-default", "lowered_kind": "execution", "source_anchor_ref": "n-default", "expansion_role": "action:switch_to_default_content", "node_kind": "browser.switch_to_default_content", "node_config": {}},
                {"node_id": "node-open-frame-page", "lowered_kind": "execution", "source_anchor_ref": "n-open-frame-page", "expansion_role": "action:open_frame_page", "node_kind": "browser.open_frame_page", "node_config": {"selector": "#content-frame"}},
                {"node_id": "node-timeout", "lowered_kind": "execution", "source_anchor_ref": "n-timeout", "expansion_role": "action:wait_for_timeout", "node_kind": "browser.wait_for_timeout", "node_config": {"timeout": 10}},
                {"node_id": "node-shot", "lowered_kind": "execution", "source_anchor_ref": "n-shot", "expansion_role": "action:screenshot", "node_kind": "browser.screenshot", "node_config": {"path": str(screenshot_path)}},
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-hover"]["selector"] == "#hover-target"
        assert run_payload["result"]["outputs"]["node-select"]["value"] == "beijing"
        assert run_payload["result"]["outputs"]["node-wait-nav"]["matched_url"].endswith("/dashboard")
        assert run_payload["result"]["outputs"]["node-frame"]["frame_url"].endswith("/frame")
        assert run_payload["result"]["outputs"]["node-open-frame-page"]["page_url"].endswith("/frame")
        assert run_payload["result"]["outputs"]["node-timeout"]["timeout_ms"] == 10
        assert run_payload["result"]["outputs"]["node-shot"]["path"] == str(screenshot_path.resolve())
    finally:
        server.shutdown()
        server.server_close()
        site_server.shutdown()
        site_server.server_close()


def test_http_runtime_run_returns_extended_excel_outputs_for_transient_graph(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workbook_path = tmp_path / "output.xlsx"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {"node_id": "node-write-file", "lowered_kind": "execution", "source_anchor_ref": "n-write-file", "expansion_role": "action:write_excel_file", "node_kind": "excel.write_file", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "headers": ["name", "score"], "rows": [["alice", 10], ["bob", 20]], "mode": "create"}},
                {"node_id": "node-write-row", "lowered_kind": "execution", "source_anchor_ref": "n-write-row", "expansion_role": "action:write_excel_row", "node_kind": "excel.write_row", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "row_index": 4, "data": ["carol", 30]}},
                {"node_id": "node-write-table", "lowered_kind": "execution", "source_anchor_ref": "n-write-table", "expansion_role": "action:write_excel_table", "node_kind": "excel.write_table", "node_config": {"path": str(workbook_path), "sheet_name": "Summary", "has_header": True, "data": [{"kind": "passed", "count": 2}, {"kind": "failed", "count": 1}]}},
                {"node_id": "node-update-cells", "lowered_kind": "execution", "source_anchor_ref": "n-update-cells", "expansion_role": "action:update_excel_cells", "node_kind": "excel.update_cells", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "updates": [{"row_index": 2, "column_name": "score", "value": 15}, {"row_index": 3, "column_index": 2, "value": 25}]}},
                {"node_id": "node-update-batch", "lowered_kind": "execution", "source_anchor_ref": "n-update-batch", "expansion_role": "action:update_excel_batch", "node_kind": "excel.update_batch", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "condition": "row.get('score', 0) >= 25", "updates": {"score": 99}}},
                {"node_id": "node-read-users", "lowered_kind": "execution", "source_anchor_ref": "n-read-users", "expansion_role": "action:read_excel_table", "node_kind": "excel.read_table", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "has_header": True}},
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] in {"accepted", "completed"}
        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))

        assert session_payload["runtime_session"]["status"] == "completed"
        assert session_payload["result"]["outputs"]["node-write-file"]["row_count"] == 2
        assert session_payload["result"]["outputs"]["node-update-cells"]["updated_count"] == 2
        assert session_payload["result"]["outputs"]["node-update-batch"]["updated_count"] == 2
        assert session_payload["result"]["outputs"]["node-read-users"]["rows"] == [
            {"name": "alice", "score": 15},
            {"name": "bob", "score": 99},
            {"name": "carol", "score": 99},
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_returns_browser_atomic_outputs(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    screenshot_path = tmp_path / "api-browser-shot.png"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    site_server, site_thread = _start_browser_mock_site_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-nav",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-nav",
                    "expansion_role": "action:navigate",
                    "node_kind": "browser.navigate",
                    "node_config": {
                        "url": f"http://127.0.0.1:{site_server.server_address[1]}/",
                    },
                },
                {
                    "node_id": "node-fill",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-fill",
                    "expansion_role": "action:fill",
                    "node_kind": "browser.fill",
                    "node_config": {
                        "selector": "#name",
                        "value": "Alice",
                    },
                },
                {
                    "node_id": "node-click",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-click",
                    "expansion_role": "action:click",
                    "node_kind": "browser.click",
                    "node_config": {
                        "selector": "#submit",
                    },
                },
                {
                    "node_id": "node-shot",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-shot",
                    "expansion_role": "action:screenshot",
                    "node_kind": "browser.screenshot",
                    "node_config": {
                        "path": str(screenshot_path),
                    },
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-nav"]["page_url"].startswith("http://127.0.0.1:")
        assert run_payload["result"]["outputs"]["node-fill"]["value"] == "Alice"
        assert run_payload["result"]["outputs"]["node-click"]["page_url"].startswith("http://127.0.0.1:")
        assert run_payload["result"]["outputs"]["node-shot"]["path"] == str(screenshot_path.resolve())
        assert run_payload["result"]["outputs"]["node-shot"]["bytes_written"] > 0
        assert screenshot_path.exists() is True
        assert BrowserMockSiteHandler.clicked is True
        assert BrowserMockSiteHandler.last_form_value == "Alice"
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_rejects_excel_update_batch_eval_escape_expression(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    workbook_path = tmp_path / "output.xlsx"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {"node_id": "node-write-file", "lowered_kind": "execution", "source_anchor_ref": "n-write-file", "expansion_role": "action:write_excel_file", "node_kind": "excel.write_file", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "headers": ["name", "score"], "rows": [["alice", 10]], "mode": "create"}},
                {"node_id": "node-update-batch", "lowered_kind": "execution", "source_anchor_ref": "n-update-batch", "expansion_role": "action:update_excel_batch", "node_kind": "excel.update_batch", "node_config": {"path": str(workbook_path), "sheet_name": "Users", "condition": "__import__('os').system('echo hacked')", "updates": {"score": 99}}},
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] in {"accepted", "completed", "failed"}
        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))
        assert session_payload["runtime_session"]["status"] == "failed"
        failed_node = next(
            item for item in session_payload["node_states"] if item["node_id"] == "node-update-batch"
        )
        failed_error = failed_node.get("error") or {}
        failed_output = failed_node.get("output") or {}
        assert (
            failed_error.get("error_code") in {"excel.condition_invalid", "runtime.executor_exception"}
            or failed_output.get("error_code") in {"excel.condition_invalid", "runtime.executor_exception"}
        )
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_rejects_absolute_file_path_outside_project_root(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    outside_path = tmp_path.parent / "forbidden-runtime-write.txt"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [
                {
                    "node_id": "node-write-text",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-write-text",
                    "expansion_role": "action:write_text_file",
                    "node_kind": "file.write_text_file",
                    "node_config": {
                        "path": str(outside_path),
                        "content": "blocked",
                    },
                }
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] in {"accepted", "completed", "failed"}
        with urllib.request.urlopen(f"{base_url}/api/workbench/runtime/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))
        assert session_payload["runtime_session"]["status"] == "failed"
        failed_node = next(
            item for item in session_payload["node_states"] if item["node_id"] == "node-write-text"
        )
        assert failed_node["error"]["error_code"] in {
            "runtime.executor_exception",
            "file.write_failed",
        }
        assert "allowed" in failed_node["error"]["message"].lower()
        assert outside_path.exists() is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_runtime_run_allows_legacy_webcontrol_click_with_ambiguous_selector(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    site_server, site_thread = _start_browser_mock_site_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        site_url = f"http://127.0.0.1:{site_server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "root_metadata": {
                "source_kind": "webcontrol_main_flow",
                "legacy_webcontrol_source": {
                    "source_path": str((tmp_path / "full_function_test.yaml").resolve()),
                    "source_kind": "webcontrol_main_flow",
                },
            },
            "nodes": [
                {
                    "node_id": "node-nav",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-nav",
                    "expansion_role": "action:navigate",
                    "node_kind": "browser.navigate",
                    "node_config": {
                        "url": f"{site_url}/ambiguous",
                    },
                },
                {
                    "node_id": "node-click",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-click",
                    "expansion_role": "action:click",
                    "node_kind": "browser.click",
                    "node_config": {
                        "selector": ".btn-success",
                    },
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_request) as response:
            run_payload = json.loads(response.read().decode("utf-8"))

        assert run_payload["status"] == "completed"
        assert run_payload["result"]["outputs"]["node-click"]["selector"] == ".btn-success"
        assert run_payload["result"]["outputs"]["node-click"]["page_url"].endswith("/ambiguous")
        assert BrowserMockSiteHandler.ambiguous_last_action == "main"
    finally:
        server.shutdown()
        server.server_close()
        site_server.shutdown()
        site_server.server_close()


def test_http_runtime_run_keeps_strict_click_for_non_legacy_graph(
    tmp_path: Path,
) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)
    site_server, site_thread = _start_browser_mock_site_server()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        site_url = f"http://127.0.0.1:{site_server.server_address[1]}"
        graph_document = {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "root_metadata": {
                "source_kind": "graph_workspace",
            },
            "nodes": [
                {
                    "node_id": "node-nav",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-nav",
                    "expansion_role": "action:navigate",
                    "node_kind": "browser.navigate",
                    "node_config": {
                        "url": f"{site_url}/ambiguous",
                    },
                },
                {
                    "node_id": "node-click",
                    "lowered_kind": "execution",
                    "source_anchor_ref": "n-click",
                    "expansion_role": "action:click",
                    "node_kind": "browser.click",
                    "node_config": {
                        "selector": ".btn-success",
                    },
                },
            ],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/start",
            data=json.dumps({"graph_document": graph_document}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["runtime_session"]["session_id"]
        run_request = urllib.request.Request(
            f"{base_url}/api/workbench/runtime/{session_id}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(run_request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload["status"] == "failed"
            assert payload["runtime_session"]["status"] == "failed"
            assert payload["result"]["failure_reason"] == "runtime.executor_exception"
            assert (
                payload["node_states"][1]["error"]["error_code"]
                == "runtime.executor_exception"
            )
            assert "strict mode violation" in payload["node_states"][1]["error"]["message"]
        else:
            raise AssertionError("expected runtime strict click failure for non-legacy graph")
    finally:
        server.shutdown()
        server.server_close()
        site_server.shutdown()
        site_server.server_close()


def test_http_api_can_start_and_query_debug_session(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{base_url}/api/workbench/graph",
            data=json.dumps(
                {
                    "graph_model_id": "graph:workspace",
                    "compilation_id": None,
                    "graph_schema_version": "graph-v1",
                    "nodes": [
                        {
                            "node_id": "node-1",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n1",
                            "expansion_role": "action:request",
                            "node_kind": "http.request",
                            "ports": [
                                {
                                    "port_id": "out",
                                    "direction": "output",
                                    "relation_layer": "data",
                                    "semantic_slot": "out.default",
                                }
                            ],
                        },
                        {
                            "node_id": "node-2",
                            "lowered_kind": "execution",
                            "source_anchor_ref": "n2",
                            "expansion_role": "transform:map",
                            "node_kind": "data.map",
                            "ports": [
                                {
                                    "port_id": "in",
                                    "direction": "input",
                                    "relation_layer": "data",
                                    "semantic_slot": "in.default",
                                }
                            ],
                        },
                    ],
                    "edges": [
                        {
                            "edge_id": "edge-1",
                            "relation_layer": "data",
                            "from_node_id": "node-1",
                            "to_node_id": "node-2",
                            "from_port_id": "out",
                            "to_port_id": "in",
                        }
                    ],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(save_request):
            pass

        start_request = urllib.request.Request(
            f"{base_url}/api/workbench/debug/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(start_request) as response:
            started_payload = json.loads(response.read().decode("utf-8"))

        session_id = started_payload["debug_session"]["session_id"]
        with urllib.request.urlopen(f"{base_url}/api/workbench/debug/{session_id}") as response:
            session_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/debug/sessions") as response:
            sessions_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/api/workbench/project") as response:
            project_payload = json.loads(response.read().decode("utf-8"))

        assert started_payload["status"] == "started"
        assert started_payload["debug_session"]["status"] == "prepared"
        assert started_payload["debug_session"]["breakpoint_slots"] == []
        assert session_payload["debug_session"]["session_id"] == session_id
        assert session_payload["stage_timeline"][-1]["stage"] == "emit"
        assert session_payload["runtime_preview_summary"]["scheduler_mode"] == "legacy_sequence"
        assert session_payload["runtime_preview_summary"]["queued_node_count"] == 0
        assert session_payload["runtime_preview_summary"]["current_node_id"] is None
        assert sessions_payload["sessions"][0]["scheduler_mode"] == "legacy_sequence"
        assert sessions_payload["sessions"][0]["session_id"] == session_id
        assert project_payload["project"]["last_debug_status"] == "prepared"
        assert project_payload["project"]["last_debug_session_id"] == session_id
        assert project_payload["project"]["execution_overview"]["debug_status_counts"]["prepared"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_info_exposes_release_manifest_and_runtime_binding(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "state" / "workspace-state.json"
    ui_dist_path = tmp_path / "ui-dist"
    ui_dist_path.mkdir(parents=True, exist_ok=True)
    (ui_dist_path / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    server, thread = _start_test_server(
        workspace_state_path=workspace_state_path,
        ui_dist_path=ui_dist_path,
    )

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/host/info") as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["host_mode"] == "python_core"
        assert payload["api_version"] == "0.7.1"
        assert payload["server_bind"]["host"] == "127.0.0.1"
        assert payload["server_bind"]["port"] == server.server_address[1]
        assert payload["server_bind"]["base_url"] == base_url
        assert payload["ui_hosting"]["ui_entrypoint"] == "/"
        assert payload["release_manifest"]["manifest_version"] == "phase3-host-baseline"
        assert "--workspace-state-path" in payload["release_manifest"]["startup_command"]
        assert "--ui-dist-path" in payload["release_manifest"]["startup_command"]
        assert str(workspace_state_path.resolve()) not in payload["release_manifest"]["startup_command"]
        assert str(ui_dist_path.resolve()) not in payload["release_manifest"]["startup_command"]
        assert payload["release_manifest"]["workspace_state_path"] != str(workspace_state_path.resolve())
        assert payload["release_manifest"]["ui_dist_path"] != str(ui_dist_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_file_dialog_uses_server_provider(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    def fake_file_dialog_provider(payload: dict) -> dict:
        assert payload["mode"] == "open_file"
        assert payload["title"] == "选择节点图"
        return {
            "status": "selected",
            "mode": payload["mode"],
            "paths": [str(tmp_path / "graph.json")],
        }

    server.file_dialog_provider = fake_file_dialog_provider

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/file-dialog",
            data=json.dumps(
                {
                    "mode": "open_file",
                    "title": "选择节点图",
                    "file_types": ["JSON Files (*.json)"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload == {
            "status": "selected",
            "mode": "open_file",
            "paths": [str(tmp_path / "graph.json")],
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_file_dialog_reports_unavailable_without_provider(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/file-dialog",
            data=json.dumps({"mode": "open_folder"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 503
            assert payload["error"] == "host.file_dialog_unavailable"
            assert payload["message"] == "host file dialog is unavailable"
        else:
            raise AssertionError("expected host file dialog to be unavailable without provider")
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_open_path_uses_server_provider(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_dir = tmp_path / "demo-project"
    project_dir.mkdir()
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    def fake_open_path_provider(payload: dict) -> dict:
        assert payload["path"] == str(project_dir)
        return {
            "status": "opened",
            "path": str(project_dir.resolve()),
            "target_kind": "directory",
        }

    server.open_path_provider = fake_open_path_provider

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/open-path",
            data=json.dumps({"path": str(project_dir)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload == {
            "status": "opened",
            "path": str(project_dir.resolve()),
            "target_kind": "directory",
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_open_path_reports_unavailable_without_provider(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    project_dir = tmp_path / "demo-project"
    project_dir.mkdir()
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/open-path",
            data=json.dumps({"path": str(project_dir)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 503
            assert payload["error"] == "host.open_path_unavailable"
            assert payload["message"] == "host open path is unavailable"
        else:
            raise AssertionError("expected host open path to be unavailable without provider")
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_read_file_returns_text_file_contents(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_text = '{"graph_model_id":"graph:workspace","nodes":[]}'
    graph_path.write_text(graph_text, encoding="utf-8")
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/read-file",
            data=json.dumps({"path": str(graph_path), "encoding": "utf-8"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload == {
            "status": "read",
            "path": str(graph_path.resolve()),
            "encoding": "utf-8",
            "content": graph_text,
            "bytes_read": len(graph_text.encode("utf-8")),
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_read_file_rejects_directory_path(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/read-file",
            data=json.dumps({"path": str(tmp_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "host.read_file_not_file"
            assert payload["message"] == "path must point to a regular file"
        else:
            raise AssertionError("expected directory path to be rejected")
    finally:
        server.shutdown()
        server.server_close()


def test_http_host_read_file_rejects_file_outside_allowed_roots(tmp_path: Path) -> None:
    workspace_state_path = tmp_path / "workspace-state.json"
    outside_root = tmp_path.parent / "outside-security-check.txt"
    outside_root.write_text("forbidden", encoding="utf-8")
    server, thread = _start_test_server(workspace_state_path=workspace_state_path)

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/host/read-file",
            data=json.dumps({"path": str(outside_root)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 403
            assert payload["error"] == "forbidden"
            assert "allowed directory" in payload["message"]
        else:
            raise AssertionError("expected file outside allowed roots to be rejected")
    finally:
        server.shutdown()
        server.server_close()
