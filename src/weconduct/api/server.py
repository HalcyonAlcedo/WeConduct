import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from urllib.parse import parse_qs, unquote, urlparse

from weconduct.application import (
    CompilationWorkbenchService,
    FileWorkspaceStateStore,
    GraphDocumentRevisionConflictError,
    PreferencesService,
    FilePreferencesStore,
)

DEFAULT_WORKSPACE_STATE_PATH = (
    Path(__file__).resolve().parents[3] / ".weconduct" / "workspace-state.json"
)
DEFAULT_PREFERENCES_PATH = Path(__file__).resolve().parents[3] / ".weconduct" / "preferences.json"
DEFAULT_UI_DIST_PATH = Path(__file__).resolve().parents[3] / "ui" / "dist"


def _sanitize_path_for_error(path: str) -> str:
    sanitized = "".join(char for char in path if char.isprintable() or char in " \t")
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + "...(truncated)"
    return sanitized


def _is_path_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


class WeConductApiServer(ThreadingHTTPServer):
    allow_reuse_address = True


class WeConductApiHandler(BaseHTTPRequestHandler):
    def _verify_api_token(self) -> bool:
        expected_token = getattr(self.server, "api_token", None)
        if expected_token is None:
            return True
        provided_token = self.headers.get("X-WeConduct-Token", "")
        return secrets.compare_digest(provided_token, expected_token)

    def _require_api_token(self) -> bool:
        if self._verify_api_token():
            return True
        self._write_json(
            HTTPStatus.UNAUTHORIZED,
            {
                "error": "unauthorized",
                "message": "invalid or missing API token",
            },
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        try:
            service = self._get_service()
        except ValueError as exc:
            self._write_workspace_state_error(exc)
            return
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        request_path = parsed_url.path
        if self.path == "/api/health":
            payload = dict(service.get_runtime_health())
            payload["ui_hosting"] = self._build_ui_hosting_metadata()
            self._write_json(HTTPStatus.OK, payload)
            return

        if self.path == "/api/workbench/snapshot":
            payload = dict(service.get_workbench_snapshot())
            payload["ui_hosting"] = self._build_ui_hosting_metadata()
            self._write_json(HTTPStatus.OK, payload)
            return

        if self.path == "/api/workbench/graph":
            result = service.get_graph_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if request_path == "/api/workbench/graph/node-draft":
            try:
                resource_key = self._get_optional_query_param(query_params, "resource_key")
                if not isinstance(resource_key, str) or not resource_key.strip():
                    raise ValueError("query parameter must be a non-empty string: resource_key")
                raw_node_id = self._get_optional_query_param(query_params, "node_id")
                x_value = self._get_optional_float_query_param(query_params, "x")
                y_value = self._get_optional_float_query_param(query_params, "y")
                position = None
                if x_value is not None and y_value is not None:
                    position = {"x": x_value, "y": y_value}
                result = service.build_graph_node_draft(
                    resource_key=resource_key,
                    node_id=raw_node_id,
                    position=position,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/graph/source-projection":
            try:
                result = service.get_graph_source_projection_document(
                    target_source_kind="native_flow",
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project":
            result = service.get_project_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "project": result["project"],
                    "project_settings": result.get("project_settings"),
                    "graph_workspace": result["graph_workspace"],
                },
            )
            return

        if self.path == "/api/workbench/project/settings":
            result = service.get_project_settings_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "project_settings": result["project_settings"],
                    "state": result["state"],
                },
            )
            return

        if self.path == "/api/workbench/project/runtime-defaults":
            result = service.get_project_settings_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "runtime_defaults": result["project_settings"]["runtime_defaults"],
                    "state": result["state"],
                },
            )
            return

        if self.path == "/api/workbench/project/package/preflight":
            result = service.run_project_package_preflight()
            status_code = HTTPStatus.OK if result["status"] == "ok" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if request_path == "/api/workbench/project/package/inspect":
            try:
                package_path = self._get_optional_query_param(query_params, "package_path")
                if not isinstance(package_path, str) or not package_path.strip():
                    raise ValueError("query parameter must be a non-empty string: package_path")
                result = service.inspect_project_package(package_path=package_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/preferences":
            result = self._get_preferences_service().get_preferences_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "preferences": result,
                },
            )
            return

        if self.path == "/api/workbench/recent-projects":
            result = service.get_recent_projects_document()
            self._write_json(
                HTTPStatus.OK,
                {
                    "recent_projects": result["recent_projects"],
                },
            )
            return

        if request_path == "/api/workbench/resources":
            result = service.get_resource_registry_document(
                query=self._get_optional_query_param(query_params, "query"),
                tags=self._get_multi_query_param(query_params, "tags"),
                enabled=self._get_optional_bool_query_param(query_params, "enabled"),
                origin=self._get_optional_query_param(query_params, "origin"),
                resource_type=self._get_optional_query_param(query_params, "resource_type"),
            )
            self._write_json(
                HTTPStatus.OK,
                {
                    "registry_revision": result["registry_revision"],
                    "resource_types": result["resource_types"],
                    "summary": result["summary"],
                    "facets": result["facets"],
                    "resources": result["resources"],
                },
            )
            return

        if self.path == "/api/workbench/project/documents":
            result = service.get_project_documents_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/project/resource-audit":
            result = service.get_project_resource_audit_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path == "/api/workbench/component-library":
            result = service.get_component_library_document(
                query=self._get_optional_query_param(query_params, "query"),
                tags=self._get_multi_query_param(query_params, "tags"),
                enabled=self._get_optional_bool_query_param(query_params, "enabled"),
                origin=self._get_optional_query_param(query_params, "origin"),
                resource_type=self._get_optional_query_param(query_params, "resource_type"),
            )
            self._write_json(
                HTTPStatus.OK,
                {
                    "summary": result["summary"],
                    "facets": result["facets"],
                    "items": result["items"],
                },
            )
            return

        if self.path == "/api/workbench/editor/history":
            result = service.get_editor_history_document()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if request_path == "/api/workbench/execution-history":
            result = service.get_execution_history_document(
                runtime_status=self._get_optional_query_param(query_params, "runtime_status"),
                debug_status=self._get_optional_query_param(query_params, "debug_status"),
            )
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/runtime/sessions":
            result = service.list_runtime_sessions()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path == "/api/workbench/debug/sessions":
            result = service.list_debug_sessions()
            self._write_json(
                HTTPStatus.OK,
                result,
            )
            return

        if self.path.startswith("/api/workbench/runtime/") and self.command == "GET":
            session_id = self.path.removeprefix("/api/workbench/runtime/")
            if session_id.endswith("/stream"):
                runtime_session_id = session_id.removesuffix("/stream")
                if runtime_session_id and "/" not in runtime_session_id:
                    try:
                        self._write_runtime_stream(service, runtime_session_id)
                    except ValueError as exc:
                        self._write_invalid_request_error(exc)
                    return
            if session_id and "/" not in session_id:
                try:
                    result = service.get_runtime_session(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if self.path.startswith("/api/workbench/debug/") and self.command == "GET":
            session_id = self.path.removeprefix("/api/workbench/debug/")
            if session_id and "/" not in session_id:
                try:
                    result = service.get_debug_session(session_id=session_id)
                except ValueError as exc:
                    self._write_invalid_request_error(exc)
                    return
                self._write_json(HTTPStatus.OK, result)
                return

        if self.path == "/api/host/info":
            service_health = service.get_runtime_health()
            payload = {
                "host_mode": service_health["host_mode"],
                "api_version": service_health["api_version"],
                "server_bind": self._build_server_bind_metadata(),
                "ui_hosting": self._build_ui_hosting_metadata(),
                "release_manifest": self._build_release_manifest(),
            }
            self._write_json(HTTPStatus.OK, payload)
            return

        if self._try_serve_ui_asset():
            return

        self._write_not_found_error()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/host/file-dialog":
            if not self._require_api_token():
                return
            self._handle_host_file_dialog()
            return

        if self.path == "/api/host/open-path":
            if not self._require_api_token():
                return
            self._handle_host_open_path()
            return

        if self.path == "/api/host/read-file":
            if not self._require_api_token():
                return
            self._handle_host_read_file()
            return

        try:
            service = self._get_service()
        except ValueError as exc:
            self._write_workspace_state_error(exc)
            return
        if self.path == "/api/workbench/compile":
            try:
                payload = self._read_json_request_body()
                self._validate_compile_payload(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            result = service.compile_source(
                source_kind=payload["source_kind"],
                entry_document=payload["entry_document"],
                source_text=payload["source_text"],
            )
            response_payload = {
                "status": result["status"],
                "request": self._serialize_request(result["request"]),
                "outcome": result["outcome"].model_dump(),
                "view": result["view"],
            }
            if result["status"] == "failed":
                response_payload.update(
                    self._build_compile_failure_error_payload(
                        result,
                        error_code="compile_failed",
                    )
                )
            response_status = (
                HTTPStatus.BAD_REQUEST
                if result["status"] == "failed"
                else HTTPStatus.OK
            )
            self._write_json(response_status, response_payload)
            return

        if self.path == "/api/workbench/graph/validate":
            try:
                payload = self._read_json_request_body()
                result = service.validate_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "summary": result["summary"],
                    "diagnostics": result["diagnostics"],
                },
            )
            return

        if self.path == "/api/workbench/graph/compile":
            try:
                payload = self._read_optional_json_request_body()
                result = service.compile_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "request": self._serialize_request(result["request"]),
                    "outcome": result["outcome"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if self.path == "/api/workbench/graph/normalize":
            try:
                payload = self._read_json_request_body()
                result = service.normalize_graph_document(payload)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "changed": result["changed"],
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        if self.path == "/api/workbench/runtime/prepare":
            try:
                payload = self._read_optional_json_request_body()
                result = service.prepare_runtime_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "ready":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_prepare_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path == "/api/workbench/runtime/start":
            try:
                payload = self._read_optional_json_request_body()
                result = service.start_runtime_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "started" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "started":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_start_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/run"):
            try:
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/run")
                if not session_id or "/" in session_id:
                    raise ValueError("invalid runtime session path")
                self._read_optional_json_request_body()
                result = service.start_runtime_session_execution(session_id=session_id)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] in {"accepted", "completed", "failed"} else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] == "failed":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_run_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path == "/api/workbench/debug/prepare":
            try:
                payload = self._read_optional_json_request_body()
                result = service.prepare_debug_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/debug/start":
            try:
                payload = self._read_optional_json_request_body()
                result = service.start_debug_session(
                    self._extract_optional_graph_document_payload(payload)
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "started" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project/new":
            try:
                payload = self._read_json_request_body()
                project_name = payload.get("project_name")
                if not isinstance(project_name, str):
                    raise ValueError("field must be a string: project_name")
                project_directory = payload.get("project_directory")
                if project_directory is not None and not isinstance(project_directory, str):
                    raise ValueError("field must be a string: project_directory")
                result = service.create_project(
                    project_name=project_name,
                    project_directory=project_directory,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/settings":
            try:
                payload = self._read_json_request_body()
                project_settings = payload.get("project_settings")
                result = service.update_project_settings(project_settings=project_settings)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "project_settings": result["project_settings"],
                    "state": result["state"],
                },
            )
            return

        if self.path == "/api/workbench/project/runtime-defaults":
            try:
                payload = self._read_json_request_body()
                runtime_defaults = payload.get("runtime_defaults")
                if not isinstance(runtime_defaults, dict):
                    raise ValueError("field must be a JSON object: runtime_defaults")
                result = service.update_project_runtime_defaults(
                    runtime_defaults=runtime_defaults
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "runtime_defaults": result["runtime_defaults"],
                    "graph_projection_refresh": result["graph_projection_refresh"],
                },
            )
            return

        if self.path == "/api/workbench/project/package/preflight":
            try:
                self._read_json_request_body()
                result = service.run_project_package_preflight()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ok" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/project/package/build":
            try:
                payload = self._read_json_request_body()
                mode = payload.get("mode")
                source_of_truth = payload.get("source_of_truth")
                output_path = payload.get("output_path")
                if not isinstance(mode, str) or not mode.strip():
                    raise ValueError("field must be a non-empty string: mode")
                if not isinstance(source_of_truth, str) or not source_of_truth.strip():
                    raise ValueError("field must be a non-empty string: source_of_truth")
                if output_path is not None and not isinstance(output_path, str):
                    raise ValueError("field must be a string when provided: output_path")
                result = service.build_project_package(
                    mode=mode,
                    source_of_truth=source_of_truth,
                    output_path=output_path,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "built" else HTTPStatus.BAD_REQUEST
            response_payload = dict(result)
            if result["status"] != "built":
                response_payload.update(
                    {
                        "error": "project_package_build_failed",
                        "message": "project package build failed",
                    }
                )
            self._write_json(status_code, response_payload)
            return

        if self.path == "/api/workbench/project/package/load":
            try:
                payload = self._read_json_request_body()
                package_path = payload.get("package_path")
                if not isinstance(package_path, str) or not package_path.strip():
                    raise ValueError("field must be a non-empty string: package_path")
                result = service.load_project_package(package_path=package_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/package/unload":
            try:
                self._read_json_request_body()
                result = service.unload_project_package()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/project/package/external-resources/bind":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                value = payload.get("value")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("field must be a non-empty string: value")
                result = service.bind_loaded_package_external_resource(
                    resource_id=resource_id,
                    value=value,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/workbench/preferences":
            try:
                payload = self._read_json_request_body()
                section = payload.get("section")
                values = payload.get("values")
                if not isinstance(section, str) or not section.strip():
                    raise ValueError("field must be a non-empty string: section")
                if not isinstance(values, dict):
                    raise ValueError("field must be a JSON object: values")
                result = self._get_preferences_service().update_preferences(
                    section=section.strip(),
                    values=values,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "preferences": result,
                },
            )
            return

        if self.path == "/api/workbench/project/open":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.open_project(project_path=project_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/convert-webcontrol":
            try:
                payload = self._read_json_request_body()
                source_path = payload.get("source_path")
                output_project_path = payload.get("output_project_path")
                if not isinstance(source_path, str) or not source_path.strip():
                    raise ValueError("field must be a non-empty string: source_path")
                if not isinstance(output_project_path, str) or not output_project_path.strip():
                    raise ValueError("field must be a non-empty string: output_project_path")
                blueprint_paths = payload.get("blueprint_paths")
                if blueprint_paths is not None and (
                    not isinstance(blueprint_paths, list)
                    or any(not isinstance(item, str) or not item.strip() for item in blueprint_paths)
                ):
                    raise ValueError("field must be a non-empty string list when provided: blueprint_paths")
                blueprint_directory = payload.get("blueprint_directory")
                if blueprint_directory is not None and not isinstance(blueprint_directory, str):
                    raise ValueError("field must be a string when provided: blueprint_directory")
                project_name = payload.get("project_name")
                if project_name is not None and not isinstance(project_name, str):
                    raise ValueError("field must be a string when provided: project_name")
                overwrite_output = payload.get("overwrite_output", False)
                auto_open_project = payload.get("auto_open_project", False)
                preserve_legacy_metadata = payload.get("preserve_legacy_metadata", True)
                write_conversion_report = payload.get("write_conversion_report", True)
                for field_name, field_value in {
                    "overwrite_output": overwrite_output,
                    "auto_open_project": auto_open_project,
                    "preserve_legacy_metadata": preserve_legacy_metadata,
                    "write_conversion_report": write_conversion_report,
                }.items():
                    if not isinstance(field_value, bool):
                        raise ValueError(f"field must be a boolean when provided: {field_name}")
                result = service.convert_webcontrol_project(
                    source_path=source_path.strip(),
                    blueprint_paths=blueprint_paths,
                    blueprint_directory=blueprint_directory,
                    output_project_path=output_project_path.strip(),
                    project_name=project_name,
                    overwrite_output=overwrite_output,
                    auto_open_project=auto_open_project,
                    preserve_legacy_metadata=preserve_legacy_metadata,
                    write_conversion_report=write_conversion_report,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(HTTPStatus.OK, self._serialize_converter_result(result))
            return

        if self.path == "/api/workbench/project/save":
            try:
                payload = self._read_json_request_body()
                result = service.save_project(
                    graph_document_payload=self._extract_optional_graph_document_payload(
                        payload,
                        allow_bare_payload=False,
                    )
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/project/save-as":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.save_project_as(
                    project_path=project_path,
                    graph_document_payload=self._extract_optional_graph_document_payload(
                        payload,
                        allow_bare_payload=False,
                    ),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "project": result["project"],
                    "graph_document": result["graph_document"].model_dump(),
                },
            )
            return

        if self.path == "/api/workbench/preferences/reset":
            try:
                self._read_json_request_body()
                result = self._get_preferences_service().reset_preferences()
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "preferences": result,
                },
            )
            return

        if self.path == "/api/workbench/recent-projects/remove":
            try:
                payload = self._read_json_request_body()
                project_path = payload.get("project_path")
                if not isinstance(project_path, str):
                    raise ValueError("field must be a string: project_path")
                result = service.remove_recent_project(project_path=project_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "recent_projects": result["recent_projects"],
                },
            )
            return

        if self.path == "/api/workbench/resources/user-components":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError("field must be a string when provided: replace_existing_resource_id")
                result = service.save_user_component_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/subgraphs":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError(
                        "field must be a string when provided: replace_existing_resource_id"
                    )
                result = service.save_subgraph_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/custom-node-graphs":
            try:
                payload = self._read_json_request_body()
                resource_name = payload.get("resource_name")
                if not isinstance(resource_name, str):
                    raise ValueError("field must be a string: resource_name")
                tags = payload.get("tags")
                if tags is not None and not isinstance(tags, list):
                    raise ValueError("field must be an array when provided: tags")
                replace_existing_resource_id = payload.get("replace_existing_resource_id")
                if replace_existing_resource_id is not None and not isinstance(
                    replace_existing_resource_id, str
                ):
                    raise ValueError(
                        "field must be a string when provided: replace_existing_resource_id"
                    )
                result = service.save_custom_node_graph_resource(
                    resource_name=resource_name,
                    replace_existing_resource_id=replace_existing_resource_id,
                )
                if tags is not None:
                    result = service.update_resource_tags(
                        resource_id=result["resource"]["resource_id"],
                        tags=tags,
                    )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/export":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                export_path = payload.get("export_path")
                if not isinstance(resource_id, str):
                    raise ValueError("field must be a string: resource_id")
                if not isinstance(export_path, str):
                    raise ValueError("field must be a string: export_path")
                result = service.export_resource(resource_id=resource_id, export_path=export_path)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "resource": result["resource"],
                    "export_path": result["export_path"],
                },
            )
            return

        if self.path == "/api/workbench/resources/import":
            try:
                payload = self._read_json_request_body()
                import_path = payload.get("import_path")
                replace_existing = payload.get("replace_existing", False)
                if not isinstance(import_path, str):
                    raise ValueError("field must be a string: import_path")
                if not isinstance(replace_existing, bool):
                    raise ValueError("field must be a boolean when provided: replace_existing")
                result = service.import_resource(
                    import_path=import_path,
                    replace_existing=replace_existing,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/graph/source-projection":
            try:
                payload = self._read_json_request_body()
                target_source_kind = payload.get("target_source_kind", "native_flow")
                if not isinstance(target_source_kind, str):
                    raise ValueError("field must be a string when provided: target_source_kind")
                graph_document_payload = payload.get("graph_document")
                if graph_document_payload is not None and not isinstance(graph_document_payload, dict):
                    raise ValueError("field must be a JSON object when provided: graph_document")
                result = service.get_graph_source_projection_document(
                    target_source_kind=target_source_kind,
                    graph_document_payload=graph_document_payload,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = HTTPStatus.OK if result["status"] == "ready" else HTTPStatus.BAD_REQUEST
            self._write_json(status_code, result)
            return

        if self.path == "/api/workbench/editor/history/record":
            try:
                payload = self._read_json_request_body()
                operation_kind = payload.get("operation_kind")
                label = payload.get("label")
                operation_payload = payload.get("payload")
                if not isinstance(operation_kind, str):
                    raise ValueError("field must be a string: operation_kind")
                if not isinstance(label, str):
                    raise ValueError("field must be a string: label")
                result = service.record_editor_operation(
                    operation_kind=operation_kind,
                    label=label,
                    payload=operation_payload,
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "operation": result["operation"],
                    "history": result["history"],
                },
            )
            return

        if self.path.startswith("/api/workbench/runtime/") and self.path.endswith("/run"):
            try:
                self._read_json_request_body()
                session_id = self.path.removeprefix("/api/workbench/runtime/").removesuffix("/run")
                if not session_id:
                    raise ValueError("session_id must not be empty")
                result = service.run_runtime_session(session_id=session_id)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            status_code = (
                HTTPStatus.OK if result["status"] == "completed" else HTTPStatus.BAD_REQUEST
            )
            response_payload = dict(result)
            if result["status"] != "completed":
                response_payload.update(
                    self._build_runtime_failure_error_payload(
                        result,
                        error_code="runtime_run_failed",
                    )
                )
            self._write_json(status_code, response_payload)
            return

        if self.path.startswith("/api/workbench/resources/") and self.path.endswith("/enabled"):
            try:
                payload = self._read_json_request_body()
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("field must be a boolean: enabled")
                resource_id = self.path.removeprefix("/api/workbench/resources/").removesuffix(
                    "/enabled"
                )
                if not resource_id:
                    raise ValueError("resource_id must not be empty")
                result = service.set_resource_enabled(resource_id=resource_id, enabled=enabled)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path.startswith("/api/workbench/resources/") and self.path.endswith("/tags"):
            try:
                payload = self._read_json_request_body()
                tags = payload.get("tags")
                if not isinstance(tags, list):
                    raise ValueError("field must be an array: tags")
                resource_id = self.path.removeprefix("/api/workbench/resources/").removesuffix(
                    "/tags"
                )
                if not resource_id:
                    raise ValueError("resource_id must not be empty")
                result = service.update_resource_tags(resource_id=resource_id, tags=tags)
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/delete":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                result = service.delete_resource(resource_id=resource_id.strip())
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        if self.path == "/api/workbench/resources/rename":
            try:
                payload = self._read_json_request_body()
                resource_id = payload.get("resource_id")
                if not isinstance(resource_id, str) or not resource_id.strip():
                    raise ValueError("field must be a non-empty string: resource_id")
                display_name = payload.get("display_name")
                if not isinstance(display_name, str) or not display_name.strip():
                    raise ValueError("field must be a non-empty string: display_name")
                result = service.rename_resource(
                    resource_id=resource_id.strip(),
                    display_name=display_name.strip(),
                )
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "registry_revision": result["registry_revision"],
                    "resource": result["resource"],
                },
            )
            return

        self._write_not_found_error()

    def do_PUT(self) -> None:  # noqa: N802
        if not self._require_api_token():
            return
        try:
            service = self._get_service()
        except ValueError as exc:
            self._write_workspace_state_error(exc)
            return
        if self.path == "/api/workbench/graph":
            try:
                payload = self._read_json_request_body()
                expected_revision = payload.pop("expected_graph_document_save_revision", None)
                if expected_revision is not None and not isinstance(expected_revision, int):
                    raise ValueError(
                        "field must be an integer when provided: expected_graph_document_save_revision"
                    )
                result = service.save_graph_document(
                    payload,
                    expected_graph_document_save_revision=expected_revision,
                )
            except GraphDocumentRevisionConflictError as exc:
                self._write_graph_revision_conflict_error(exc)
                return
            except ValueError as exc:
                self._write_invalid_request_error(exc)
                return
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": result["status"],
                    "graph_model": result["graph_model"].model_dump(),
                    "view": result["view"],
                },
            )
            return

        self._write_not_found_error()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_not_found_error(self) -> None:
        sanitized_path = _sanitize_path_for_error(self.path)
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "path": sanitized_path,
                "message": f"resource not found: {sanitized_path}",
            },
        )

    def _write_workspace_state_error(self, exc: ValueError) -> None:
        self._write_json(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {
                "error": "workspace_state_invalid",
                "message": str(exc),
            },
        )

    def _write_invalid_request_error(self, exc: ValueError) -> None:
        payload = {
            "error": getattr(exc, "error_code", "invalid_request"),
            "message": str(exc),
        }
        recovery_action = getattr(exc, "recovery_action", None)
        if recovery_action is not None:
            payload["recovery_action"] = recovery_action
        self._write_json(
            HTTPStatus.BAD_REQUEST,
            payload,
        )

    def _write_host_file_dialog_unavailable_error(self) -> None:
        self._write_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "host.file_dialog_unavailable",
                "message": "host file dialog is unavailable",
            },
        )

    def _write_host_open_path_unavailable_error(self) -> None:
        self._write_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "host.open_path_unavailable",
                "message": "host open path is unavailable",
            },
        )

    def _write_graph_revision_conflict_error(
        self,
        exc: GraphDocumentRevisionConflictError,
    ) -> None:
        self._write_json(
            HTTPStatus.CONFLICT,
            {
                "error": "graph_revision_conflict",
                "message": str(exc),
            },
        )

    def _build_compile_failure_error_payload(
        self,
        result: dict,
        *,
        error_code: str,
    ) -> dict:
        view = result.get("view", {})
        primary_diagnostic = view.get("primary_diagnostic")
        message = "compile failed"
        if isinstance(primary_diagnostic, dict):
            primary_message = primary_diagnostic.get("message")
            if isinstance(primary_message, str) and primary_message.strip():
                message = primary_message
        details = {
            "primary_diagnostic": primary_diagnostic,
            "diagnostic_summary": view.get("diagnostic_summary"),
            "stage_overview": view.get("stage_overview"),
        }
        return {
            "error": error_code,
            "message": message,
            "details": details,
        }

    def _build_runtime_failure_error_payload(
        self,
        result: dict,
        *,
        error_code: str,
    ) -> dict:
        diagnostics = result.get("diagnostics")
        message = "runtime failed"
        details = None
        if isinstance(diagnostics, dict):
            entries = diagnostics.get("entries")
            primary_entry = None
            if isinstance(entries, list) and entries:
                severity_rank = {
                    "info": 0,
                    "warning": 1,
                    "degraded": 2,
                    "error": 3,
                    "fatal": 4,
                }
                typed_entries = [item for item in entries if isinstance(item, dict)]
                if typed_entries:
                    primary_entry = max(
                        typed_entries,
                        key=lambda item: severity_rank.get(item.get("severity"), -1),
                    )
                    primary_message = primary_entry.get("message")
                    if isinstance(primary_message, str) and primary_message.strip():
                        message = primary_message
            details = {
                "primary_diagnostic": primary_entry,
                "diagnostic_summary": {
                    "total_count": diagnostics.get("total_count"),
                    "highest_severity": diagnostics.get("highest_severity"),
                },
            }
        result_payload = result.get("result")
        if message == "runtime failed" and isinstance(result_payload, dict):
            failure_reason = result_payload.get("failure_reason")
            if isinstance(failure_reason, str) and failure_reason.strip():
                message = failure_reason
        return {
            "error": error_code,
            "message": message,
            "details": details,
        }

    def _serialize_request(self, request) -> dict:
        if hasattr(request, "model_dump"):
            return request.model_dump()
        return dict(request)

    def _serialize_converter_result(self, result: dict) -> dict:
        payload = dict(result)
        graph_document = payload.get("graph_document")
        if hasattr(graph_document, "model_dump"):
            payload["graph_document"] = graph_document.model_dump(mode="json")
        return payload

    def _get_optional_query_param(self, params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        if not values:
            return None
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _get_multi_query_param(self, params: dict[str, list[str]], key: str) -> list[str]:
        values = params.get(key, [])
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            parts = [item.strip() for item in value.split(",")]
            normalized.extend([item for item in parts if item])
        return normalized

    def _get_optional_bool_query_param(
        self,
        params: dict[str, list[str]],
        key: str,
    ) -> bool | None:
        value = self._get_optional_query_param(params, key)
        if value is None:
            return None
        if value.lower() in {"true", "1", "yes", "on"}:
            return True
        if value.lower() in {"false", "0", "no", "off"}:
            return False
        return None

    def _get_optional_float_query_param(
        self,
        params: dict[str, list[str]],
        key: str,
    ) -> float | None:
        value = self._get_optional_query_param(params, key)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"query parameter must be numeric when provided: {key}") from None

    def _handle_host_file_dialog(self) -> None:
        try:
            payload = self._read_json_request_body()
            self._validate_host_file_dialog_payload(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return

        provider = getattr(self.server, "file_dialog_provider", None)
        if provider is None:
            self._write_host_file_dialog_unavailable_error()
            return

        try:
            result = provider(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except RuntimeError as exc:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "host.file_dialog_unavailable",
                    "message": str(exc) or "host file dialog is unavailable",
                },
            )
            return

        if not isinstance(result, dict):
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "host.file_dialog_invalid_response",
                    "message": "host file dialog provider must return a JSON object",
                },
            )
            return
        self._write_json(HTTPStatus.OK, result)

    def _validate_host_file_dialog_payload(self, payload: dict) -> None:
        mode = payload.get("mode")
        allowed_modes = {"open_file", "open_files", "open_folder", "save_file"}
        if mode not in allowed_modes:
            raise ValueError(
                "field must be one of open_file, open_files, open_folder, save_file: mode"
            )
        title = payload.get("title")
        if title is not None and not isinstance(title, str):
            raise ValueError("field must be a string when provided: title")
        default_path = payload.get("default_path")
        if default_path is not None and not isinstance(default_path, str):
            raise ValueError("field must be a string when provided: default_path")
        file_types = payload.get("file_types")
        if file_types is not None and (
            not isinstance(file_types, list)
            or any(not isinstance(item, str) for item in file_types)
        ):
            raise ValueError("field must be a string list when provided: file_types")

    def _handle_host_open_path(self) -> None:
        try:
            payload = self._read_json_request_body()
            resolved_path = self._validate_host_open_path_payload(payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return

        provider = getattr(self.server, "open_path_provider", None)
        if provider is None:
            self._write_host_open_path_unavailable_error()
            return

        provider_payload = {
            "path": str(resolved_path),
            "target_kind": "directory" if resolved_path.is_dir() else "file",
        }
        try:
            result = provider(provider_payload)
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except RuntimeError as exc:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "host.open_path_unavailable",
                    "message": str(exc) or "host open path is unavailable",
                },
            )
            return

        if not isinstance(result, dict):
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "host.open_path_invalid_response",
                    "message": "host open path provider must return a JSON object",
                },
            )
            return
        self._write_json(HTTPStatus.OK, result)

    def _validate_host_open_path_payload(self, payload: dict) -> Path:
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("field must be a non-empty string: path")
        resolved_path = Path(raw_path).expanduser().resolve()
        if not resolved_path.exists():
            exc = ValueError("path does not exist")
            exc.error_code = "host.open_path_missing"
            raise exc
        return resolved_path

    def _handle_host_read_file(self) -> None:
        try:
            payload = self._read_json_request_body()
            path, encoding, max_bytes = self._validate_host_read_file_payload(payload)
            resolved_path = path.expanduser().resolve()
            allowed_roots = self._collect_host_read_roots()
            if not any(_is_path_under_root(resolved_path, root) for root in allowed_roots):
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "forbidden",
                        "message": (
                            f"file path is not within any allowed directory: {resolved_path}"
                        ),
                    },
                )
                return
            if not resolved_path.is_file():
                exc = ValueError("path must point to a regular file")
                exc.error_code = "host.read_file_not_file"
                raise exc
            file_size = resolved_path.stat().st_size
            if file_size > max_bytes:
                exc = ValueError(f"file is too large: {file_size} bytes")
                exc.error_code = "host.read_file_too_large"
                raise exc
            raw_content = resolved_path.read_bytes()
            try:
                content = raw_content.decode(encoding)
            except UnicodeDecodeError as decode_exc:
                exc = ValueError(f"file cannot be decoded with {encoding}")
                exc.error_code = "host.read_file_decode_failed"
                raise exc from decode_exc
        except ValueError as exc:
            self._write_invalid_request_error(exc)
            return
        except OSError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "host.read_file_failed",
                    "message": str(exc),
                },
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "status": "read",
                "path": str(resolved_path),
                "encoding": encoding,
                "content": content,
                "bytes_read": len(raw_content),
            },
        )

    def _validate_host_read_file_payload(self, payload: dict) -> tuple[Path, str, int]:
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("field must be a non-empty string: path")
        encoding = payload.get("encoding", "utf-8")
        if not isinstance(encoding, str) or not encoding.strip():
            raise ValueError("field must be a non-empty string when provided: encoding")
        max_bytes_value = payload.get("max_bytes", 2 * 1024 * 1024)
        if not isinstance(max_bytes_value, int) or max_bytes_value <= 0:
            raise ValueError("field must be a positive integer when provided: max_bytes")
        return Path(raw_path), encoding.strip(), max_bytes_value

    def _collect_host_read_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        workspace_state_path = self._resolve_workspace_state_path().resolve()
        workspace_root = workspace_state_path.parent
        roots.append(workspace_root)
        ui_root = self._resolve_ui_dist_path().resolve()
        roots.append(ui_root)
        try:
            service = self._get_service()
        except ValueError:
            service = None
        if service is not None:
            project_document = service.get_project_document()
            project_file_path = project_document.get("project", {}).get("project_file_path")
            if isinstance(project_file_path, str) and project_file_path.strip():
                project_root = Path(project_file_path).resolve().parent
                if project_root not in roots:
                    roots.append(project_root)
        return tuple(dict.fromkeys(roots))

    def _try_serve_ui_asset(self) -> bool:
        request_path = unquote(urlparse(self.path).path)
        if request_path.startswith("/api/"):
            return False
        ui_dist_path = self._resolve_ui_dist_path()
        index_path = ui_dist_path / "index.html"
        if not index_path.exists():
            return False

        relative_path = request_path.lstrip("/")
        if request_path in {"", "/"}:
            return self._write_file_response(index_path, content_type="text/html; charset=utf-8")

        requested_file = (ui_dist_path / relative_path).resolve()
        try:
            requested_file.relative_to(ui_dist_path.resolve())
        except ValueError:
            return False

        if requested_file.is_file():
            content_type, _ = mimetypes.guess_type(str(requested_file))
            return self._write_file_response(
                requested_file,
                content_type=content_type or "application/octet-stream",
            )

        if "." not in Path(relative_path).name:
            return self._write_file_response(index_path, content_type="text/html; charset=utf-8")

        return False

    def _write_file_response(self, path: Path, *, content_type: str) -> bool:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _write_runtime_stream(
        self,
        service: CompilationWorkbenchService,
        session_id: str,
    ) -> None:
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        initial_snapshot = service.get_runtime_stream_snapshot(session_id=session_id)
        self._write_sse_event("runtime.snapshot", initial_snapshot)
        initial_status = initial_snapshot.get("status")
        if initial_status == "completed":
            self._write_sse_event(
                "runtime.summary",
                {
                    "session_id": initial_snapshot.get("session_id"),
                    "status": initial_snapshot.get("status"),
                    "total_node_count": len(initial_snapshot.get("node_states", [])),
                    "completed_node_count": initial_snapshot.get("execution_summary", {}).get("completed_node_count", 0),
                    "failed_node_count": initial_snapshot.get("execution_summary", {}).get("failed_node_count", 0),
                    "running_node_count": 0,
                    "pending_node_count": 0,
                    "percent": 100.0,
                    "event_count": initial_snapshot.get("execution_summary", {}).get("event_count", 0),
                },
            )
            self._write_sse_event("runtime.completed", initial_snapshot)
            return
        if initial_status == "failed":
            total_node_count = len(initial_snapshot.get("node_states", []))
            failed_count = initial_snapshot.get("execution_summary", {}).get("failed_node_count", 0)
            completed_count = initial_snapshot.get("execution_summary", {}).get("completed_node_count", 0)
            pending_count = max(total_node_count - completed_count - failed_count, 0)
            percent = ((completed_count + failed_count) / total_node_count * 100.0) if total_node_count else 0.0
            self._write_sse_event(
                "runtime.summary",
                {
                    "session_id": initial_snapshot.get("session_id"),
                    "status": initial_snapshot.get("status"),
                    "total_node_count": total_node_count,
                    "completed_node_count": completed_count,
                    "failed_node_count": failed_count,
                    "running_node_count": 0,
                    "pending_node_count": pending_count,
                    "percent": round(percent, 1),
                    "event_count": initial_snapshot.get("execution_summary", {}).get("event_count", 0),
                },
            )
            self._write_sse_event("runtime.failed", initial_snapshot)
            return
        for event_name, payload in service.iter_runtime_stream_events(session_id=session_id):
            if event_name == "runtime.snapshot":
                continue
            self._write_sse_event(event_name, payload)
            if event_name in {"runtime.completed", "runtime.failed"}:
                break

    def _write_sse_event(self, event_name: str, payload: dict) -> None:
        body = (
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _read_json_request_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _read_optional_json_request_body(self) -> dict | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        if not raw_body.strip():
            return None
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        if payload == {}:
            return None
        return payload

    def _extract_optional_graph_document_payload(
        self,
        payload: dict | None,
        *,
        allow_bare_payload: bool = True,
    ) -> dict | None:
        if payload is None:
            return None
        if "graph_document" not in payload:
            return payload if allow_bare_payload else None
        graph_document_payload = payload.get("graph_document")
        if graph_document_payload is None:
            return None
        if not isinstance(graph_document_payload, dict):
            raise ValueError("field must be a JSON object when provided: graph_document")
        return graph_document_payload

    def _validate_compile_payload(self, payload: dict) -> None:
        required_fields = ("source_kind", "entry_document", "source_text")
        for field_name in required_fields:
            if field_name not in payload:
                raise ValueError(f"missing required field: {field_name}")
        for field_name in ("source_kind", "entry_document"):
            field_value = payload[field_name]
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"field must be a non-empty string: {field_name}")
        if not isinstance(payload["source_text"], str):
            raise ValueError("field must be a string: source_text")

    def _get_service(self) -> CompilationWorkbenchService:
        if not hasattr(self.server, "workbench_service"):
            self.server.workbench_service = CompilationWorkbenchService(
                state_store=FileWorkspaceStateStore(self._resolve_workspace_state_path()),
                preferences_service=self._get_preferences_service(),
            )
        return self.server.workbench_service

    def _get_preferences_service(self) -> PreferencesService:
        if not hasattr(self.server, "preferences_service"):
            self.server.preferences_service = PreferencesService(
                preferences_store=FilePreferencesStore(self._resolve_preferences_path())
            )
        return self.server.preferences_service

    def _resolve_workspace_state_path(self) -> Path:
        configured_path = getattr(self.server, "workspace_state_path", None)
        if configured_path is None:
            return DEFAULT_WORKSPACE_STATE_PATH
        return Path(configured_path)

    def _resolve_ui_dist_path(self) -> Path:
        configured_path = getattr(self.server, "ui_dist_path", None)
        if configured_path is None:
            return DEFAULT_UI_DIST_PATH
        return Path(configured_path)

    def _resolve_preferences_path(self) -> Path:
        configured_path = getattr(self.server, "preferences_path", None)
        if configured_path is None:
            return DEFAULT_PREFERENCES_PATH
        return Path(configured_path)

    def _build_ui_hosting_metadata(self) -> dict:
        ui_dist_path = self._resolve_ui_dist_path().resolve()
        index_path = ui_dist_path / "index.html"
        ui_dist_available = index_path.exists()
        return {
            "ui_hosted": ui_dist_available,
            "ui_dist_available": ui_dist_available,
            "ui_dist_path": str(ui_dist_path),
            "ui_entrypoint": "/" if ui_dist_available else None,
        }

    def _build_server_bind_metadata(self) -> dict:
        host, port = self.server.server_address
        return {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
        }

    def _build_release_manifest(self) -> dict:
        return {
            "manifest_version": "phase3-host-baseline",
            "startup_command": (
                "python -m weconduct.cli.main serve-api "
                f"--host {self.server.server_address[0]} "
                f"--port {self.server.server_address[1]} "
                "--workspace-state-path <...> "
                "--preferences-path <...> "
                "--ui-dist-path <...>"
            ),
            "workspace_state_path": "<redacted>",
            "preferences_path": "<redacted>",
            "ui_dist_path": "<redacted>",
        }


def build_api_server(
    *,
    host: str,
    port: int,
    workspace_state_path: str | Path | None = None,
    preferences_path: str | Path | None = None,
    ui_dist_path: str | Path | None = None,
    api_token: str | None = None,
) -> WeConductApiServer:
    server = WeConductApiServer((host, port), WeConductApiHandler)
    server.workspace_state_path = (
        Path(workspace_state_path)
        if workspace_state_path is not None
        else DEFAULT_WORKSPACE_STATE_PATH
    )
    server.preferences_path = (
        Path(preferences_path) if preferences_path is not None else DEFAULT_PREFERENCES_PATH
    )
    server.ui_dist_path = (
        Path(ui_dist_path)
        if ui_dist_path is not None
        else DEFAULT_UI_DIST_PATH
    )
    server.api_token = api_token
    return server
