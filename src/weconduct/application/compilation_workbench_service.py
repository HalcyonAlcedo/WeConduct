from datetime import datetime, timezone
from copy import deepcopy
import json
from pathlib import Path
import shutil
from time import perf_counter
from threading import Lock, Thread
import uuid

from pydantic import ValidationError

from weconduct.compiler import CompilerFacade
from weconduct.compiler.errors import CompilationAbortedError
from weconduct.compiler.sources.legacy_webcontrol import (
    build_legacy_webcontrol_blueprint_custom_node_graph_seed,
)
from weconduct.builtin_components import (
    build_builtin_resource_registry,
    get_graph_node_draft_definition,
)
from weconduct.runtime import RuntimeContext, RuntimeExecutorRegistry, execute_runtime_node
from weconduct.runtime.engine import _safe_eval_expression
from weconduct.contracts import (
    CompilationOutcome,
    CompilationRequest,
    CompilationSource,
    Diagnostic,
    DiagnosticCatalog,
    GraphModel,
    create_empty_graph_model,
    create_initial_summary,
)
from weconduct.application.preferences_service import PreferencesService
from weconduct.application.legacy_webcontrol_converter import (
    build_conversion_report,
    convert_legacy_webcontrol_project,
)
from weconduct.application.runtime_session_stream import RuntimeSessionStreamBroker
from weconduct.application.workspace_state_store import (
    FileWorkspaceStateStore,
    InMemoryWorkspaceStateStore,
    WORKSPACE_STATE_VERSION,
    WorkspaceStateStore,
)

SUPPORTED_SOURCE_KINDS = [
    "graph_workspace",
    "native_flow",
    "webcontrol_main_flow",
    "webcontrol_blueprint",
]
SUPPORTED_STAGE_NAMES = ["parse", "bind", "validate", "normalize", "lower", "emit"]
COMPILE_STATUSES = ["succeeded", "failed", "unsupported"]
DIAGNOSTIC_SEVERITIES = ["info", "warning", "degraded", "error", "fatal"]
RESOURCE_TYPES = ["builtin_component", "user_component", "subgraph_resource", "custom_node_graph"]
RESOURCE_IMPLEMENTATION_KINDS = ["core_atomic", "builtin_custom_component", "project_component"]
NODE_TAXONOMIES = [
    "builtin_component",
    "control_structure",
    "logic_expression",
    "graph_edge_semantics",
    "user_component",
    "compat_action",
]
LEGACY_SUBGRAPH_RESOURCE_PREFIX = "subgraph_resource:"
CUSTOM_NODE_GRAPH_RESOURCE_PREFIX = "custom_node_graph:"
DIAGNOSTIC_SEVERITY_RANK = {
    "info": 0,
    "warning": 1,
    "degraded": 2,
    "error": 3,
    "fatal": 4,
}
MAX_COMPILE_HISTORY = 5
MAX_RECENT_PROJECTS = 10
MAX_RECENT_PROJECTS_LIMIT = 100
PROJECT_FILE_SCHEMA_VERSION = 2
LEGACY_PROJECT_FILE_SCHEMA_VERSION = 1
RESOURCE_EXPORT_SCHEMA_VERSION = 1
MAX_EDITOR_HISTORY_DEPTH = 100
MAX_RUNTIME_SESSION_HISTORY = 20
MAX_DEBUG_SESSION_HISTORY = 20
MAX_RUNTIME_EXECUTION_STEPS = 1000
MAX_COMPONENT_CALL_DEPTH = 8
SOURCE_TEMPLATES = {
    "graph_workspace": {
        "entry_document": "graph:workspace",
        "source_text": (
            '{"graph_model_id":"graph:workspace","compilation_id":null,'
            '"graph_schema_version":"graph-v1","nodes":['
            '{"node_id":"node-1","lowered_kind":"execution","source_anchor_ref":"n1",'
            '"expansion_role":"action:request","display_name":"HTTP Request",'
            '"node_kind":"http.request","position":{"x":120,"y":80},"ports":['
            '{"port_id":"out-main","direction":"output","relation_layer":"data",'
            '"semantic_slot":"out.result"}],"node_config":{"method":"GET"}},'
            '{"node_id":"node-2","lowered_kind":"execution","source_anchor_ref":"n2",'
            '"expansion_role":"transform:map","display_name":"Map Result",'
            '"node_kind":"data.map","position":{"x":360,"y":80},"ports":['
            '{"port_id":"in-main","direction":"input","relation_layer":"data",'
            '"semantic_slot":"in.default"}],"node_config":{"mode":"map"}}],'
            '"edges":[{"edge_id":"edge-1","relation_layer":"data","from_node_id":"node-1",'
            '"to_node_id":"node-2","from_port_id":"out-main","to_port_id":"in-main",'
            '"edge_state":"draft"}],"viewport":{"x":0,"y":0,"zoom":1.1},'
            '"graph_effective_diagnostic_anchor_refs":[]}'
        ),
    },
    "native_flow": {
        "entry_document": "examples/native-flow.json",
        "source_text": (
            '{"nodes":[{"id":"n1","role":"action",'
            '"capability_domain":"http","action_kind":"request"}]}'
        ),
    },
    "webcontrol_main_flow": {
        "entry_document": "examples/webcontrol-main-flow.json",
        "source_text": (
            '{"project_info":{"name":"demo"},'
            '"automation_steps":[{"step_id":"step-1","action":"open_url"}]}'
        ),
    },
    "webcontrol_blueprint": {
        "entry_document": "examples/webcontrol-blueprint.json",
        "source_text": (
            '{"blueprint_info":{"id":"blueprint-demo","name":"Demo Blueprint"},'
            '"input_schema":{"username":{"type":"string"}},'
            '"output_schema":{"logged_in":{"type":"boolean"}},'
            '"automation_steps":[{"step_id":"step-1","action":"open_url"}]}'
        ),
    },
}
DEFAULT_SOURCE_KIND = "graph_workspace"
NATIVE_FLOW_CAPABILITY_DOMAINS = {"http", "data", "file", "os", "browser", "excel", "python"}
NATIVE_FLOW_ROLES = {"action", "transform", "condition"}


class GraphCompileMappingError(ValueError):
    def __init__(self, diagnostics: list[dict]) -> None:
        super().__init__("graph compile mapping failed")
        self.diagnostics = diagnostics


class GraphDocumentRevisionConflictError(ValueError):
    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        super().__init__(
            "graph document save revision conflict: "
            f"expected {expected_revision}, current {current_revision}"
        )
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class ProjectRequiresSaveAsError(ValueError):
    def __init__(self) -> None:
        super().__init__("project_file_path is not set; use save_project_as first")
        self.error_code = "project.needs_save_as"
        self.recovery_action = "save_as"


class CompilationWorkbenchService:
    def __init__(
        self,
        *,
        state_store: WorkspaceStateStore | None = None,
        preferences_service: PreferencesService | None = None,
        runtime_stream_broker: RuntimeSessionStreamBroker | None = None,
    ) -> None:
        self._compiler = CompilerFacade()
        self._state_store = state_store or InMemoryWorkspaceStateStore()
        self._preferences_service = preferences_service or PreferencesService()
        self._runtime_stream_broker = runtime_stream_broker or RuntimeSessionStreamBroker()
        self._runtime_execution_lock = Lock()
        self._runtime_execution_threads: dict[str, Thread] = {}
        self._suppress_dirty_workspace_recovery = False
        self._allow_dirty_workspace_recovery_conversion = True
        loaded_state = self._state_store.load()
        state, changed = self._normalize_workspace_state(loaded_state)
        if changed:
            state = self._state_store.mutate(
                lambda current: self._normalize_workspace_state(current)[0]
            )
        self._state = state
        self._allow_dirty_workspace_recovery_conversion = False

    def get_workbench_snapshot(self) -> dict:
        self._refresh_state_from_store()
        graph_model = self._get_graph_document_model()
        return {
            "workbench": self._build_workbench_metadata(),
            "project": self._build_project_metadata(),
            "graph_workspace": self._build_graph_workspace_metadata(graph_model),
            "preferences": self._preferences_service.get_preferences_document(),
            "capabilities": self._build_capabilities_metadata(),
            "entrypoints": self._build_entrypoints_metadata(),
            "compiler": {
                "available_source_kinds": SUPPORTED_SOURCE_KINDS,
                "default_source_kind": DEFAULT_SOURCE_KIND,
                "supported_stage_names": SUPPORTED_STAGE_NAMES,
                "compile_statuses": COMPILE_STATUSES,
                "compile_history_limit": MAX_COMPILE_HISTORY,
                "diagnostic_severities": DIAGNOSTIC_SEVERITIES,
                "source_templates": self._build_source_templates(),
            },
            "last_compile": self._state["last_compile"],
            "compile_history": list(self._state["compile_history"]),
        }

    def get_runtime_health(self) -> dict:
        self._refresh_state_from_store()
        workbench = self._build_workbench_metadata()
        return {
            "status": "ok",
            "service": "weconduct-api",
            "host_mode": workbench["host_mode"],
            "api_version": workbench["api_version"],
            "workspace_state_version": workbench["workspace_state_version"],
            "workspace_session_id": workbench["workspace_session_id"],
            "service_started_at": workbench["service_started_at"],
            "capabilities": self._build_capabilities_metadata(),
            "entrypoints": self._build_entrypoints_metadata(),
        }

    def get_graph_document(self) -> dict:
        self._refresh_state_from_store()
        graph_model = self._get_graph_document_model()
        return {
            "graph_model": graph_model,
            "view": self._build_graph_document_view(graph_model),
        }

    def get_project_document(self) -> dict:
        self._refresh_state_from_store()
        graph_model = self._get_graph_document_model()
        return {
            "project": self._build_project_metadata(),
            "graph_workspace": self._build_graph_workspace_metadata(graph_model),
        }

    def get_recent_projects_document(self) -> dict:
        self._refresh_state_from_store()
        return {
            "recent_projects": self._get_recent_projects(),
        }

    def get_resource_registry_document(
        self,
        *,
        query: str | None = None,
        tags: list[str] | None = None,
        enabled: bool | None = None,
        origin: str | None = None,
        resource_type: str | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        resources = self._filter_resources(
            [
                item for item in self._get_resource_registry()
                if item.get("resource_manager_visible") is True
            ],
            query=query,
            tags=tags,
            enabled=enabled,
            origin=origin,
            resource_type=resource_type,
        )
        return {
            "registry_revision": self._get_resource_registry_revision(),
            "resource_types": list(RESOURCE_TYPES),
            "summary": self._build_resource_registry_summary(resources),
            "facets": self._build_resource_facets(resources),
            "resources": [
                {
                    **item,
                    "category_group_path": list(item.get("category_group_path", [])),
                    "category_group_label": item.get("category_group_label"),
                }
                for item in resources
            ],
        }

    def get_project_documents_document(self) -> dict:
        self._refresh_state_from_store()
        graph_model = self._get_graph_document_model()
        graph_document_meta = self._get_graph_document_meta()
        project_runtime = self._get_project_runtime()
        project_file_path = project_runtime.get("project_file_path")
        project_layout = None
        if isinstance(project_file_path, str) and project_file_path.strip():
            project_layout = self._build_project_storage_layout(Path(project_file_path))
        return {
            "main_graph_document_id": graph_model.graph_model_id,
            "documents": [
                {
                    "document_id": graph_model.graph_model_id,
                    "document_role": "main_graph",
                    "document_type": "graph_document",
                    "graph_schema_version": graph_model.graph_schema_version,
                    "node_count": len(graph_model.nodes),
                    "edge_count": len(graph_model.edges),
                    "save_revision": graph_document_meta["save_revision"],
                    "saved_at": graph_document_meta["saved_at"],
                }
            ],
            "project_file": (
                project_layout["project_manifest"]
                if isinstance(project_layout, dict)
                else None
            ),
            "graph_document": (
                project_layout["graph_document"]
                if isinstance(project_layout, dict)
                else graph_model.model_dump()
            ),
            "project_owned_resources_index": (
                project_layout["project_owned_resources_index"]
                if isinstance(project_layout, dict)
                else None
            ),
            "resource_overrides": (
                project_layout["resource_overrides"]
                if isinstance(project_layout, dict)
                else None
            ),
        }

    def get_project_resource_audit_document(self) -> dict:
        self._refresh_state_from_store()
        project_runtime = self._get_project_runtime()
        project_file_path = project_runtime.get("project_file_path")
        if not isinstance(project_file_path, str) or not project_file_path.strip():
            return {
                "status": "ready",
                "project_file_path": None,
                "storage_root": None,
                "summary": {"resource_count": 0, "issue_count": 0, "healthy_count": 0},
                "resources": [],
                "issues": [],
            }
        return self._build_project_resource_audit_document(Path(project_file_path))

    def get_graph_source_projection_document(
        self,
        *,
        target_source_kind: str,
        graph_document_payload: dict | None = None,
    ) -> dict:
        if target_source_kind != "native_flow":
            raise ValueError(f"unsupported graph source projection kind: {target_source_kind}")

        graph_model, request_meta = self._resolve_graph_document_request(graph_document_payload)
        graph_document_meta = (
            self._get_graph_document_meta()
            if request_meta["request_origin"] == "saved_graph_document"
            else {"save_revision": None, "saved_at": None}
        )
        try:
            source_text = self._graph_model_to_native_flow_source_text(graph_model)
        except GraphCompileMappingError as exc:
            return {
                "status": "ready",
                "source_kind": "graph_workspace",
                "request_origin": request_meta["request_origin"],
                "graph_model_id": graph_model.graph_model_id,
                "graph_document_save_revision": graph_document_meta["save_revision"],
                "entry_document": graph_model.graph_model_id,
                "source_text": json.dumps(
                    graph_model.model_dump(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "diagnostics": exc.diagnostics,
            }

        return {
            "status": "ready",
            "source_kind": target_source_kind,
            "request_origin": request_meta["request_origin"],
            "graph_model_id": graph_model.graph_model_id,
            "graph_document_save_revision": graph_document_meta["save_revision"],
            "entry_document": "graph:workspace.native-flow.json",
            "source_text": source_text,
            "diagnostics": [],
        }

    def get_component_library_document(
        self,
        *,
        query: str | None = None,
        tags: list[str] | None = None,
        enabled: bool | None = None,
        origin: str | None = None,
        resource_type: str | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        resources = self._filter_resources(
            [
                item for item in self._get_resource_registry()
                if item["enabled"] is True and item.get("component_library_visible") is True
            ],
            query=query,
            tags=tags,
            enabled=enabled,
            origin=origin,
            resource_type=resource_type,
        )
        items = [
            {
                "resource_id": item["resource_id"],
                "display_name": item["display_name"],
                "display_name_i18n": dict(item.get("display_name_i18n", {})),
                "resource_type": item["resource_type"],
                "resource_key": item["resource_key"],
                "enabled": item["enabled"],
                "category": self._infer_resource_category(item),
                "node_taxonomy": item["node_taxonomy"],
                "component_library_visible": item["component_library_visible"],
                "resource_manager_visible": item["resource_manager_visible"],
                "user_creatable": item["user_creatable"],
                "compatibility_only": item["compatibility_only"],
                "graph_semantic_kind": item["graph_semantic_kind"],
                "description": item.get("description"),
                "description_i18n": dict(item.get("description_i18n", {})),
                "tags": list(item.get("tags", [])),
                "category_path": list(item.get("category_path", [])),
                "category_group_path": list(item.get("category_group_path", [])),
                "category_group_label": item.get("category_group_label"),
                "search_tokens": list(item.get("search_tokens", [])),
            }
            for item in resources
        ]
        return {
            "summary": {
                "available_resource_count": len(items),
            },
            "facets": self._build_resource_facets(resources),
            "items": items,
        }

    def build_graph_node_draft(
        self,
        *,
        resource_key: str,
        node_id: str | None = None,
        position: dict | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        if not isinstance(resource_key, str) or not resource_key.strip():
            raise ValueError("resource_key must be a non-empty string")
        normalized_resource_key = resource_key.strip()
        resource = self._find_graph_node_draft_resource(normalized_resource_key)
        if resource is None:
            raise ValueError(f"resource not found for graph node draft: {normalized_resource_key}")
        if resource.get("compatibility_only") is True or resource.get("user_creatable") is False:
            raise ValueError(
                "compatibility-only resource cannot be created directly: "
                f"{normalized_resource_key}"
            )
        draft_definition = self._build_graph_node_draft_definition(
            resource=resource,
            resource_key=normalized_resource_key,
        )
        resolved_node_id = self._build_graph_node_draft_node_id(node_id=node_id)
        graph_node = {
            "node_id": resolved_node_id,
            "lowered_kind": draft_definition["lowered_kind"],
            "source_anchor_ref": f"n-{resolved_node_id}",
            "expansion_role": draft_definition["expansion_role"],
            "display_name": self._resolve_resource_display_name(resource),
            "node_kind": normalized_resource_key,
            "ports": deepcopy(draft_definition["ports"]),
            "node_config": deepcopy(draft_definition["node_config"]),
        }
        if isinstance(position, dict):
            x_value = position.get("x")
            y_value = position.get("y")
            if isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
                graph_node["position"] = {
                    "x": float(x_value),
                    "y": float(y_value),
                }
        return {
            "resource": {
                "resource_id": resource["resource_id"],
                "resource_key": resource["resource_key"],
                "display_name": graph_node["display_name"],
                "display_name_i18n": dict(resource.get("display_name_i18n", {})),
                "resource_type": resource.get("resource_type"),
                "node_taxonomy": resource.get("node_taxonomy"),
                "graph_semantic_kind": resource.get("graph_semantic_kind"),
            },
            "node": graph_node,
            "parameter_schema": deepcopy(draft_definition.get("parameter_schema", {})),
        }

    def normalize_graph_document(self, graph_document_payload: dict) -> dict:
        try:
            graph_model = GraphModel.model_validate(graph_document_payload)
        except ValidationError as exc:
            raise ValueError(f"graph document payload is invalid: {exc.errors()[0]['loc']}") from exc
        normalized_graph_model, changed = self._normalize_graph_model(graph_model)
        return {
            "status": "normalized",
            "changed": changed,
            "graph_model": normalized_graph_model,
            "view": self._build_graph_document_view(normalized_graph_model),
        }

    def get_editor_history_document(self) -> dict:
        self._refresh_state_from_store()
        editor_history = self._get_editor_history()
        return {
            "undo_depth": len(editor_history["undo_stack"]),
            "redo_depth": len(editor_history["redo_stack"]),
            "undo_stack": editor_history["undo_stack"],
            "redo_stack": editor_history["redo_stack"],
        }

    def get_execution_history_document(
        self,
        *,
        runtime_status: str | None = None,
        debug_status: str | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        execution_history = self._get_execution_history()
        runtime_runs = self._filter_execution_history_entries(
            execution_history["runtime_runs"],
            status=runtime_status,
        )
        debug_sessions = self._filter_execution_history_entries(
            execution_history["debug_sessions"],
            status=debug_status,
        )
        return {
            "summary": {
                "runtime_run_count": len(runtime_runs),
                "debug_session_count": len(debug_sessions),
                "runtime_status_counts": self._build_execution_status_counts(runtime_runs),
                "debug_status_counts": self._build_execution_status_counts(debug_sessions),
            },
            "runtime_runs": runtime_runs,
            "debug_sessions": debug_sessions,
        }

    def get_runtime_session(self, *, session_id: str) -> dict:
        self._refresh_state_from_store()
        session = self._find_runtime_session(session_id)
        response = dict(session)
        response["node_states"] = self._decorate_runtime_node_states_for_display(
            session.get("node_states", [])
        )
        return response

    def list_runtime_sessions(self) -> dict:
        self._refresh_state_from_store()
        sessions = self._get_runtime_sessions()
        return {
            "sessions": [
                {
                    "session_id": item["runtime_session"]["session_id"],
                    "status": item["runtime_session"]["status"],
                    "graph_model_id": item["runtime_plan"]["graph_model_id"],
                    "started_at": item["runtime_session"]["started_at"],
                    "completed_at": item["runtime_session"].get("completed_at"),
                    "completed_node_count": item["runtime_session"].get("completed_node_count", 0),
                    "failed_node_count": item["runtime_session"].get("failed_node_count", 0),
                    "event_count": item.get("execution_summary", {}).get("event_count", 0),
                    "latest_event_kind": item.get("execution_summary", {}).get("latest_event_kind"),
                }
                for item in sessions
            ]
        }

    def get_debug_session(self, *, session_id: str) -> dict:
        self._refresh_state_from_store()
        session = self._find_debug_session(session_id)
        return dict(session)

    def list_debug_sessions(self) -> dict:
        self._refresh_state_from_store()
        sessions = self._get_debug_sessions()
        return {
            "sessions": [
                {
                    "session_id": item["debug_session"]["session_id"],
                    "status": item["debug_session"]["status"],
                    "graph_model_id": item["object_index"]["graph_model_id"],
                    "started_at": item["debug_session"]["started_at"],
                    "prepared_at": item["debug_session"].get("prepared_at"),
                    "scheduler_mode": item.get("runtime_preview_summary", {}).get("scheduler_mode"),
                    "queued_node_count": item.get("runtime_preview_summary", {}).get("queued_node_count", 0),
                    "current_node_id": item.get("runtime_preview_summary", {}).get("current_node_id"),
                }
                for item in sessions
            ]
        }

    def create_project(
        self,
        *,
        project_name: str,
        project_directory: str | Path | None = None,
    ) -> dict:
        normalized_name = project_name.strip()
        if not normalized_name:
            raise ValueError("project_name must not be empty")
        if project_directory is None:
            default_project_directory = self._get_default_project_directory()
            if default_project_directory is not None:
                project_directory = default_project_directory

        def mutation(state: dict | None) -> dict:
            recent_projects = self._extract_recent_projects(state)
            current_state = self._build_initial_workspace_state(
                project_name=normalized_name,
                mark_project_dirty=True,
            )
            current_state["recent_projects"] = recent_projects
            return current_state

        self._state = self._state_store.mutate(mutation)
        if project_directory is not None:
            resolved_directory = self._resolve_project_directory(project_directory)
            project_path = resolved_directory / f"{normalized_name}.weconduct.json"
            result = self._save_project_to_path(project_path)
            result["status"] = "created"
            return result
        graph_model = self._get_graph_document_model()
        return {
            "status": "created",
            "project": self._build_project_metadata(),
            "graph_document": graph_model,
        }

    def save_project(self, *, graph_document_payload: dict | None = None) -> dict:
        self._refresh_state_from_store()
        project_runtime = self._get_project_runtime()
        project_file_path = project_runtime["project_file_path"]
        if project_file_path is None:
            raise ProjectRequiresSaveAsError()
        if graph_document_payload is not None:
            self.save_graph_document(graph_document_payload)
        return self._save_project_to_path(Path(project_file_path))

    def save_project_as(
        self,
        *,
        project_path: str | Path,
        graph_document_payload: dict | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        if graph_document_payload is not None:
            self.save_graph_document(graph_document_payload)
        resolved_path = self._resolve_project_path(project_path)
        return self._save_project_to_path(resolved_path)

    def remove_recent_project(self, *, project_path: str | Path) -> dict:
        self._refresh_state_from_store()
        resolved_path = self._resolve_project_path(project_path)
        serialized_path = str(resolved_path)

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            current_state["recent_projects"] = [
                item
                for item in self._extract_recent_projects(current_state)
                if item.get("project_path") != serialized_path
            ]
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "removed",
            "recent_projects": self._get_recent_projects(),
        }

    def open_project(self, *, project_path: str | Path) -> dict:
        self._refresh_state_from_store()
        resolved_path = self._resolve_project_path(project_path)
        project_document = self._read_project_file(resolved_path)

        def mutation(state: dict | None) -> dict:
            recent_projects = self._extract_recent_projects(state)
            current_state = self._build_initial_workspace_state(
                project_name=project_document["project"]["project_name"],
                project_id=project_document["project"]["project_id"],
                project_file_path=resolved_path,
                mark_project_dirty=False,
            )
            current_state["project"].update(project_document["project"])
            current_state["project"]["workspace_root"] = str(resolved_path.parent)
            current_state["graph_document"] = project_document["graph_document"]
            current_state["graph_document_meta"] = project_document["graph_document_meta"]
            current_state["resource_registry"] = project_document["resource_registry"]
            current_state["editor_history"] = project_document["editor_history"]
            current_state["execution_history"] = project_document["execution_history"]
            current_state["recent_projects"] = self._upsert_recent_project_record(
                recent_projects,
                project_name=current_state["project"]["project_name"],
                project_path=resolved_path,
            )
            return current_state

        self._state = self._state_store.mutate(mutation)
        graph_model = self._get_graph_document_model()
        return {
            "status": "opened",
            "project": self._build_project_metadata(),
            "graph_document": graph_model,
        }

    def convert_webcontrol_project(
        self,
        *,
        source_path: str | Path,
        output_project_path: str | Path,
        blueprint_paths: list[str | Path] | None = None,
        blueprint_directory: str | Path | None = None,
        project_name: str | None = None,
        overwrite_output: bool = False,
        auto_open_project: bool = False,
        preserve_legacy_metadata: bool = True,
        write_conversion_report: bool = True,
    ) -> dict:
        self._refresh_state_from_store()
        resolved_output_project_path = self._resolve_project_path(output_project_path)
        if resolved_output_project_path.exists() and not overwrite_output:
            raise ValueError(
                f"output project already exists: {resolved_output_project_path}; "
                "set overwrite_output=true to overwrite"
            )
        conversion = convert_legacy_webcontrol_project(
            source_path=source_path,
            blueprint_paths=blueprint_paths,
            blueprint_directory=blueprint_directory,
            preserve_legacy_metadata=preserve_legacy_metadata,
        )
        report_path = None
        temp_service = self._build_temporary_project_conversion_service()
        temp_project_name = (
            project_name.strip()
            if isinstance(project_name, str) and project_name.strip()
            else conversion.project_name
        )
        temp_service.create_project(project_name=temp_project_name)
        temp_service.save_graph_document(conversion.graph_model.model_dump(mode="json"))
        for blueprint_result in conversion.blueprint_results:
            temp_service.import_resource_from_record(blueprint_result.resource_record)
        save_result = temp_service.save_project_as(project_path=resolved_output_project_path)
        if write_conversion_report:
            report_path = (
                resolved_output_project_path.parent
                / f"{resolved_output_project_path.stem}.data"
                / "conversion-report.json"
            )
        report = build_conversion_report(
            conversion=conversion,
            output_project_path=resolved_output_project_path,
            report_path=report_path,
        )
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        response = {
            "status": "converted",
            "output_project_path": str(resolved_output_project_path.resolve()),
            "output_storage_root": str(
                self._resolve_project_storage_root(resolved_output_project_path).resolve()
            ),
            "report_path": str(report_path.resolve()) if report_path is not None else None,
            "report": report,
        }
        if auto_open_project:
            opened = self.open_project(project_path=resolved_output_project_path)
            response["project"] = opened["project"]
            response["graph_document"] = opened["graph_document"]
        else:
            response["project"] = save_result["project"]
            response["graph_document"] = save_result["graph_document"]
        return response

    def restore_pending_recovery(self) -> dict:
        self._refresh_state_from_store()

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            pending_recovery = self._extract_pending_recovery(current_state)
            if pending_recovery is None:
                raise ValueError("pending recovery was not found")
            restored_state = deepcopy(pending_recovery["workspace_state"])
            restored_state["pending_recovery"] = None
            normalized_state, _ = self._normalize_workspace_state_without_recovery_conversion(
                restored_state
            )
            return normalized_state

        self._state = self._state_store.mutate(mutation)
        self._suppress_dirty_workspace_recovery = True
        graph_model = self._get_graph_document_model()
        return {
            "status": "restored",
            "project": self._build_project_metadata(),
            "graph_document": graph_model,
        }

    def discard_pending_recovery(self) -> dict:
        self._refresh_state_from_store()

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            pending_recovery = self._extract_pending_recovery(current_state)
            if pending_recovery is None:
                raise ValueError("pending recovery was not found")
            recent_projects = self._extract_recent_projects(current_state)
            next_state = self._build_initial_workspace_state(
                project_name=pending_recovery["project_name"],
                project_id=pending_recovery["project_id"],
                project_file_path=pending_recovery["project_file_path"],
                mark_project_dirty=False,
            )
            next_state["recent_projects"] = recent_projects
            next_state["pending_recovery"] = None
            return next_state

        self._state = self._state_store.mutate(mutation)
        graph_model = self._get_graph_document_model()
        return {
            "status": "discarded",
            "project": self._build_project_metadata(),
            "graph_document": graph_model,
        }

    def save_user_component_resource(
        self,
        *,
        resource_name: str,
        replace_existing_resource_id: str | None = None,
    ) -> dict:
        return self._save_graph_backed_resource(
            resource_name=resource_name,
            replace_existing_resource_id=replace_existing_resource_id,
            resource_type="user_component",
            default_id_prefix="user_component",
            description="User component captured from current graph document.",
        )

    def save_subgraph_resource(
        self,
        *,
        resource_name: str,
        replace_existing_resource_id: str | None = None,
    ) -> dict:
        return self._save_graph_backed_resource(
            resource_name=resource_name,
            replace_existing_resource_id=replace_existing_resource_id,
            resource_type="subgraph_resource",
            default_id_prefix="subgraph_resource",
            description="Reusable subgraph resource captured from current graph document.",
        )

    def save_custom_node_graph_resource(
        self,
        *,
        resource_name: str,
        replace_existing_resource_id: str | None = None,
    ) -> dict:
        return self._save_graph_backed_resource(
            resource_name=resource_name,
            replace_existing_resource_id=replace_existing_resource_id,
            resource_type="custom_node_graph",
            default_id_prefix="custom_node_graph",
            description="Reusable custom node graph captured from current graph document.",
        )

    def update_resource_tags(
        self,
        *,
        resource_id: str,
        tags: list[str],
    ) -> dict:
        self._refresh_state_from_store()
        updated_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            matched = False
            next_resources: list[dict] = []
            for item in resources:
                if item["resource_id"] == resource_id:
                    matched = True
                    updated_item = dict(item)
                    updated_item["tags"] = self._normalize_user_tags(tags)
                    normalized_item = self._normalize_resource_record(updated_item)
                    if normalized_item is None:
                        raise ValueError(f"resource payload is invalid after tag update: {resource_id}")
                    updated_resource_holder["value"] = normalized_item
                    next_resources.append(normalized_item)
                else:
                    next_resources.append(item)
            if not matched:
                raise ValueError(f"resource not found: {resource_id}")
            current_state["resource_registry"] = next_resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "updated",
            "resource": updated_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def _save_graph_backed_resource(
        self,
        *,
        resource_name: str,
        replace_existing_resource_id: str | None,
        resource_type: str,
        default_id_prefix: str,
        description: str,
    ) -> dict:
        self._refresh_state_from_store()
        normalized_name = resource_name.strip()
        if not normalized_name:
            raise ValueError("resource_name must not be empty")
        graph_model = self._get_graph_document_model()
        graph_document_meta = self._get_graph_document_meta()
        saved_resource_holder: dict[str, dict] = {}
        derived_input_schema: dict = {}
        derived_output_schema: dict = {}
        has_boundary_nodes = False
        if resource_type == "custom_node_graph":
            has_boundary_nodes, derived_input_schema, derived_output_schema = (
                self._extract_custom_node_graph_boundary_schemas(graph_model.model_dump())
            )

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            if replace_existing_resource_id is not None:
                target_index = None
                for index, item in enumerate(resources):
                    if item["resource_id"] == replace_existing_resource_id:
                        target_index = index
                        break
                if target_index is None:
                    raise ValueError(f"resource not found: {replace_existing_resource_id}")
                resource_id = replace_existing_resource_id
            else:
                target_index = None
                resource_id = f"{default_id_prefix}:{uuid.uuid4().hex[:12]}"
            resource_record = {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "display_name": normalized_name,
                "resource_key": resource_id,
                "enabled": True,
                "origin": "project",
                "description": description,
                "source_graph_document_id": graph_model.graph_model_id,
                "source_graph_document_save_revision": graph_document_meta["save_revision"],
                "source_graph_document": graph_model.model_dump(),
                "input_schema": (
                    deepcopy(derived_input_schema)
                    if resource_type == "custom_node_graph" and has_boundary_nodes
                    else self._extract_graph_resource_schema(
                        graph_model.root_metadata,
                        schema_key="input_schema",
                    )
                ),
                "output_schema": (
                    deepcopy(derived_output_schema)
                    if resource_type == "custom_node_graph" and has_boundary_nodes
                    else self._extract_graph_resource_schema(
                        graph_model.root_metadata,
                        schema_key="output_schema",
                    )
                ),
                "tags": (
                    graph_model.root_metadata.get("resource_tags")
                    if isinstance(graph_model.root_metadata, dict)
                    else None
                ),
            }
            normalized_resource_record = self._normalize_resource_record(resource_record)
            if normalized_resource_record is None:
                raise ValueError(f"{resource_type} resource payload is invalid")
            if target_index is None:
                resources.insert(0, normalized_resource_record)
            else:
                resources[target_index] = normalized_resource_record
            current_state["resource_registry"] = resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            saved_resource_holder["value"] = dict(normalized_resource_record)
            return current_state

        self._state = self._state_store.mutate(mutation)
        if resource_type == "custom_node_graph":
            self._refresh_workspace_graph_validation_snapshot()
        return {
            "status": "saved",
            "resource": saved_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def export_resource(self, *, resource_id: str, export_path: str | Path) -> dict:
        self._refresh_state_from_store()
        resolved_path = self._resolve_export_path(export_path)
        resource = self._require_resource(resource_id)
        payload = {
            "resource_export_schema_version": RESOURCE_EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "resource": resource,
        }
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "status": "exported",
            "resource": resource,
            "export_path": str(resolved_path),
        }

    def export_custom_node_graph_resource(
        self,
        *,
        resource_id: str,
        target_directory: str | Path,
    ) -> dict:
        self._refresh_state_from_store()
        resource = self._require_resource(resource_id)
        if resource.get("resource_type") != "custom_node_graph":
            raise ValueError(f"custom node graph resource not found: {resource_id}")
        target = self._resolve_export_path(target_directory)
        target.mkdir(parents=True, exist_ok=True)
        self._write_json_file(target / "manifest.json", self._build_project_resource_manifest(resource))
        self._write_json_file(
            target / "graph.json",
            self._build_project_resource_graph_document(resource),
        )
        return {
            "status": "exported",
            "resource": resource,
            "target_directory": str(target),
        }

    def import_resource(
        self,
        *,
        import_path: str | Path,
        replace_existing: bool = False,
    ) -> dict:
        self._refresh_state_from_store()
        resolved_path = self._resolve_export_path(import_path)
        if not resolved_path.exists():
            raise ValueError(f"resource import file not found: {resolved_path}")
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"resource import file must be valid JSON: {resolved_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"resource import file must be a JSON object: {resolved_path}")
        raw_resource: dict | None = None
        if payload.get("resource_export_schema_version") == RESOURCE_EXPORT_SCHEMA_VERSION:
            raw_resource = payload.get("resource")
            if not isinstance(raw_resource, dict):
                raise ValueError(
                    f"resource import file missing required object: resource ({resolved_path})"
                )
        else:
            raw_resource = self._build_legacy_resource_import_payload(
                payload=payload,
                import_path=resolved_path,
            )
        if raw_resource is None:
            raise ValueError(
                "resource export schema version mismatch: "
                f"expected {RESOURCE_EXPORT_SCHEMA_VERSION}, got "
                f"{payload.get('resource_export_schema_version')!r}"
            )
        imported_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            normalized_resource = self._normalize_resource_record(raw_resource)
            if normalized_resource is None:
                raise ValueError("resource import payload is invalid")
            existing_index = None
            for index, item in enumerate(resources):
                if item["resource_id"] == normalized_resource["resource_id"]:
                    existing_index = index
                    break
            if existing_index is not None and not replace_existing:
                raise ValueError(
                    f"resource already exists: {normalized_resource['resource_id']}; "
                    "set replace_existing=true to overwrite"
                )
            if existing_index is None:
                resources.insert(0, normalized_resource)
            else:
                resources[existing_index] = normalized_resource
            current_state["resource_registry"] = resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            imported_resource_holder["value"] = normalized_resource
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "imported",
            "resource": imported_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def import_custom_node_graph_resource(
        self,
        *,
        source_directory: str | Path,
        conflict_policy: str = "rename",
    ) -> dict:
        self._refresh_state_from_store()
        source = self._resolve_export_path(source_directory)
        manifest_path = source / "manifest.json"
        graph_path = source / "graph.json"
        if not manifest_path.exists():
            raise ValueError(f"custom node graph manifest not found: {manifest_path}")
        if not graph_path.exists():
            raise ValueError(f"custom node graph graph file not found: {graph_path}")
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"custom node graph manifest must be valid JSON: {manifest_path}") from exc
        try:
            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"custom node graph graph file must be valid JSON: {graph_path}") from exc
        if not isinstance(manifest_payload, dict):
            raise ValueError(f"custom node graph manifest must be a JSON object: {manifest_path}")
        if not isinstance(graph_payload, dict):
            raise ValueError(f"custom node graph graph file must be a JSON object: {graph_path}")
        resource = {
            **manifest_payload,
            "source_graph_document": graph_payload,
            "resource_type": "custom_node_graph",
            "origin": manifest_payload.get("origin", "project"),
            "implementation_kind": manifest_payload.get(
                "implementation_kind", "project_component"
            ),
        }
        normalized_resource = self._normalize_resource_record(resource)
        if normalized_resource is None:
            raise ValueError("custom node graph import payload is invalid")
        resolved_resource = self._resolve_imported_custom_node_graph_conflict(
            normalized_resource,
            conflict_policy=conflict_policy,
        )
        imported = self.import_resource_from_record(resolved_resource)
        return {
            "status": imported["status"],
            "resource": imported["resource"],
            "registry_revision": imported["registry_revision"],
        }

    def import_resource_from_record(
        self,
        raw_resource: dict,
        *,
        replace_existing: bool = False,
    ) -> dict:
        self._refresh_state_from_store()
        imported_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            normalized_resource = self._normalize_resource_record(raw_resource)
            if normalized_resource is None:
                raise ValueError("resource import payload is invalid")
            existing_index = None
            for index, item in enumerate(resources):
                if item["resource_id"] == normalized_resource["resource_id"]:
                    existing_index = index
                    break
            if existing_index is not None and not replace_existing:
                raise ValueError(
                    f"resource already exists: {normalized_resource['resource_id']}; "
                    "set replace_existing=true to overwrite"
                )
            if existing_index is None:
                resources.insert(0, normalized_resource)
            else:
                resources[existing_index] = normalized_resource
            current_state["resource_registry"] = resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            imported_resource_holder["value"] = normalized_resource
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "imported",
            "resource": imported_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def _resolve_imported_custom_node_graph_conflict(
        self,
        resource: dict,
        *,
        conflict_policy: str,
    ) -> dict:
        normalized_policy = conflict_policy.strip().lower()
        if normalized_policy != "rename":
            raise ValueError(
                "unsupported custom node graph conflict policy: "
                f"{conflict_policy}"
            )
        existing_ids = {item["resource_id"] for item in self._get_resource_registry()}
        if resource["resource_id"] not in existing_ids:
            return dict(resource)
        next_resource = dict(resource)
        next_resource["resource_id"] = (
            f"{CUSTOM_NODE_GRAPH_RESOURCE_PREFIX}{uuid.uuid4().hex[:12]}"
        )
        next_resource["resource_key"] = next_resource["resource_id"]
        return next_resource

    def _build_legacy_resource_import_payload(
        self,
        *,
        payload: dict,
        import_path: Path,
    ) -> dict | None:
        if not self._looks_like_legacy_webcontrol_blueprint_payload(payload):
            return None
        source_text = import_path.read_text(encoding="utf-8")
        compiler = CompilerFacade()
        request = CompilationRequest(
            compilation_id=f"legacy-blueprint-import-{uuid.uuid4().hex[:12]}",
            source=CompilationSource(
                kind="webcontrol_blueprint",
                entry_document=str(import_path),
                source_text=source_text,
            ),
        )
        outcome = compiler.compile(request)
        graph_model = outcome.graph_model
        if graph_model is None:
            raise ValueError(f"legacy blueprint import compile produced no graph: {import_path}")
        resource_seed = build_legacy_webcontrol_blueprint_custom_node_graph_seed(
            source_text,
            fallback_name=import_path.stem,
        )
        return {
            **resource_seed,
            "source_graph_document_id": graph_model.graph_model_id,
            "source_graph_document_save_revision": 1,
            "source_graph_document": graph_model.model_dump(),
        }

    def _looks_like_legacy_webcontrol_blueprint_payload(self, payload: dict) -> bool:
        automation_steps = payload.get("automation_steps")
        if not isinstance(automation_steps, list):
            return False
        blueprint_info = payload.get("blueprint_info")
        if not isinstance(blueprint_info, dict):
            return False
        return True

    def _build_temporary_project_conversion_service(self) -> "CompilationWorkbenchService":
        return CompilationWorkbenchService(
            state_store=InMemoryWorkspaceStateStore(),
            preferences_service=self._preferences_service,
        )

    def set_resource_enabled(self, *, resource_id: str, enabled: bool) -> dict:
        self._refresh_state_from_store()
        updated_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            matched = False
            next_resources: list[dict] = []
            for item in resources:
                if item["resource_id"] == resource_id:
                    matched = True
                    updated_item = dict(item)
                    updated_item["enabled"] = enabled
                    updated_resource_holder["value"] = updated_item
                    next_resources.append(updated_item)
                else:
                    next_resources.append(item)
            if not matched:
                raise ValueError(f"resource not found: {resource_id}")
            current_state["resource_registry"] = next_resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "updated",
            "resource": updated_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def delete_resource(self, *, resource_id: str) -> dict:
        self._refresh_state_from_store()
        deleted_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            matched = False
            next_resources: list[dict] = []
            for item in resources:
                if item["resource_id"] == resource_id:
                    matched = True
                    if item.get("resource_type") == "builtin_component":
                        raise ValueError(f"builtin resource cannot be deleted: {resource_id}")
                    deleted_resource_holder["value"] = dict(item)
                    continue
                next_resources.append(item)
            if not matched:
                raise ValueError(f"resource not found: {resource_id}")
            current_state["resource_registry"] = next_resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            return current_state

        self._state = self._state_store.mutate(mutation)
        deleted_resource = deleted_resource_holder["value"]
        if deleted_resource.get("resource_type") == "custom_node_graph":
            self._refresh_workspace_graph_validation_snapshot()
        return {
            "status": "deleted",
            "resource": deleted_resource,
            "registry_revision": self._get_resource_registry_revision(),
        }

    def rename_resource(self, *, resource_id: str, display_name: str) -> dict:
        self._refresh_state_from_store()
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            raise ValueError("display_name must not be empty")
        renamed_resource_holder: dict[str, dict] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            resources = self._extract_resource_registry(current_state)
            matched = False
            next_resources: list[dict] = []
            for item in resources:
                if item["resource_id"] == resource_id:
                    matched = True
                    if item.get("resource_type") == "builtin_component":
                        raise ValueError(f"builtin resource cannot be renamed: {resource_id}")
                    updated_item = dict(item)
                    updated_item["display_name"] = normalized_display_name
                    display_name_i18n = dict(updated_item.get("display_name_i18n", {}))
                    display_name_i18n["en-US"] = normalized_display_name
                    updated_item["display_name_i18n"] = display_name_i18n
                    renamed_resource_holder["value"] = updated_item
                    next_resources.append(updated_item)
                else:
                    next_resources.append(item)
            if not matched:
                raise ValueError(f"resource not found: {resource_id}")
            current_state["resource_registry"] = next_resources
            current_state["project"]["resource_registry_revision"] += 1
            current_state["project_runtime"] = {
                **self._extract_project_runtime(current_state),
                "is_dirty": True,
            }
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "renamed",
            "resource": renamed_resource_holder["value"],
            "registry_revision": self._get_resource_registry_revision(),
        }

    def record_editor_operation(
        self,
        *,
        operation_kind: str,
        label: str,
        payload: dict | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        normalized_kind = operation_kind.strip()
        normalized_label = label.strip()
        if not normalized_kind:
            raise ValueError("operation_kind must not be empty")
        if not normalized_label:
            raise ValueError("label must not be empty")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object when provided")
        operation_record = {
            "operation_id": f"edit-op-{uuid.uuid4().hex[:12]}",
            "operation_kind": normalized_kind,
            "label": normalized_label,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            editor_history = self._extract_editor_history(current_state)
            editor_history["undo_stack"].insert(0, operation_record)
            editor_history["undo_stack"] = editor_history["undo_stack"][:MAX_EDITOR_HISTORY_DEPTH]
            editor_history["redo_stack"] = []
            current_state["editor_history"] = editor_history
            return current_state

        self._state = self._state_store.mutate(mutation)
        return {
            "status": "recorded",
            "operation": operation_record,
            "history": self.get_editor_history_document(),
        }

    def start_runtime_session(self, graph_document_payload: dict | None) -> dict:
        graph_model, request_meta = self._resolve_graph_document_request(graph_document_payload)
        compile_result = self._compile_graph_document_transient(
            graph_model,
            compilation_id_prefix="runtime",
        )
        if compile_result["status"] != "succeeded" or compile_result["outcome"].graph_model is None:
            return {
                "status": "failed",
                "request": {
                    "compilation_id": compile_result["request"]["compilation_id"],
                    "request_origin": request_meta["request_origin"],
                    "requested_graph_model_id": request_meta["requested_graph_model_id"],
                    "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                    "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                    "compile_status": compile_result["status"],
                },
                "runtime_session": {
                    "session_id": None,
                    "status": "diagnostic_blocked",
                    "execution_supported": False,
                },
                "runtime_plan": None,
                "diagnostics": self._build_compilation_diagnostics_summary(compile_result),
            }
        runtime_plan = self._build_runtime_plan(compile_result["outcome"].graph_model)
        session_id = f"runtime-session-{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()
        session_document = {
            "request": {
                "compilation_id": compile_result["request"]["compilation_id"],
                "request_origin": request_meta["request_origin"],
                "requested_graph_model_id": request_meta["requested_graph_model_id"],
                "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                "compile_status": compile_result["status"],
            },
            "runtime_session": {
                "session_id": session_id,
                "status": "running",
                "execution_supported": True,
                "started_at": started_at,
                "completed_at": None,
                "completed_node_count": 0,
            },
            "runtime_plan": runtime_plan,
            "node_states": [
                {
                    "node_id": node["node_id"],
                    "node_status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "input_snapshot": None,
                    "output": None,
                    "runtime_order": None,
                    "static_order": node.get("static_order"),
                    "plan_index": node.get("plan_index"),
                }
                for node in runtime_plan["executable_nodes"]
            ],
            "event_log": [
                {
                    "event_kind": "session.started",
                    "recorded_at": started_at,
                    "session_id": session_id,
                }
            ],
            "debug_snapshot": self._build_runtime_debug_snapshot(
                scheduler_mode=runtime_plan.get("scheduler_mode"),
                pending_node_entries=[],
                queued_node_ids=set(),
                executed_node_ids_in_order=[],
                join_state_by_node_id={},
                retry_state_by_node_id={},
                executable_nodes=runtime_plan["executable_nodes"],
                current_program_counter=None,
                current_repeat_mode=False,
            ),
            "diagnostic_events": [],
            "execution_summary": {
                "status": "running",
                "completed_node_count": 0,
                "failed_node_count": 0,
                "event_count": 1,
                "diagnostic_event_count": 0,
            },
            "result": None,
        }
        self._remember_runtime_session(session_document)
        self._runtime_stream_broker.publish_snapshot(
            session_id,
            self._build_runtime_stream_snapshot_payload(
                session_id=session_id,
                session=session_document,
                runtime_session=session_document["runtime_session"],
                node_states=session_document["node_states"],
                event_log=session_document["event_log"],
                result=None,
            ),
        )
        return {
            "status": "started",
            **{
                **session_document,
                "node_states": self._decorate_runtime_node_states_for_display(
                    session_document["node_states"]
                ),
            },
            "diagnostics": self._build_compilation_diagnostics_summary(compile_result),
        }

    def run_runtime_session(self, *, session_id: str) -> dict:
        return self._run_runtime_session_sync(session_id=session_id)

    def start_runtime_session_execution(self, *, session_id: str) -> dict:
        self._refresh_state_from_store()
        existing_session = self._find_runtime_session(session_id)
        if existing_session["runtime_session"]["status"] in {"completed", "failed"}:
            return {
                "status": existing_session["runtime_session"]["status"],
                **existing_session,
            }
        with self._runtime_execution_lock:
            existing_thread = self._runtime_execution_threads.get(session_id)
            if existing_thread is not None and existing_thread.is_alive():
                return {
                    "status": "accepted",
                    **existing_session,
                }
            thread = Thread(
                target=self._run_runtime_session_sync,
                kwargs={"session_id": session_id},
                daemon=True,
                name=f"runtime-{session_id}",
            )
            self._runtime_execution_threads[session_id] = thread
            thread.start()
        refreshed = self.get_runtime_session(session_id=session_id)
        return {
            "status": "accepted",
            **refreshed,
        }

    def _run_runtime_session_sync(self, *, session_id: str) -> dict:
        self._refresh_state_from_store()
        existing_session = self._find_runtime_session(session_id)
        if existing_session["runtime_session"]["status"] in {"completed", "failed"}:
            return {
                "status": existing_session["runtime_session"]["status"],
                **existing_session,
            }

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            sessions = self._extract_runtime_sessions(current_state)
            target_index = None
            for index, item in enumerate(sessions):
                if item["runtime_session"]["session_id"] == session_id:
                    target_index = index
                    break
            if target_index is None:
                raise ValueError(f"runtime session not found: {session_id}")

            session = dict(sessions[target_index])
            node_states = [dict(item) for item in session["node_states"]]
            event_log = list(session["event_log"])
            completed_node_ids: list[str] = []
            failed_node_ids: list[str] = []
            runtime_context = RuntimeContext(
                project_directory=self._resolve_runtime_project_directory(),
                workspace_root=self._resolve_runtime_workspace_root(),
            )
            runtime_context.flow_runtime["graph_root_metadata"] = deepcopy(
                session["runtime_plan"].get("root_metadata", {})
            )
            executor_registry = RuntimeExecutorRegistry(
                runtime_settings=self._build_runtime_execution_settings()
            )
            session_status = "completed"
            failure_reason = None
            runtime_execution_order_counter = 0

            try:
                executable_nodes = [dict(item) for item in session["runtime_plan"]["executable_nodes"]]
                node_index_by_id = {
                    item["node_id"]: index for index, item in enumerate(executable_nodes)
                }
                data_edges_by_target = self._build_runtime_data_edges_by_target(
                    session["runtime_plan"].get("relation_edges", [])
                )
                control_edges_by_source: dict[str, list[dict]] = {}
                for edge in session["runtime_plan"].get("relation_edges", []):
                    if edge.get("relation_layer") != "control":
                        continue
                    source_id = edge.get("from_node_id")
                    if isinstance(source_id, str):
                        control_edges_by_source.setdefault(source_id, []).append(dict(edge))

                scheduler_mode = session["runtime_plan"].get("scheduler_mode")
                join_state_by_node_id: dict[str, dict[str, object]] = {}
                retry_state_by_node_id: dict[str, dict[str, object]] = {}
                pending_node_entries: list[dict[str, object]] = []
                queued_node_ids: set[str] = set()
                executed_node_ids: set[str] = set()
                control_edges_by_target = self._build_runtime_relation_edges_by_target(
                    relation_edges=session["runtime_plan"].get("relation_edges", []),
                    relation_layer="control",
                )
                node_kind_by_id = {
                    item["node_id"]: item.get("node_kind") for item in executable_nodes
                }

                def publish_live_update(event_name: str, payload: dict) -> None:
                    runtime_session = {
                        **session["runtime_session"],
                        "status": session_status if failure_reason is not None else "running",
                        "completed_node_count": len(completed_node_ids),
                        "failed_node_count": len(failed_node_ids),
                    }
                    self._runtime_stream_broker.publish_event(session_id, event_name, dict(payload))
                    self._runtime_stream_broker.publish_event(
                        session_id,
                        "runtime.summary",
                        self._build_runtime_stream_summary_payload(
                            session_id=session_id,
                            runtime_session=runtime_session,
                            node_states=node_states,
                            event_log=event_log,
                        ),
                    )
                    self._runtime_stream_broker.publish_snapshot(
                        session_id,
                        self._build_runtime_stream_snapshot_payload(
                            session_id=session_id,
                            session=session,
                            runtime_session=runtime_session,
                            node_states=node_states,
                            event_log=event_log,
                            result=None,
                        ),
                    )

                def queue_control_edge(edge: dict, *, repeat_mode_value: bool) -> None:
                    self._queue_runtime_control_edge_with_wait_all(
                        edge=edge,
                        repeat_mode_value=repeat_mode_value,
                        control_edges_by_source=control_edges_by_source,
                        control_edges_by_target=control_edges_by_target,
                        node_index_by_id=node_index_by_id,
                        node_kind_by_id=node_kind_by_id,
                        join_state_by_node_id=join_state_by_node_id,
                        pending_node_entries=pending_node_entries,
                        queued_node_ids=queued_node_ids,
                        executed_node_ids=executed_node_ids,
                        executable_nodes=executable_nodes,
                        event_log=event_log,
                        session_id=session_id,
                    )

                def queue_control_edges(
                    *,
                    source_node_id: str,
                    source_port_id: str | None,
                    repeat_mode_value: bool,
                ) -> None:
                    for edge in control_edges_by_source.get(source_node_id, []):
                        if source_port_id is not None and edge.get("from_port_id") not in {None, source_port_id}:
                            continue
                        queue_control_edge(edge, repeat_mode_value=repeat_mode_value)

                if scheduler_mode == "flow_graph":
                    for entry_node_id in session["runtime_plan"].get("entry_node_ids", []):
                        entry_index = node_index_by_id.get(entry_node_id)
                        if entry_index is not None:
                            self._enqueue_runtime_flow_graph_node(
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                node_index=entry_index,
                                repeat_mode=False,
                                event_log=event_log,
                                session_id=session_id,
                            )
                    next_entry = pending_node_entries.pop(0) if pending_node_entries else None
                    if isinstance(next_entry, dict):
                        dispatched_node_index = next_entry.get("node_index")
                        if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                            dispatched_node = executable_nodes[dispatched_node_index]
                            dispatched_at = datetime.now(timezone.utc).isoformat()
                            event_log.append(
                                {
                                    "event_kind": "token.dispatched",
                                    "recorded_at": dispatched_at,
                                    "session_id": session_id,
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                    "repeat_mode": bool(next_entry.get("repeat_mode")),
                                }
                            )
                            event_log.append(
                                {
                                    "event_kind": "node.ready",
                                    "recorded_at": dispatched_at,
                                    "session_id": session_id,
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                }
                            )
                    program_counter = (
                        int(next_entry["node_index"])
                        if isinstance(next_entry, dict)
                        else -1
                    )
                    repeat_mode = (
                        bool(next_entry.get("repeat_mode"))
                        if isinstance(next_entry, dict)
                        else False
                    )
                else:
                    program_counter = 0
                    repeat_mode = False
                execution_step_count = 0
                while 0 <= program_counter < len(node_states):
                    if execution_step_count >= MAX_RUNTIME_EXECUTION_STEPS:
                        session_status = "failed"
                        failure_reason = "runtime.execution_step_limit_exceeded"
                        break
                    execution_step_count += 1
                    node_state = node_states[program_counter]
                    executable_node = executable_nodes[program_counter]
                    if (
                        scheduler_mode == "flow_graph"
                        and repeat_mode is not True
                        and node_state["node_id"] in executed_node_ids
                    ):
                        next_entry = pending_node_entries.pop(0) if pending_node_entries else None
                        if isinstance(next_entry, dict):
                            dispatched_node_index = next_entry.get("node_index")
                            if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                                dispatched_node = executable_nodes[dispatched_node_index]
                                dispatched_at = datetime.now(timezone.utc).isoformat()
                                event_log.append(
                                    {
                                        "event_kind": "token.dispatched",
                                        "recorded_at": dispatched_at,
                                        "session_id": session_id,
                                        "node_id": dispatched_node["node_id"],
                                        "node_kind": dispatched_node.get("node_kind"),
                                        "repeat_mode": bool(next_entry.get("repeat_mode")),
                                    }
                                )
                                event_log.append(
                                    {
                                        "event_kind": "node.ready",
                                        "recorded_at": dispatched_at,
                                        "session_id": session_id,
                                        "node_id": dispatched_node["node_id"],
                                        "node_kind": dispatched_node.get("node_kind"),
                                    }
                                )
                        program_counter = (
                            int(next_entry["node_index"])
                            if isinstance(next_entry, dict)
                            else -1
                        )
                        repeat_mode = (
                            bool(next_entry.get("repeat_mode"))
                            if isinstance(next_entry, dict)
                            else False
                        )
                        continue
                    if scheduler_mode == "flow_graph":
                        executed_node_ids.add(node_state["node_id"])
                    started_at = datetime.now(timezone.utc).isoformat()
                    node_state["node_status"] = "running"
                    node_state["started_at"] = started_at
                    node_state["input_snapshot"] = deepcopy(
                        executable_node.get("node_config", {})
                        if isinstance(executable_node.get("node_config"), dict)
                        else {}
                    )
                    if not isinstance(node_state.get("runtime_order"), int):
                        node_state["runtime_order"] = runtime_execution_order_counter
                        runtime_execution_order_counter += 1
                    event_log.append(
                        {
                            "event_kind": "node.started",
                            "recorded_at": started_at,
                            "session_id": session_id,
                            "node_id": node_state["node_id"],
                        }
                    )
                    publish_live_update(
                        "runtime.node",
                        {
                            "session_id": session_id,
                            "node_id": node_state["node_id"],
                            "node_status": node_state["node_status"],
                            "started_at": node_state["started_at"],
                            "completed_at": node_state.get("completed_at"),
                            "output": node_state.get("output"),
                            "error": node_state.get("error"),
                        },
                    )
                    resource_status = executable_node.get("resource_status")
                    if resource_status != "enabled":
                        completed_at = datetime.now(timezone.utc).isoformat()
                        error_code = (
                            "resource_disabled" if resource_status == "disabled" else "resource_missing"
                        )
                        node_state["node_status"] = "failed"
                        node_state["completed_at"] = completed_at
                        node_state["error"] = {
                            "error_code": error_code,
                            "message": (
                                f"required resource is {resource_status}: "
                                f"{executable_node.get('resolved_resource_id') or executable_node.get('node_kind')}"
                            ),
                            "resource_id": executable_node.get("resolved_resource_id"),
                        }
                        failed_node_ids.append(node_state["node_id"])
                        session_status = "failed"
                        failure_reason = error_code
                        event_log.append(
                            {
                                "event_kind": "diagnostic.raised",
                                "recorded_at": completed_at,
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                                "node_kind": executable_node.get("node_kind"),
                                "severity": "error",
                                "message": (
                                    f"required resource is {resource_status}: "
                                    f"{executable_node.get('resolved_resource_id') or executable_node.get('node_kind')}"
                                ),
                                "error_code": error_code,
                            }
                        )
                        event_log.append(
                            {
                                "event_kind": "node.failed",
                                "recorded_at": completed_at,
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                            "error_code": error_code,
                        }
                    )
                        publish_live_update(
                            "runtime.node",
                            {
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                                "node_status": node_state["node_status"],
                                "started_at": node_state["started_at"],
                                "completed_at": node_state["completed_at"],
                                "output": node_state.get("output"),
                                "error": node_state.get("error"),
                            },
                        )
                        break
                    completed_at = datetime.now(timezone.utc).isoformat()
                    try:
                        self._inject_runtime_data_edge_inputs(
                            executable_node=executable_node,
                            runtime_context=runtime_context,
                            data_edges_by_target=data_edges_by_target,
                        )
                        node_output = self._execute_runtime_plan_node(
                            executable_node=executable_node,
                            runtime_context=runtime_context,
                            executor_registry=executor_registry,
                        )
                    except Exception as exc:
                        node_output = self._build_runtime_executor_exception_output(
                            executable_node=executable_node,
                            exc=exc,
                        )
                    node_state["output"] = node_output
                    if (
                        isinstance(node_output, dict)
                        and node_output.get("status") == "failed"
                    ):
                        error_code = node_output.get("error_code") or "runtime.node_failed"
                        node_state["node_status"] = "failed"
                        node_state["completed_at"] = completed_at
                        node_error = {
                            "error_code": error_code,
                            "message": node_output.get("message", "runtime node failed"),
                        }
                        if "exception_type" in node_output:
                            node_error["exception_type"] = node_output["exception_type"]
                        node_state["error"] = node_error
                        failed_node_ids.append(node_state["node_id"])
                        session_status = "failed"
                        failure_reason = error_code
                        event_log.append(
                            {
                                "event_kind": "diagnostic.raised",
                                "recorded_at": completed_at,
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                                "node_kind": executable_node.get("node_kind"),
                                "severity": "error",
                                "message": node_output.get("message", "runtime node failed"),
                                "error_code": error_code,
                            }
                        )
                        event_log.append(
                            {
                                "event_kind": "node.failed",
                                "recorded_at": completed_at,
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                            "error_code": error_code,
                        }
                    )
                        publish_live_update(
                            "runtime.node",
                            {
                                "session_id": session_id,
                                "node_id": node_state["node_id"],
                                "node_status": node_state["node_status"],
                                "started_at": node_state["started_at"],
                                "completed_at": node_state["completed_at"],
                                "output": node_state.get("output"),
                                "error": node_state.get("error"),
                            },
                        )
                        break
                    node_state["node_status"] = "completed"
                    node_state["completed_at"] = completed_at
                    completed_node_ids.append(node_state["node_id"])
                    event_log.append(
                        {
                            "event_kind": "node.completed",
                            "recorded_at": completed_at,
                            "session_id": session_id,
                            "node_id": node_state["node_id"],
                        }
                    )
                    publish_live_update(
                        "runtime.node",
                        {
                            "session_id": session_id,
                            "node_id": node_state["node_id"],
                            "node_status": node_state["node_status"],
                            "started_at": node_state["started_at"],
                            "completed_at": node_state["completed_at"],
                            "output": node_state.get("output"),
                            "error": node_state.get("error"),
                        },
                    )
                    next_program_counter = program_counter + 1
                    node_kind = executable_node.get("node_kind")
                    if scheduler_mode == "flow_graph":
                        if node_kind == "control.foreach":
                            loop_body_index, loop_exit_index = self._resolve_runtime_foreach_targets(
                                executable_node=executable_node,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                            )
                            loop_result = self._execute_runtime_foreach_body(
                                foreach_node=executable_node,
                                foreach_output=node_output,
                                loop_body_index=loop_body_index,
                                loop_exit_index=loop_exit_index,
                                executable_nodes=executable_nodes,
                                node_states=node_states,
                                node_index_by_id=node_index_by_id,
                                control_edges_by_source=control_edges_by_source,
                                event_log=event_log,
                                session_id=session_id,
                                runtime_context=runtime_context,
                                executor_registry=executor_registry,
                                completed_node_ids=completed_node_ids,
                                failed_node_ids=failed_node_ids,
                                max_execution_steps=MAX_RUNTIME_EXECUTION_STEPS - execution_step_count,
                                allow_propagation=False,
                            )
                            execution_step_count += loop_result.get("execution_step_count", 0)
                            if loop_result["status"] == "failed":
                                session_status = "failed"
                                failure_reason = loop_result["failure_reason"]
                                break
                            node_state["output"] = {
                                **node_output,
                                "iteration_count": loop_result["iteration_count"],
                            }
                            runtime_context.node_outputs[executable_node["node_id"]] = node_state["output"]
                            next_flow_index = loop_result.get("next_program_counter")
                            if (
                                isinstance(next_flow_index, int)
                                and 0 <= next_flow_index < len(executable_nodes)
                            ):
                                self._enqueue_runtime_flow_graph_node(
                                    pending_node_entries=pending_node_entries,
                                    queued_node_ids=queued_node_ids,
                                    executed_node_ids=executed_node_ids,
                                    executable_nodes=executable_nodes,
                                    node_index=next_flow_index,
                                    repeat_mode=repeat_mode,
                                )
                        elif node_kind == "control.if":
                            self._queue_runtime_if_successors(
                                executable_node=executable_node,
                                runtime_context=runtime_context,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.switch":
                            self._queue_runtime_switch_successors(
                                executable_node=executable_node,
                                runtime_context=runtime_context,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.parallel_fork":
                            self._queue_runtime_parallel_fork_successors(
                                executable_node=executable_node,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.join":
                            self._queue_runtime_join_successors(
                                executable_node=executable_node,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.while":
                            self._queue_runtime_while_successors(
                                executable_node=executable_node,
                                runtime_context=runtime_context,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.retry":
                            self._queue_runtime_retry_successors(
                                executable_node=executable_node,
                                runtime_context=runtime_context,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                retry_state_by_node_id=retry_state_by_node_id,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.failover":
                            self._queue_runtime_failover_successors(
                                executable_node=executable_node,
                                runtime_context=runtime_context,
                                control_edges_by_source=control_edges_by_source,
                                node_index_by_id=node_index_by_id,
                                node_kind_by_id=node_kind_by_id,
                                control_edges_by_target=control_edges_by_target,
                                join_state_by_node_id=join_state_by_node_id,
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                event_log=event_log,
                                session_id=session_id,
                            )
                        elif node_kind == "control.jump_to_step":
                            jump_result = node_output if isinstance(node_output, dict) else {}
                            if jump_result.get("jump_executed") is True:
                                jump_target_index = self._resolve_runtime_jump_target_index(
                                    executable_node=executable_node,
                                    jump_output=jump_result,
                                    node_index_by_id=node_index_by_id,
                                )
                                if jump_target_index is None:
                                    node_state["node_status"] = "failed"
                                    node_state["error"] = {
                                        "error_code": "control.jump_target_missing",
                                        "message": "jump target node was not found",
                                    }
                                    failed_node_ids.append(node_state["node_id"])
                                    session_status = "failed"
                                    failure_reason = "control.jump_target_missing"
                                    event_log.append(
                                        {
                                            "event_kind": "node.failed",
                                            "recorded_at": completed_at,
                                            "session_id": session_id,
                                            "node_id": node_state["node_id"],
                                            "error_code": "control.jump_target_missing",
                                        }
                                    )
                                    break
                                self._enqueue_runtime_flow_graph_node(
                                    pending_node_entries=pending_node_entries,
                                    queued_node_ids=queued_node_ids,
                                    executed_node_ids=executed_node_ids,
                                    executable_nodes=executable_nodes,
                                    node_index=jump_target_index,
                                    repeat_mode=True,
                                )
                            else:
                                queue_control_edges(
                                    source_node_id=executable_node["node_id"],
                                    source_port_id=None,
                                    repeat_mode_value=False,
                                )
                        else:
                            queue_control_edges(
                                source_node_id=executable_node["node_id"],
                                source_port_id=None,
                                repeat_mode_value=repeat_mode,
                            )
                        next_entry = pending_node_entries.pop(0) if pending_node_entries else None
                        if isinstance(next_entry, dict):
                            dispatched_node_index = next_entry.get("node_index")
                            if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                                dispatched_node = executable_nodes[dispatched_node_index]
                                dispatched_at = datetime.now(timezone.utc).isoformat()
                                event_log.append(
                                    {
                                        "event_kind": "token.dispatched",
                                        "recorded_at": dispatched_at,
                                        "session_id": session_id,
                                        "node_id": dispatched_node["node_id"],
                                        "node_kind": dispatched_node.get("node_kind"),
                                        "repeat_mode": bool(next_entry.get("repeat_mode")),
                                    }
                                )
                                event_log.append(
                                    {
                                        "event_kind": "node.ready",
                                        "recorded_at": dispatched_at,
                                        "session_id": session_id,
                                        "node_id": dispatched_node["node_id"],
                                        "node_kind": dispatched_node.get("node_kind"),
                                    }
                                )
                        program_counter = (
                            int(next_entry["node_index"])
                            if isinstance(next_entry, dict)
                            else -1
                        )
                        repeat_mode = (
                            bool(next_entry.get("repeat_mode"))
                            if isinstance(next_entry, dict)
                            else False
                        )
                        continue
                    if node_kind == "control.foreach":
                        loop_body_index, loop_exit_index = self._resolve_runtime_foreach_targets(
                            executable_node=executable_node,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                        )
                        loop_result = self._execute_runtime_foreach_body(
                            foreach_node=executable_node,
                            foreach_output=node_output,
                            loop_body_index=loop_body_index,
                            loop_exit_index=loop_exit_index,
                            executable_nodes=executable_nodes,
                            node_states=node_states,
                            node_index_by_id=node_index_by_id,
                            control_edges_by_source=control_edges_by_source,
                            event_log=event_log,
                            session_id=session_id,
                            runtime_context=runtime_context,
                            executor_registry=executor_registry,
                            completed_node_ids=completed_node_ids,
                            failed_node_ids=failed_node_ids,
                            max_execution_steps=MAX_RUNTIME_EXECUTION_STEPS - execution_step_count,
                            allow_propagation=False,
                        )
                        execution_step_count += loop_result.get("execution_step_count", 0)
                        if loop_result["status"] == "failed":
                            session_status = "failed"
                            failure_reason = loop_result["failure_reason"]
                            break
                        next_program_counter = loop_result["next_program_counter"]
                        node_state["output"] = {
                            **node_output,
                            "iteration_count": loop_result["iteration_count"],
                        }
                        runtime_context.node_outputs[executable_node["node_id"]] = node_state["output"]
                    elif node_kind == "control.jump_to_step":
                        jump_result = node_output if isinstance(node_output, dict) else {}
                        if jump_result.get("jump_executed") is True:
                            jump_target_index = self._resolve_runtime_jump_target_index(
                                executable_node=executable_node,
                                jump_output=jump_result,
                                node_index_by_id=node_index_by_id,
                            )
                            if jump_target_index is None:
                                node_state["node_status"] = "failed"
                                node_state["error"] = {
                                    "error_code": "control.jump_target_missing",
                                    "message": "jump target node was not found",
                                }
                                failed_node_ids.append(node_state["node_id"])
                                session_status = "failed"
                                failure_reason = "control.jump_target_missing"
                                event_log.append(
                                    {
                                        "event_kind": "node.failed",
                                        "recorded_at": completed_at,
                                        "session_id": session_id,
                                        "node_id": node_state["node_id"],
                                        "error_code": "control.jump_target_missing",
                                    }
                                )
                                break
                            next_program_counter = jump_target_index
                    program_counter = next_program_counter
            finally:
                runtime_context.close()

            completed_at = datetime.now(timezone.utc).isoformat()
            runtime_session = dict(session["runtime_session"])
            runtime_session["status"] = session_status
            runtime_session["completed_at"] = completed_at
            runtime_session["completed_node_count"] = len(completed_node_ids)
            runtime_session["failed_node_count"] = len(failed_node_ids)
            skipped_node_ids = [
                item["node_id"]
                for item in node_states
                if item.get("node_status") == "pending"
            ]
            for skipped_node_id in skipped_node_ids:
                skipped_node = next(
                    (
                        item
                        for item in executable_nodes
                        if item.get("node_id") == skipped_node_id
                    ),
                    None,
                )
                event_log.append(
                    {
                        "event_kind": "node.skipped",
                        "recorded_at": completed_at,
                        "session_id": session_id,
                        "node_id": skipped_node_id,
                        "node_kind": skipped_node.get("node_kind")
                        if isinstance(skipped_node, dict)
                        else None,
                        "reason": "unreachable",
                    }
                )
            unreachable_node_ids = (
                list(skipped_node_ids)
                if scheduler_mode == "flow_graph"
                else []
            )
            result = {
                "status": "succeeded" if session_status == "completed" else "failed",
                "completed_node_ids": completed_node_ids,
                "failed_node_ids": failed_node_ids,
                "skipped_node_ids": skipped_node_ids,
                "unreachable_node_ids": unreachable_node_ids,
                "finished_at": completed_at,
                "outputs": dict(runtime_context.node_outputs),
                "variables": dict(runtime_context.variables),
            }
            if failure_reason is not None:
                result["failure_reason"] = failure_reason
                event_log.append(
                    {
                        "event_kind": "session.failed",
                        "recorded_at": completed_at,
                        "session_id": session_id,
                        "failure_reason": failure_reason,
                    }
                )
            else:
                event_log.append(
                    {
                        "event_kind": "session.completed",
                        "recorded_at": completed_at,
                        "session_id": session_id,
                        "unreachable_node_ids": unreachable_node_ids,
                    }
                )
            sessions[target_index] = {
                **session,
                "runtime_session": runtime_session,
                "node_states": node_states,
                "event_log": event_log,
                "debug_snapshot": self._build_runtime_debug_snapshot(
                    scheduler_mode=scheduler_mode,
                    pending_node_entries=pending_node_entries,
                    queued_node_ids=queued_node_ids,
                    executed_node_ids_in_order=completed_node_ids,
                    join_state_by_node_id=join_state_by_node_id,
                    retry_state_by_node_id=retry_state_by_node_id,
                    executable_nodes=executable_nodes,
                    current_program_counter=None,
                    current_repeat_mode=repeat_mode,
                ),
                "diagnostic_events": [
                    item
                    for item in event_log
                    if item.get("event_kind") == "diagnostic.raised"
                ],
                "execution_summary": self._build_runtime_execution_summary(
                    runtime_session=runtime_session,
                    node_states=node_states,
                    event_log=event_log,
                    diagnostic_events=[
                        item
                        for item in event_log
                        if item.get("event_kind") == "diagnostic.raised"
                    ],
                    result=result,
                ),
                "result": result,
            }
            current_state["runtime_sessions"] = sessions
            execution_history = self._extract_execution_history(current_state)
            runtime_run_record = {
                "session_id": session_id,
                "status": runtime_session["status"],
                "graph_model_id": session["runtime_plan"]["graph_model_id"],
                "started_at": runtime_session["started_at"],
                "completed_at": runtime_session["completed_at"],
                "completed_node_count": runtime_session["completed_node_count"],
                "failed_node_count": runtime_session["failed_node_count"],
            }
            if failure_reason is not None:
                runtime_run_record["failure_reason"] = failure_reason
            execution_history["runtime_runs"] = [
                item
                for item in execution_history["runtime_runs"]
                if item.get("session_id") != session_id
            ]
            execution_history["runtime_runs"].insert(0, runtime_run_record)
            execution_history["runtime_runs"] = execution_history["runtime_runs"][
                :MAX_RUNTIME_SESSION_HISTORY
            ]
            current_state["execution_history"] = execution_history
            return current_state

        try:
            self._state = self._state_store.mutate(mutation)
            session_document = self.get_runtime_session(session_id=session_id)
            self._runtime_stream_broker.publish_snapshot(
                session_id,
                self._build_runtime_stream_terminal_payload(
                    session_id=session_id,
                    session_document=session_document,
                ),
            )
            terminal_event_name = (
                "runtime.completed"
                if session_document["runtime_session"]["status"] == "completed"
                else "runtime.failed"
            )
            self._runtime_stream_broker.publish_event(
                session_id,
                terminal_event_name,
                self._build_runtime_stream_terminal_payload(
                    session_id=session_id,
                    session_document=session_document,
                ),
            )
            return {
                "status": session_document["runtime_session"]["status"],
                **session_document,
            }
        finally:
            with self._runtime_execution_lock:
                self._runtime_execution_threads.pop(session_id, None)
            self._runtime_stream_broker.close_session(session_id)

    def _execute_runtime_plan_node(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
    ) -> dict:
        try:
            if executable_node.get("node_kind") == "call_blueprint":
                return self._execute_call_blueprint_node(
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                    executor_registry=executor_registry,
                )
            if executable_node.get("node_kind") == "graph.call_subgraph":
                return self._execute_call_subgraph_node(
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                    executor_registry=executor_registry,
                )
            if executable_node.get("resource_type") == "custom_node_graph":
                return self._execute_custom_node_graph_resource(
                    executable_node=executable_node,
                    runtime_context=runtime_context,
                    executor_registry=executor_registry,
                )
            if executable_node.get("resource_type") == "user_component":
                component_graph = executable_node.get("component_source_graph_document")
                if not isinstance(component_graph, dict):
                    return self._record_runtime_node_output(
                        runtime_context=runtime_context,
                        executable_node=executable_node,
                        output={
                            "status": "failed",
                            "node_id": executable_node["node_id"],
                            "error_code": "component.graph_missing",
                            "message": "user component source graph document is missing",
                        },
                    )
                node_config = executable_node.get("node_config")
                if not isinstance(node_config, dict):
                    node_config = {}
                raw_inputs = self._resolve_runtime_component_inputs(
                    executable_node=executable_node,
                    node_config=node_config,
                )
                if raw_inputs is not None and not isinstance(raw_inputs, dict):
                    return self._record_runtime_node_output(
                        runtime_context=runtime_context,
                        executable_node=executable_node,
                        output={
                            "status": "failed",
                            "node_id": executable_node["node_id"],
                            "error_code": "component.input_mapping_invalid",
                            "message": "component node_config.inputs must be an object mapping",
                        },
                    )
                raw_outputs = node_config.get("outputs")
                if raw_outputs is not None and not isinstance(raw_outputs, dict):
                    return self._record_runtime_node_output(
                        runtime_context=runtime_context,
                        executable_node=executable_node,
                        output={
                            "status": "failed",
                            "node_id": executable_node["node_id"],
                            "error_code": "component.output_mapping_invalid",
                            "message": "component node_config.outputs must be an object mapping",
                        },
                    )
                return self._execute_component_call(
                    executable_node=executable_node,
                    component_graph=component_graph,
                    resource_id=executable_node.get("resolved_resource_id"),
                    runtime_context=runtime_context,
                    executor_registry=executor_registry,
                    inputs=raw_inputs if isinstance(raw_inputs, dict) else {},
                    output_mapping=raw_outputs,
                    call_kind="user_component",
                )
            return execute_runtime_node(executable_node, runtime_context, executor_registry)
        except Exception as exc:
            return self._build_runtime_executor_exception_output(
                executable_node=executable_node,
                exc=exc,
            )

    def _execute_custom_node_graph_resource(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
    ) -> dict:
        component_graph = executable_node.get("component_source_graph_document")
        resource_id = executable_node.get("resolved_resource_id")
        resource_key = executable_node.get("resource_key")
        resource_ref = resource_id or resource_key or executable_node.get("node_kind")
        if not isinstance(component_graph, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "custom_node_graph.graph_missing",
                    "message": f"custom node graph source graph document is missing: {resource_ref}",
                },
            )
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        raw_inputs = self._resolve_runtime_component_inputs(
            executable_node=executable_node,
            node_config=node_config,
        )
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "custom_node_graph.input_mapping_invalid",
                    "message": "custom node graph node_config.inputs must be an object mapping",
                },
            )
        raw_outputs = node_config.get("outputs")
        if raw_outputs is not None and not isinstance(raw_outputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "custom_node_graph.output_mapping_invalid",
                    "message": "custom node graph node_config.outputs must be an object mapping",
                },
            )
        result = self._execute_component_call(
            executable_node=executable_node,
            component_graph=component_graph,
            resource_id=resource_ref,
            runtime_context=runtime_context,
            executor_registry=executor_registry,
            inputs=raw_inputs if isinstance(raw_inputs, dict) else {},
            output_mapping=raw_outputs,
            call_kind="custom_node_graph",
        )
        if result.get("status") == "failed":
            error_code = result.get("error_code")
            if error_code == "component.input_mapping_invalid":
                result["error_code"] = "custom_node_graph.input_mapping_invalid"
            elif error_code == "component.output_mapping_invalid":
                result["error_code"] = "custom_node_graph.output_mapping_invalid"
            elif error_code == "component.recursive_call_detected":
                result["error_code"] = "custom_node_graph.recursive_call_detected"
            elif error_code == "component.call_depth_exceeded":
                result["error_code"] = "custom_node_graph.call_depth_exceeded"
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result
        result["custom_node_graph_id"] = resource_ref
        runtime_context.node_outputs[executable_node["node_id"]] = result
        return result

    def _build_runtime_executor_exception_output(
        self,
        *,
        executable_node: dict,
        exc: Exception,
    ) -> dict:
        return {
            "status": "failed",
            "node_id": executable_node["node_id"],
            "error_code": "runtime.executor_exception",
            "message": str(exc),
            "exception_type": type(exc).__name__,
        }

    def _record_runtime_node_output(
        self,
        *,
        runtime_context: RuntimeContext,
        executable_node: dict,
        output: dict,
    ) -> dict:
        runtime_context.node_outputs[executable_node["node_id"]] = output
        return output

    def _resolve_runtime_port_semantic_slot(
        self,
        *,
        executable_node: dict,
        port_id: str | None,
        direction: str | None = None,
    ) -> str | None:
        if not isinstance(port_id, str) or not port_id.strip():
            return None
        normalized_port_id = port_id.strip()
        for port in executable_node.get("ports", []):
            if not isinstance(port, dict):
                continue
            candidate_port_id = port.get("port_id")
            if not isinstance(candidate_port_id, str) or candidate_port_id.strip() != normalized_port_id:
                continue
            if direction is not None and port.get("direction") != direction:
                continue
            semantic_slot = port.get("semantic_slot")
            if isinstance(semantic_slot, str) and semantic_slot.strip():
                return semantic_slot.strip()
            return None
        return None

    def _build_runtime_component_output_payload(
        self,
        *,
        executable_node: dict,
        component_result: dict,
        mapped_outputs: dict[str, object],
    ) -> dict:
        result = {
            "status": "succeeded",
            "node_id": executable_node["node_id"],
            "mapped_outputs": dict(mapped_outputs),
        }
        child_variables = component_result.get("variables", {})
        if isinstance(child_variables, dict):
            for key, value in child_variables.items():
                if isinstance(key, str) and key.strip():
                    result[key.strip()] = value
        output_ports = executable_node.get("ports")
        if isinstance(output_ports, list):
            for port in output_ports:
                if not isinstance(port, dict):
                    continue
                if port.get("direction") != "output" or port.get("relation_layer") != "data":
                    continue
                port_id = port.get("port_id")
                semantic_slot = port.get("semantic_slot")
                if not isinstance(port_id, str) or not port_id.strip():
                    continue
                candidate_keys = self._derive_runtime_output_binding_keys(
                    from_port_id=port_id,
                    semantic_slot=semantic_slot,
                )
                resolved_value = None
                found = False
                for key in candidate_keys:
                    if not isinstance(key, str) or not key.strip():
                        continue
                    normalized_key = key.strip()
                    if isinstance(child_variables, dict) and normalized_key in child_variables:
                        resolved_value = child_variables[normalized_key]
                        found = True
                        break
                    if normalized_key in mapped_outputs:
                        resolved_value = mapped_outputs[normalized_key]
                        found = True
                        break
                if found:
                    result[port_id.strip()] = resolved_value
                    if isinstance(semantic_slot, str) and semantic_slot.strip():
                        result.setdefault(semantic_slot.strip(), resolved_value)
                    for key in candidate_keys:
                        if isinstance(key, str) and key.strip():
                            result.setdefault(key.strip(), resolved_value)
        return result

    def _execute_call_blueprint_node(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
    ) -> dict:
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        blueprint_id = node_config.get("blueprint_id")
        if not isinstance(blueprint_id, str) or not blueprint_id.strip():
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "call_blueprint.blueprint_id_required",
                    "message": "call_blueprint requires node_config.blueprint_id",
                },
            )
        component_resource = self._find_component_resource_for_blueprint(blueprint_id.strip())
        if component_resource is None:
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "call_blueprint.blueprint_missing",
                    "message": f"blueprint was not found: {blueprint_id.strip()}",
                },
            )
        if component_resource.get("enabled") is not True:
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "call_blueprint.blueprint_disabled",
                    "message": f"blueprint is disabled: {blueprint_id.strip()}",
                },
            )
        component_graph = component_resource.get("source_graph_document")
        if not isinstance(component_graph, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "call_blueprint.graph_missing",
                    "message": f"blueprint graph is missing: {blueprint_id.strip()}",
                },
            )
        raw_inputs = self._resolve_runtime_component_inputs(
            executable_node=executable_node,
            node_config=node_config,
        )
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "component.input_mapping_invalid",
                    "message": "call_blueprint node_config.inputs must be an object mapping",
                },
            )
        raw_outputs = node_config.get("outputs")
        if raw_outputs is not None and not isinstance(raw_outputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "component.output_mapping_invalid",
                    "message": "call_blueprint node_config.outputs must be an object mapping",
                },
            )
        result = self._execute_component_call(
            executable_node=executable_node,
            component_graph=component_graph,
            resource_id=component_resource["resource_id"],
            runtime_context=runtime_context,
            executor_registry=executor_registry,
            inputs=raw_inputs if isinstance(raw_inputs, dict) else {},
            output_mapping=raw_outputs,
            call_kind="call_blueprint",
        )
        if result.get("status") == "succeeded":
            result["blueprint_id"] = blueprint_id.strip()
        return result

    def _execute_call_subgraph_node(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
    ) -> dict:
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        subgraph_id = node_config.get("subgraph_id")
        if not isinstance(subgraph_id, str) or not subgraph_id.strip():
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.subgraph_id_required",
                    "message": "graph.call_subgraph requires node_config.subgraph_id",
                },
            )
        subgraph_resource = self._find_subgraph_resource(subgraph_id.strip())
        if subgraph_resource is None:
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.subgraph_missing",
                    "message": f"subgraph was not found: {subgraph_id.strip()}",
                },
            )
        if subgraph_resource.get("enabled") is not True:
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.subgraph_disabled",
                    "message": f"subgraph is disabled: {subgraph_id.strip()}",
                },
            )
        component_graph = subgraph_resource.get("source_graph_document")
        if not isinstance(component_graph, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.graph_missing",
                    "message": f"subgraph graph is missing: {subgraph_id.strip()}",
                },
            )
        raw_inputs = self._resolve_runtime_component_inputs(
            executable_node=executable_node,
            node_config=node_config,
        )
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.input_mapping_invalid",
                    "message": "graph.call_subgraph node_config.inputs must be an object mapping",
                },
            )
        raw_outputs = node_config.get("outputs")
        if raw_outputs is not None and not isinstance(raw_outputs, dict):
            return self._record_runtime_node_output(
                runtime_context=runtime_context,
                executable_node=executable_node,
                output={
                    "status": "failed",
                    "node_id": executable_node["node_id"],
                    "error_code": "subgraph.output_mapping_invalid",
                    "message": "graph.call_subgraph node_config.outputs must be an object mapping",
                },
            )
        input_schema = subgraph_resource.get("input_schema")
        if isinstance(input_schema, dict) and input_schema:
            missing_required_inputs = [
                input_name
                for input_name, input_meta in input_schema.items()
                if isinstance(input_name, str)
                and input_name.strip()
                and isinstance(input_meta, dict)
                and input_meta.get("required") is True
                and (
                    not isinstance(raw_inputs, dict)
                    or input_name.strip() not in raw_inputs
                )
            ]
            if missing_required_inputs:
                return self._record_runtime_node_output(
                    runtime_context=runtime_context,
                    executable_node=executable_node,
                    output={
                        "status": "failed",
                        "node_id": executable_node["node_id"],
                        "error_code": "subgraph.input_mapping_invalid",
                        "message": (
                            "graph.call_subgraph is missing required schema inputs: "
                            + ", ".join(sorted(missing_required_inputs))
                        ),
                    },
                )
            if isinstance(raw_inputs, dict):
                invalid_typed_inputs = [
                    input_name
                    for input_name, input_meta in input_schema.items()
                    if isinstance(input_name, str)
                    and input_name.strip()
                    and input_name.strip() in raw_inputs
                    and isinstance(input_meta, dict)
                    and not self._schema_value_matches_type(
                        raw_inputs[input_name.strip()],
                        input_meta.get("type"),
                    )
                ]
                if invalid_typed_inputs:
                    return self._record_runtime_node_output(
                        runtime_context=runtime_context,
                        executable_node=executable_node,
                        output={
                            "status": "failed",
                            "node_id": executable_node["node_id"],
                            "error_code": "subgraph.input_mapping_invalid",
                            "message": (
                                "graph.call_subgraph schema input type mismatch: "
                                + ", ".join(sorted(invalid_typed_inputs))
                            ),
                        },
                    )
        output_schema = subgraph_resource.get("output_schema")
        if isinstance(output_schema, dict) and output_schema and isinstance(raw_outputs, dict):
            unknown_outputs = [
                child_name
                for child_name in raw_outputs
                if isinstance(child_name, str)
                and child_name.strip()
                and child_name.strip() not in output_schema
            ]
            if unknown_outputs:
                return self._record_runtime_node_output(
                    runtime_context=runtime_context,
                    executable_node=executable_node,
                    output={
                        "status": "failed",
                        "node_id": executable_node["node_id"],
                        "error_code": "subgraph.output_mapping_invalid",
                        "message": (
                            "graph.call_subgraph maps unknown schema outputs: "
                            + ", ".join(sorted(unknown_outputs))
                        ),
                    },
                )
        result = self._execute_component_call(
            executable_node=executable_node,
            component_graph=component_graph,
            resource_id=subgraph_resource["resource_id"],
            runtime_context=runtime_context,
            executor_registry=executor_registry,
            inputs=raw_inputs if isinstance(raw_inputs, dict) else {},
            output_mapping=raw_outputs,
            call_kind="graph.call_subgraph",
        )
        if result.get("status") == "failed":
            error_code = result.get("error_code")
            if error_code == "component.recursive_call_detected":
                result["error_code"] = "subgraph.recursive_call_detected"
            elif error_code == "component.call_depth_exceeded":
                result["error_code"] = "subgraph.call_depth_exceeded"
        if result.get("status") == "succeeded":
            mapped_outputs = result.get("mapped_outputs")
            if isinstance(mapped_outputs, dict) and isinstance(output_schema, dict) and output_schema:
                invalid_typed_outputs = [
                    parent_name
                    for child_name, parent_name in (raw_outputs or {}).items()
                    if isinstance(child_name, str)
                    and child_name.strip()
                    and isinstance(parent_name, str)
                    and parent_name.strip()
                    and parent_name.strip() in mapped_outputs
                    and child_name.strip() in output_schema
                    and not self._schema_value_matches_type(
                        mapped_outputs[parent_name.strip()],
                        output_schema[child_name.strip()].get("type"),
                    )
                ]
                if invalid_typed_outputs:
                    result["status"] = "failed"
                    result["error_code"] = "subgraph.output_mapping_invalid"
                    result["message"] = (
                        "graph.call_subgraph schema output type mismatch: "
                        + ", ".join(sorted(invalid_typed_outputs))
                    )
                    runtime_context.node_outputs[executable_node["node_id"]] = result
                    return result
            result["subgraph_id"] = subgraph_id.strip()
        return result

    def _find_component_resource_for_blueprint(self, blueprint_id: str) -> dict | None:
        for item in self._get_resource_registry():
            if item.get("resource_type") not in {"user_component", "custom_node_graph"}:
                continue
            source_graph_document = item.get("source_graph_document")
            root_metadata = (
                source_graph_document.get("root_metadata")
                if isinstance(source_graph_document, dict)
                else None
            )
            blueprint_info = (
                root_metadata.get("blueprint_info")
                if isinstance(root_metadata, dict)
                else None
            )
            legacy_blueprint_id = (
                blueprint_info.get("id")
                if isinstance(blueprint_info, dict)
                else None
            )
            if blueprint_id in {
                item.get("resource_id"),
                item.get("resource_key"),
                item.get("display_name"),
                item.get("source_graph_document_id"),
                legacy_blueprint_id,
            }:
                return item
        return None

    def _find_subgraph_resource(self, subgraph_id: str) -> dict | None:
        for item in self._get_resource_registry():
            if item.get("resource_type") not in {
                "subgraph_resource",
                "user_component",
                "custom_node_graph",
            }:
                continue
            compatibility_aliases = item.get("compatibility_aliases", [])
            if not isinstance(compatibility_aliases, list):
                compatibility_aliases = []
            if subgraph_id in {
                item.get("resource_id"),
                item.get("resource_key"),
                item.get("display_name"),
                item.get("source_graph_document_id"),
                (
                    item.get("source_graph_document")
                    .get("root_metadata", {})
                    .get("blueprint_info", {})
                    .get("id")
                    if isinstance(item.get("source_graph_document"), dict)
                    else None
                ),
                *[
                    alias.strip()
                    for alias in compatibility_aliases
                    if isinstance(alias, str) and alias.strip()
                ],
            }:
                return item
        return None

    def _execute_component_call(
        self,
        *,
        executable_node: dict,
        component_graph: dict,
        resource_id: object,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
        inputs: dict,
        output_mapping: object,
        call_kind: str,
    ) -> dict:
        resource_id_text = str(resource_id) if isinstance(resource_id, str) and resource_id else "<unknown>"
        if not isinstance(inputs, dict):
            result = {
                "status": "failed",
                "node_id": executable_node["node_id"],
                "error_code": "component.input_mapping_invalid",
                "message": "component inputs must be an object mapping",
            }
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result
        if output_mapping is not None and not isinstance(output_mapping, dict):
            result = {
                "status": "failed",
                "node_id": executable_node["node_id"],
                "error_code": "component.output_mapping_invalid",
                "message": "component outputs must be an object mapping",
            }
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result
        call_stack = self._get_component_call_stack(runtime_context)
        if resource_id_text in call_stack:
            result = {
                "status": "failed",
                "node_id": executable_node["node_id"],
                "error_code": "component.recursive_call_detected",
                "message": f"recursive component call detected: {resource_id_text}",
                "component_call_stack": [*call_stack, resource_id_text],
            }
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result
        if len(call_stack) >= MAX_COMPONENT_CALL_DEPTH:
            result = {
                "status": "failed",
                "node_id": executable_node["node_id"],
                "error_code": "component.call_depth_exceeded",
                "message": f"component call depth exceeded: {MAX_COMPONENT_CALL_DEPTH}",
                "component_call_stack": call_stack,
            }
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result

        next_call_stack = [*call_stack, resource_id_text]
        component_result = self._execute_component_graph_runtime(
            graph_model=component_graph,
            inputs=self._resolve_component_inputs(inputs, runtime_context),
            parent_runtime_context=runtime_context,
            executor_registry=executor_registry,
            component_call_stack=next_call_stack,
        )
        if component_result.get("status") != "succeeded":
            result = {
                "status": "failed",
                "node_id": executable_node["node_id"],
                "error_code": component_result.get("error_code", "component.execution_failed"),
                "message": component_result.get("message", "component execution failed"),
                "component_result": component_result,
                "component_call_stack": component_result.get("component_call_stack", next_call_stack),
            }
            runtime_context.node_outputs[executable_node["node_id"]] = result
            return result
        mapped_outputs: dict[str, object] = {}
        child_variables = component_result.get("variables", {})
        if isinstance(output_mapping, dict) and isinstance(child_variables, dict):
            for child_name, parent_name in output_mapping.items():
                if (
                    isinstance(child_name, str)
                    and child_name.strip()
                    and isinstance(parent_name, str)
                    and parent_name.strip()
                ):
                    value = child_variables.get(child_name.strip())
                    runtime_context.variables[parent_name.strip()] = value
                    mapped_outputs[parent_name.strip()] = value
        result = self._build_runtime_component_output_payload(
            executable_node=executable_node,
            component_result=component_result,
            mapped_outputs=mapped_outputs,
        )
        result.update(
            {
                "call_kind": call_kind,
                "resource_id": resource_id,
                "component_graph_model_id": component_graph.get("graph_model_id"),
                "component_call_stack": next_call_stack,
                "executed_node_ids": component_result.get("executed_node_ids", []),
                "component_result": component_result,
            }
        )
        runtime_context.node_outputs[executable_node["node_id"]] = result
        return result

    def _execute_component_graph_runtime(
        self,
        *,
        graph_model: dict,
        inputs: dict[str, object],
        parent_runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
        component_call_stack: list[str],
    ) -> dict:
        try:
            graph = GraphModel.model_validate(graph_model)
        except ValidationError as exc:
            return {
                "status": "failed",
                "error_code": "component.graph_invalid",
                "message": f"component graph is invalid: {exc.errors()[0]['loc']}",
            }
        runtime_plan = self._build_runtime_plan(graph)
        executable_nodes = [dict(item) for item in runtime_plan["executable_nodes"]]
        node_states = [
            {
                "node_id": node["node_id"],
                "node_status": "pending",
                "started_at": None,
                "completed_at": None,
                "input_snapshot": None,
                "output": None,
                "error": None,
            }
            for node in executable_nodes
        ]
        node_index_by_id = {
            item["node_id"]: index for index, item in enumerate(executable_nodes)
        }
        data_edges_by_target = self._build_runtime_data_edges_by_target(
            runtime_plan.get("relation_edges", [])
        )
        control_edges_by_source: dict[str, list[dict]] = {}
        for edge in runtime_plan.get("relation_edges", []):
            if edge.get("relation_layer") == "control":
                source_id = edge.get("from_node_id")
                if isinstance(source_id, str):
                    control_edges_by_source.setdefault(source_id, []).append(dict(edge))

        child_context = RuntimeContext(
            project_directory=parent_runtime_context.project_directory,
            workspace_root=parent_runtime_context.workspace_root,
        )
        child_context.browser_runtime = parent_runtime_context.browser_runtime
        child_context.variables.update(inputs)
        child_context.flow_runtime["component_call_stack"] = list(component_call_stack)
        completed_node_ids: list[str] = []
        failed_node_ids: list[str] = []
        event_log: list[dict] = []
        has_control_edges = bool(control_edges_by_source)
        explicit_entry_node_ids = [
            item
            for item in runtime_plan.get("entry_node_ids", [])
            if isinstance(item, str) and item in node_index_by_id
        ]
        inferred_entry_node_ids = [
            item
            for item in runtime_plan.get("start_node_ids", [])
            if isinstance(item, str) and item in node_index_by_id
        ]
        scheduler_mode = runtime_plan.get("scheduler_mode")
        if scheduler_mode == "flow_graph" and explicit_entry_node_ids:
            component_scheduler_mode = "flow_graph"
            initial_entry_node_ids = explicit_entry_node_ids
        elif has_control_edges and inferred_entry_node_ids:
            component_scheduler_mode = "flow_graph"
            initial_entry_node_ids = inferred_entry_node_ids
        elif has_control_edges and executable_nodes:
            component_scheduler_mode = "flow_graph"
            initial_entry_node_ids = [executable_nodes[0]["node_id"]]
        else:
            component_scheduler_mode = "legacy_sequence"
            initial_entry_node_ids = []

        join_state_by_node_id: dict[str, dict[str, object]] = {}
        retry_state_by_node_id: dict[str, dict[str, object]] = {}
        pending_node_entries: list[dict[str, object]] = []
        queued_node_ids: set[str] = set()
        executed_node_ids: set[str] = set()
        control_edges_by_target = self._build_runtime_relation_edges_by_target(
            relation_edges=runtime_plan.get("relation_edges", []),
            relation_layer="control",
        )
        node_kind_by_id = {
            item["node_id"]: item.get("node_kind") for item in executable_nodes
        }

        def queue_control_edge(edge: dict, *, repeat_mode_value: bool) -> None:
            self._queue_runtime_control_edge_with_wait_all(
                edge=edge,
                repeat_mode_value=repeat_mode_value,
                control_edges_by_source=control_edges_by_source,
                control_edges_by_target=control_edges_by_target,
                node_index_by_id=node_index_by_id,
                node_kind_by_id=node_kind_by_id,
                join_state_by_node_id=join_state_by_node_id,
                pending_node_entries=pending_node_entries,
                queued_node_ids=queued_node_ids,
                executed_node_ids=executed_node_ids,
                executable_nodes=executable_nodes,
                event_log=event_log,
                session_id="component-runtime",
            )

        def queue_control_edges(
            *,
            source_node_id: str,
            source_port_id: str | None,
            repeat_mode_value: bool,
        ) -> None:
            for edge in control_edges_by_source.get(source_node_id, []):
                if source_port_id is not None and edge.get("from_port_id") not in {
                    None,
                    source_port_id,
                }:
                    continue
                queue_control_edge(edge, repeat_mode_value=repeat_mode_value)

        if component_scheduler_mode == "flow_graph":
            for entry_node_id in initial_entry_node_ids:
                entry_index = node_index_by_id.get(entry_node_id)
                if entry_index is not None:
                    self._enqueue_runtime_flow_graph_node(
                        pending_node_entries=pending_node_entries,
                        queued_node_ids=queued_node_ids,
                        executed_node_ids=executed_node_ids,
                        executable_nodes=executable_nodes,
                        node_index=entry_index,
                        repeat_mode=False,
                        event_log=event_log,
                        session_id="component-runtime",
                    )
            next_entry = pending_node_entries.pop(0) if pending_node_entries else None
            if isinstance(next_entry, dict):
                dispatched_node_index = next_entry.get("node_index")
                if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                    dispatched_node = executable_nodes[dispatched_node_index]
                    dispatched_at = datetime.now(timezone.utc).isoformat()
                    event_log.append(
                        {
                            "event_kind": "token.dispatched",
                            "recorded_at": dispatched_at,
                            "session_id": "component-runtime",
                            "node_id": dispatched_node["node_id"],
                            "node_kind": dispatched_node.get("node_kind"),
                            "repeat_mode": bool(next_entry.get("repeat_mode")),
                        }
                    )
                    event_log.append(
                        {
                            "event_kind": "node.ready",
                            "recorded_at": dispatched_at,
                            "session_id": "component-runtime",
                            "node_id": dispatched_node["node_id"],
                            "node_kind": dispatched_node.get("node_kind"),
                        }
                    )
            program_counter = (
                int(next_entry["node_index"])
                if isinstance(next_entry, dict)
                else -1
            )
            repeat_mode = (
                bool(next_entry.get("repeat_mode"))
                if isinstance(next_entry, dict)
                else False
            )
        else:
            program_counter = 0
            repeat_mode = False
        execution_step_count = 0
        try:
            while 0 <= program_counter < len(executable_nodes):
                if execution_step_count >= MAX_RUNTIME_EXECUTION_STEPS:
                    return {
                        "status": "failed",
                        "error_code": "component.execution_step_limit_exceeded",
                        "message": "component execution step limit exceeded",
                        "executed_node_ids": completed_node_ids,
                        "outputs": dict(child_context.node_outputs),
                        "variables": dict(child_context.variables),
                    }
                execution_step_count += 1
                node_state = node_states[program_counter]
                executable_node = executable_nodes[program_counter]
                if (
                    component_scheduler_mode == "flow_graph"
                    and repeat_mode is not True
                    and node_state["node_id"] in executed_node_ids
                ):
                    next_entry = pending_node_entries.pop(0) if pending_node_entries else None
                    if isinstance(next_entry, dict):
                        dispatched_node_index = next_entry.get("node_index")
                        if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                            dispatched_node = executable_nodes[dispatched_node_index]
                            dispatched_at = datetime.now(timezone.utc).isoformat()
                            event_log.append(
                                {
                                    "event_kind": "token.dispatched",
                                    "recorded_at": dispatched_at,
                                    "session_id": "component-runtime",
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                    "repeat_mode": bool(next_entry.get("repeat_mode")),
                                }
                            )
                            event_log.append(
                                {
                                    "event_kind": "node.ready",
                                    "recorded_at": dispatched_at,
                                    "session_id": "component-runtime",
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                }
                            )
                    program_counter = (
                        int(next_entry["node_index"])
                        if isinstance(next_entry, dict)
                        else -1
                    )
                    repeat_mode = (
                        bool(next_entry.get("repeat_mode"))
                        if isinstance(next_entry, dict)
                        else False
                    )
                    continue
                if component_scheduler_mode == "flow_graph":
                    executed_node_ids.add(node_state["node_id"])
                started_at = datetime.now(timezone.utc).isoformat()
                node_state["node_status"] = "running"
                node_state["started_at"] = started_at
                node_state["input_snapshot"] = deepcopy(
                    executable_node.get("node_config", {})
                    if isinstance(executable_node.get("node_config"), dict)
                    else {}
                )
                event_log.append(
                    {
                        "event_kind": "node.started",
                        "recorded_at": started_at,
                        "session_id": "component-runtime",
                        "node_id": node_state["node_id"],
                    }
                )
                if executable_node.get("resource_status") != "enabled":
                    error_code = (
                        "resource_disabled"
                        if executable_node.get("resource_status") == "disabled"
                        else "resource_missing"
                    )
                    failed_node_ids.append(node_state["node_id"])
                    completed_at = datetime.now(timezone.utc).isoformat()
                    node_state["node_status"] = "failed"
                    node_state["completed_at"] = completed_at
                    node_state["error"] = {
                        "error_code": error_code,
                        "message": (
                            f"required resource is {executable_node.get('resource_status')}: "
                            f"{executable_node.get('resolved_resource_id') or executable_node.get('node_kind')}"
                        ),
                    }
                    event_log.append(
                        {
                            "event_kind": "diagnostic.raised",
                            "recorded_at": completed_at,
                            "session_id": "component-runtime",
                            "node_id": node_state["node_id"],
                            "node_kind": executable_node.get("node_kind"),
                            "severity": "error",
                            "message": (
                                f"required resource is {executable_node.get('resource_status')}: "
                                f"{executable_node.get('resolved_resource_id') or executable_node.get('node_kind')}"
                            ),
                            "error_code": error_code,
                        }
                    )
                    event_log.append(
                        {
                            "event_kind": "node.failed",
                            "recorded_at": completed_at,
                            "session_id": "component-runtime",
                            "node_id": node_state["node_id"],
                            "error_code": error_code,
                        }
                    )
                    return {
                        "status": "failed",
                        "error_code": error_code,
                        "message": (
                            f"required resource is {executable_node.get('resource_status')}: "
                            f"{executable_node.get('resolved_resource_id') or executable_node.get('node_kind')}"
                        ),
                        "executed_node_ids": completed_node_ids,
                        "failed_node_ids": failed_node_ids,
                        "outputs": dict(child_context.node_outputs),
                        "variables": dict(child_context.variables),
                        "event_log": event_log,
                    }
                self._inject_runtime_data_edge_inputs(
                    executable_node=executable_node,
                    runtime_context=child_context,
                    data_edges_by_target=data_edges_by_target,
                )
                node_output = self._execute_runtime_plan_node(
                    executable_node=executable_node,
                    runtime_context=child_context,
                    executor_registry=executor_registry,
                )
                completed_at = datetime.now(timezone.utc).isoformat()
                node_state["output"] = node_output
                if isinstance(node_output, dict) and node_output.get("status") == "failed":
                    failed_node_ids.append(node_state["node_id"])
                    node_state["node_status"] = "failed"
                    node_state["completed_at"] = completed_at
                    node_state["error"] = {
                        "error_code": node_output.get("error_code") or "runtime.node_failed",
                        "message": node_output.get("message", "runtime node failed"),
                    }
                    if "exception_type" in node_output:
                        node_state["error"]["exception_type"] = node_output["exception_type"]
                    event_log.append(
                        {
                            "event_kind": "diagnostic.raised",
                            "recorded_at": completed_at,
                            "session_id": "component-runtime",
                            "node_id": node_state["node_id"],
                            "node_kind": executable_node.get("node_kind"),
                            "severity": "error",
                            "message": node_output.get("message", "runtime node failed"),
                            "error_code": node_output.get("error_code") or "runtime.node_failed",
                        }
                    )
                    event_log.append(
                        {
                            "event_kind": "node.failed",
                            "recorded_at": completed_at,
                            "session_id": "component-runtime",
                            "node_id": node_state["node_id"],
                            "error_code": node_output.get("error_code") or "runtime.node_failed",
                        }
                    )
                    return {
                        "status": "failed",
                        "error_code": node_output.get("error_code") or "runtime.node_failed",
                        "message": node_output.get("message", "runtime node failed"),
                        "component_call_stack": node_output.get(
                            "component_call_stack",
                            component_call_stack,
                        ),
                        "executed_node_ids": completed_node_ids,
                        "failed_node_ids": failed_node_ids,
                        "outputs": dict(child_context.node_outputs),
                        "variables": dict(child_context.variables),
                        "event_log": event_log,
                    }
                node_state["node_status"] = "completed"
                node_state["completed_at"] = completed_at
                completed_node_ids.append(node_state["node_id"])
                event_log.append(
                    {
                        "event_kind": "node.completed",
                        "recorded_at": completed_at,
                        "session_id": "component-runtime",
                        "node_id": node_state["node_id"],
                    }
                )
                next_program_counter = program_counter + 1
                node_kind = executable_node.get("node_kind")
                if component_scheduler_mode == "flow_graph":
                    if node_kind == "control.foreach":
                        loop_body_index, loop_exit_index = self._resolve_runtime_foreach_targets(
                            executable_node=executable_node,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                        )
                        loop_result = self._execute_runtime_foreach_body(
                            foreach_node=executable_node,
                            foreach_output=node_output,
                            loop_body_index=loop_body_index,
                            loop_exit_index=loop_exit_index,
                            executable_nodes=executable_nodes,
                            node_states=node_states,
                            node_index_by_id=node_index_by_id,
                            control_edges_by_source=control_edges_by_source,
                            event_log=event_log,
                            session_id="component-runtime",
                            runtime_context=child_context,
                            executor_registry=executor_registry,
                            completed_node_ids=completed_node_ids,
                            failed_node_ids=failed_node_ids,
                            max_execution_steps=MAX_RUNTIME_EXECUTION_STEPS - execution_step_count,
                            allow_propagation=False,
                        )
                        execution_step_count += loop_result.get("execution_step_count", 0)
                        if loop_result["status"] == "failed":
                            return {
                                "status": "failed",
                                "error_code": loop_result["failure_reason"],
                                "message": loop_result["failure_reason"],
                                "executed_node_ids": completed_node_ids,
                                "failed_node_ids": failed_node_ids,
                                "outputs": dict(child_context.node_outputs),
                                "variables": dict(child_context.variables),
                                "component_call_stack": component_call_stack,
                            }
                        node_state["output"] = {
                            **node_output,
                            "iteration_count": loop_result["iteration_count"],
                        }
                        child_context.node_outputs[executable_node["node_id"]] = node_state["output"]
                        next_flow_index = loop_result.get("next_program_counter")
                        if (
                            isinstance(next_flow_index, int)
                            and 0 <= next_flow_index < len(executable_nodes)
                        ):
                            self._enqueue_runtime_flow_graph_node(
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                node_index=next_flow_index,
                                repeat_mode=repeat_mode,
                                event_log=event_log,
                                session_id="component-runtime",
                                source_node_id=executable_node["node_id"],
                            )
                    elif node_kind == "control.if":
                        self._queue_runtime_if_successors(
                            executable_node=executable_node,
                            runtime_context=child_context,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            control_edges_by_target=control_edges_by_target,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.switch":
                        self._queue_runtime_switch_successors(
                            executable_node=executable_node,
                            runtime_context=child_context,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.parallel_fork":
                        self._queue_runtime_parallel_fork_successors(
                            executable_node=executable_node,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            control_edges_by_target=control_edges_by_target,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.join":
                        self._queue_runtime_join_successors(
                            executable_node=executable_node,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            control_edges_by_target=control_edges_by_target,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.while":
                        self._queue_runtime_while_successors(
                            executable_node=executable_node,
                            runtime_context=child_context,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            control_edges_by_target=control_edges_by_target,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.retry":
                        self._queue_runtime_retry_successors(
                            executable_node=executable_node,
                            runtime_context=child_context,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            retry_state_by_node_id=retry_state_by_node_id,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.failover":
                        self._queue_runtime_failover_successors(
                            executable_node=executable_node,
                            runtime_context=child_context,
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            node_kind_by_id=node_kind_by_id,
                            join_state_by_node_id=join_state_by_node_id,
                            pending_node_entries=pending_node_entries,
                            queued_node_ids=queued_node_ids,
                            executed_node_ids=executed_node_ids,
                            executable_nodes=executable_nodes,
                            event_log=event_log,
                            session_id="component-runtime",
                        )
                    elif node_kind == "control.jump_to_step":
                        jump_result = node_output if isinstance(node_output, dict) else {}
                        if jump_result.get("jump_executed") is True:
                            jump_target_index = self._resolve_runtime_jump_target_index(
                                executable_node=executable_node,
                                jump_output=jump_result,
                                node_index_by_id=node_index_by_id,
                            )
                            if jump_target_index is None:
                                failed_node_ids.append(node_state["node_id"])
                                return {
                                    "status": "failed",
                                    "error_code": "control.jump_target_missing",
                                    "message": "jump target node was not found",
                                    "executed_node_ids": completed_node_ids,
                                    "failed_node_ids": failed_node_ids,
                                    "outputs": dict(child_context.node_outputs),
                                    "variables": dict(child_context.variables),
                                    "component_call_stack": component_call_stack,
                                }
                            self._enqueue_runtime_flow_graph_node(
                                pending_node_entries=pending_node_entries,
                                queued_node_ids=queued_node_ids,
                                executed_node_ids=executed_node_ids,
                                executable_nodes=executable_nodes,
                                node_index=jump_target_index,
                                repeat_mode=True,
                                event_log=event_log,
                                session_id="component-runtime",
                                source_node_id=executable_node["node_id"],
                            )
                        else:
                            queue_control_edges(
                                source_node_id=executable_node["node_id"],
                                source_port_id=None,
                                repeat_mode_value=False,
                            )
                    else:
                        queue_control_edges(
                            source_node_id=executable_node["node_id"],
                            source_port_id=None,
                            repeat_mode_value=repeat_mode,
                        )
                    next_entry = pending_node_entries.pop(0) if pending_node_entries else None
                    if isinstance(next_entry, dict):
                        dispatched_node_index = next_entry.get("node_index")
                        if isinstance(dispatched_node_index, int) and 0 <= dispatched_node_index < len(executable_nodes):
                            dispatched_node = executable_nodes[dispatched_node_index]
                            dispatched_at = datetime.now(timezone.utc).isoformat()
                            event_log.append(
                                {
                                    "event_kind": "token.dispatched",
                                    "recorded_at": dispatched_at,
                                    "session_id": "component-runtime",
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                    "repeat_mode": bool(next_entry.get("repeat_mode")),
                                }
                            )
                            event_log.append(
                                {
                                    "event_kind": "node.ready",
                                    "recorded_at": dispatched_at,
                                    "session_id": "component-runtime",
                                    "node_id": dispatched_node["node_id"],
                                    "node_kind": dispatched_node.get("node_kind"),
                                }
                            )
                    program_counter = (
                        int(next_entry["node_index"])
                        if isinstance(next_entry, dict)
                        else -1
                    )
                    repeat_mode = (
                        bool(next_entry.get("repeat_mode"))
                        if isinstance(next_entry, dict)
                        else False
                    )
                    continue
                if node_kind == "control.foreach":
                    loop_body_index, loop_exit_index = self._resolve_runtime_foreach_targets(
                        executable_node=executable_node,
                        control_edges_by_source=control_edges_by_source,
                        node_index_by_id=node_index_by_id,
                    )
                    loop_result = self._execute_runtime_foreach_body(
                        foreach_node=executable_node,
                        foreach_output=node_output,
                        loop_body_index=loop_body_index,
                        loop_exit_index=loop_exit_index,
                        executable_nodes=executable_nodes,
                        node_states=node_states,
                        node_index_by_id=node_index_by_id,
                        control_edges_by_source=control_edges_by_source,
                        event_log=event_log,
                        session_id="component-runtime",
                        runtime_context=child_context,
                        executor_registry=executor_registry,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        max_execution_steps=MAX_RUNTIME_EXECUTION_STEPS - execution_step_count,
                        allow_propagation=False,
                    )
                    execution_step_count += loop_result.get("execution_step_count", 0)
                    if loop_result["status"] == "failed":
                        return {
                            "status": "failed",
                            "error_code": loop_result["failure_reason"],
                            "message": loop_result["failure_reason"],
                            "executed_node_ids": completed_node_ids,
                            "failed_node_ids": failed_node_ids,
                            "outputs": dict(child_context.node_outputs),
                            "variables": dict(child_context.variables),
                        }
                    next_program_counter = loop_result["next_program_counter"]
                elif node_kind == "control.jump_to_step":
                    jump_result = node_output if isinstance(node_output, dict) else {}
                    if jump_result.get("jump_executed") is True:
                        jump_target_index = self._resolve_runtime_jump_target_index(
                            executable_node=executable_node,
                            jump_output=jump_result,
                            node_index_by_id=node_index_by_id,
                        )
                        if jump_target_index is None:
                            failed_node_ids.append(node_state["node_id"])
                            return {
                                "status": "failed",
                                "error_code": "control.jump_target_missing",
                                "message": "jump target node was not found",
                                "executed_node_ids": completed_node_ids,
                                "failed_node_ids": failed_node_ids,
                                "outputs": dict(child_context.node_outputs),
                                "variables": dict(child_context.variables),
                                "component_call_stack": component_call_stack,
                            }
                        next_program_counter = jump_target_index
                program_counter = next_program_counter
            skipped_node_ids = [
                item["node_id"]
                for item in node_states
                if item.get("node_status") == "pending"
            ]
            for skipped_node_id in skipped_node_ids:
                skipped_node = next(
                    (
                        item
                        for item in executable_nodes
                        if item.get("node_id") == skipped_node_id
                    ),
                    None,
                )
                event_log.append(
                    {
                        "event_kind": "node.skipped",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "session_id": "component-runtime",
                        "node_id": skipped_node_id,
                        "node_kind": skipped_node.get("node_kind")
                        if isinstance(skipped_node, dict)
                        else None,
                        "reason": "unreachable",
                    }
                )
            unreachable_node_ids = (
                list(skipped_node_ids)
                if component_scheduler_mode == "flow_graph"
                else []
            )
            return {
                "status": "succeeded",
                "executed_node_ids": completed_node_ids,
                "failed_node_ids": failed_node_ids,
                "skipped_node_ids": skipped_node_ids,
                "unreachable_node_ids": unreachable_node_ids,
                "outputs": dict(child_context.node_outputs),
                "variables": dict(child_context.variables),
                "component_call_stack": component_call_stack,
                "event_log": event_log,
            }
        finally:
            if child_context.browser_runtime is parent_runtime_context.browser_runtime:
                child_context.browser_runtime = {}
            child_context.close()

    def _get_component_call_stack(self, runtime_context: RuntimeContext) -> list[str]:
        call_stack = runtime_context.flow_runtime.get("component_call_stack", [])
        if not isinstance(call_stack, list):
            return []
        return [item for item in call_stack if isinstance(item, str)]

    def _resolve_component_inputs(
        self,
        inputs: dict,
        runtime_context: RuntimeContext,
    ) -> dict[str, object]:
        resolved_inputs: dict[str, object] = {}
        for name, value in inputs.items():
            if isinstance(name, str) and name.strip():
                resolved_inputs[name.strip()] = self._resolve_component_input_value(value, runtime_context)
        return resolved_inputs

    def _resolve_component_input_value(
        self,
        value: object,
        runtime_context: RuntimeContext,
    ) -> object:
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}") and len(value) > 3:
                variable_name = value[2:-1].strip()
                return runtime_context.variables.get(variable_name)
            return value
        if isinstance(value, list):
            return [
                self._resolve_component_input_value(item, runtime_context)
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: self._resolve_component_input_value(item, runtime_context)
                for key, item in value.items()
                if isinstance(key, str)
            }
        return value

    def _resolve_runtime_foreach_targets(
        self,
        *,
        executable_node: dict,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
    ) -> tuple[int | None, int | None]:
        edges = control_edges_by_source.get(executable_node["node_id"], [])
        ordered_targets = [
            edge.get("to_node_id")
            for edge in edges
            if isinstance(edge.get("to_node_id"), str) and edge.get("to_node_id") in node_index_by_id
        ]
        body_index = (
            node_index_by_id[ordered_targets[0]]
            if ordered_targets
            else None
        )
        exit_index = (
            node_index_by_id[ordered_targets[1]]
            if len(ordered_targets) > 1
            else None
        )
        return body_index, exit_index

    def _execute_runtime_foreach_body(
        self,
        *,
        foreach_node: dict,
        foreach_output: dict,
        loop_body_index: int | None,
        loop_exit_index: int | None,
        executable_nodes: list[dict],
        node_states: list[dict],
        node_index_by_id: dict[str, int],
        control_edges_by_source: dict[str, list[dict]],
        event_log: list[dict],
        session_id: str,
        runtime_context: RuntimeContext,
        executor_registry: RuntimeExecutorRegistry,
        completed_node_ids: list[str],
        failed_node_ids: list[str],
        max_execution_steps: int,
        allow_propagation: bool,
    ) -> dict:
        if loop_body_index is None:
            return {
                "status": "failed",
                "failure_reason": "control.foreach_body_missing",
            }
        items = foreach_output.get("items", [])
        if not isinstance(items, list):
            return {
                "status": "failed",
                "failure_reason": "control.foreach_items_invalid",
            }
        item_var = str(foreach_output.get("item_var") or "item")
        index_var = str(foreach_output.get("index_var") or "index")
        body_execution_step_count = 0
        implicit_exit_index: int | None = None
        for item_index, item_value in enumerate(items):
            runtime_context.variables[item_var] = item_value
            runtime_context.variables[index_var] = item_index
            current_body_index = loop_body_index
            visited_body_node_ids: set[str] = set()
            while current_body_index is not None:
                if body_execution_step_count >= max_execution_steps:
                    return {
                        "status": "failed",
                        "failure_reason": "runtime.execution_step_limit_exceeded",
                        "execution_step_count": body_execution_step_count,
                    }
                body_execution_step_count += 1
                body_node = executable_nodes[current_body_index]
                body_state = node_states[current_body_index]
                if body_node["node_id"] in visited_body_node_ids:
                    return {
                        "status": "failed",
                        "failure_reason": "control.foreach_cycle_detected",
                        "execution_step_count": body_execution_step_count,
                    }
                visited_body_node_ids.add(body_node["node_id"])
                started_at = datetime.now(timezone.utc).isoformat()
                body_state["node_status"] = "running"
                body_state["started_at"] = started_at
                event_log.append(
                    {
                        "event_kind": "node.started",
                        "recorded_at": started_at,
                        "session_id": session_id,
                        "node_id": body_state["node_id"],
                    }
                )
                try:
                    body_output = self._execute_runtime_plan_node(
                        executable_node=body_node,
                        runtime_context=runtime_context,
                        executor_registry=executor_registry,
                    )
                except Exception as exc:
                    body_output = self._build_runtime_executor_exception_output(
                        executable_node=body_node,
                        exc=exc,
                    )
                completed_at = datetime.now(timezone.utc).isoformat()
                body_state["output"] = body_output
                if isinstance(body_output, dict) and body_output.get("status") == "failed":
                    body_state["node_status"] = "failed"
                    body_state["completed_at"] = completed_at
                    body_error = {
                        "error_code": body_output.get("error_code", "runtime.node_failed"),
                        "message": body_output.get("message", "runtime node failed"),
                    }
                    if "exception_type" in body_output:
                        body_error["exception_type"] = body_output["exception_type"]
                    body_state["error"] = body_error
                    failed_node_ids.append(body_state["node_id"])
                    event_log.append(
                        {
                            "event_kind": "node.failed",
                            "recorded_at": completed_at,
                            "session_id": session_id,
                            "node_id": body_state["node_id"],
                            "error_code": body_output.get("error_code", "runtime.node_failed"),
                        }
                    )
                    return {
                        "status": "failed",
                        "failure_reason": body_output.get("error_code", "runtime.node_failed"),
                        "execution_step_count": body_execution_step_count,
                    }
                body_state["node_status"] = "completed"
                body_state["completed_at"] = completed_at
                completed_node_ids.append(body_state["node_id"])
                event_log.append(
                    {
                        "event_kind": "node.completed",
                        "recorded_at": completed_at,
                        "session_id": session_id,
                        "node_id": body_state["node_id"],
                    }
                )
                if body_node.get("node_kind") == "control.foreach":
                    nested_body_index, nested_exit_index = self._resolve_runtime_foreach_targets(
                        executable_node=body_node,
                        control_edges_by_source=control_edges_by_source,
                        node_index_by_id=node_index_by_id,
                    )
                    nested_result = self._execute_runtime_foreach_body(
                        foreach_node=body_node,
                        foreach_output=body_output,
                        loop_body_index=nested_body_index,
                        loop_exit_index=nested_exit_index,
                        executable_nodes=executable_nodes,
                        node_states=node_states,
                        node_index_by_id=node_index_by_id,
                        control_edges_by_source=control_edges_by_source,
                        event_log=event_log,
                        session_id=session_id,
                        runtime_context=runtime_context,
                        executor_registry=executor_registry,
                        completed_node_ids=completed_node_ids,
                        failed_node_ids=failed_node_ids,
                        max_execution_steps=max_execution_steps - body_execution_step_count,
                        allow_propagation=True,
                    )
                    body_execution_step_count += nested_result.get("execution_step_count", 0)
                    if nested_result["status"] == "failed":
                        return nested_result
                    body_state["output"] = {
                        **body_output,
                        "iteration_count": nested_result["iteration_count"],
                    }
                    runtime_context.node_outputs[body_node["node_id"]] = body_state["output"]
                    propagated_signal = nested_result.get("control_signal")
                    propagated_level = self._normalize_foreach_control_level(
                        nested_result.get("control_level")
                    )
                    if propagated_signal == "break":
                        if propagated_level <= 1 or not allow_propagation:
                            return {
                                "status": "succeeded",
                                "iteration_count": item_index + 1,
                                "execution_step_count": body_execution_step_count,
                                "next_program_counter": (
                                    loop_exit_index
                                    if loop_exit_index is not None
                                    else (
                                        implicit_exit_index
                                        if implicit_exit_index is not None
                                        else len(executable_nodes)
                                    )
                                ),
                            }
                        return {
                            "status": "succeeded",
                            "iteration_count": item_index + 1,
                            "execution_step_count": body_execution_step_count,
                            "next_program_counter": (
                                loop_exit_index
                                if loop_exit_index is not None
                                else (
                                    implicit_exit_index
                                    if implicit_exit_index is not None
                                    else len(executable_nodes)
                                )
                            ),
                            "control_signal": "break",
                            "control_level": propagated_level - 1,
                        }
                    if propagated_signal == "continue":
                        if propagated_level <= 1 or not allow_propagation:
                            break
                        return {
                            "status": "succeeded",
                            "iteration_count": item_index + 1,
                            "execution_step_count": body_execution_step_count,
                            "next_program_counter": (
                                loop_exit_index
                                if loop_exit_index is not None
                                else (
                                    implicit_exit_index
                                    if implicit_exit_index is not None
                                    else len(executable_nodes)
                                )
                            ),
                            "control_signal": "continue",
                            "control_level": propagated_level - 1,
                        }
                    nested_next_index = nested_result.get("next_program_counter")
                    current_body_index = (
                        nested_next_index
                        if isinstance(nested_next_index, int)
                        and 0 <= nested_next_index < len(executable_nodes)
                        else None
                    )
                    continue
                if body_output.get("break_triggered") is True:
                    break_level = self._normalize_foreach_control_level(body_output.get("level"))
                    if break_level > 1 and allow_propagation:
                        return {
                            "status": "succeeded",
                            "iteration_count": item_index + 1,
                            "execution_step_count": body_execution_step_count,
                            "next_program_counter": (
                                loop_exit_index
                                if loop_exit_index is not None
                                else (
                                    implicit_exit_index
                                    if implicit_exit_index is not None
                                    else len(executable_nodes)
                                )
                            ),
                            "control_signal": "break",
                            "control_level": break_level - 1,
                        }
                    return {
                        "status": "succeeded",
                        "iteration_count": item_index + 1,
                        "execution_step_count": body_execution_step_count,
                        "next_program_counter": (
                            loop_exit_index
                            if loop_exit_index is not None
                            else (
                                implicit_exit_index
                                if implicit_exit_index is not None
                                else len(executable_nodes)
                            )
                        ),
                    }
                if body_output.get("continue_triggered") is True:
                    continue_level = self._normalize_foreach_control_level(body_output.get("level"))
                    if continue_level > 1 and allow_propagation:
                        return {
                            "status": "succeeded",
                            "iteration_count": item_index + 1,
                            "execution_step_count": body_execution_step_count,
                            "next_program_counter": (
                                loop_exit_index
                                if loop_exit_index is not None
                                else (
                                    implicit_exit_index
                                    if implicit_exit_index is not None
                                    else len(executable_nodes)
                                )
                            ),
                            "control_signal": "continue",
                            "control_level": continue_level - 1,
                        }
                    break
                if body_output.get("end_marker") is True:
                    if implicit_exit_index is None:
                        implicit_exit_index = self._resolve_runtime_control_successor_index(
                            source_node_id=body_node["node_id"],
                            control_edges_by_source=control_edges_by_source,
                            node_index_by_id=node_index_by_id,
                            excluded_node_ids={
                                foreach_node["node_id"],
                                body_node["node_id"],
                            },
                        )
                    break
                current_body_index = self._resolve_runtime_control_successor_index(
                    source_node_id=body_node["node_id"],
                    control_edges_by_source=control_edges_by_source,
                    node_index_by_id=node_index_by_id,
                    excluded_node_ids={
                        foreach_node["node_id"],
                        executable_nodes[loop_exit_index]["node_id"] if loop_exit_index is not None else None,
                    },
                )
        next_program_counter = (
            loop_exit_index
            if loop_exit_index is not None
            else (
                implicit_exit_index
                if implicit_exit_index is not None
                else len(executable_nodes)
            )
        )
        return {
            "status": "succeeded",
            "iteration_count": len(items),
            "execution_step_count": body_execution_step_count,
            "next_program_counter": next_program_counter,
        }

    def _normalize_foreach_control_level(self, value: object) -> int:
        if isinstance(value, bool):
            return 1
        if isinstance(value, int):
            return value if value >= 1 else 1
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                parsed = int(stripped)
                return parsed if parsed >= 1 else 1
        return 1

    def _resolve_runtime_control_successor_index(
        self,
        *,
        source_node_id: str,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        excluded_node_ids: set[str | None],
    ) -> int | None:
        for edge in control_edges_by_source.get(source_node_id, []):
            target_node_id = edge.get("to_node_id")
            if not isinstance(target_node_id, str):
                continue
            if target_node_id in excluded_node_ids:
                continue
            target_index = node_index_by_id.get(target_node_id)
            if target_index is not None:
                return target_index
        return None

    def _enqueue_runtime_flow_graph_node(
        self,
        *,
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        node_index: int,
        repeat_mode: bool,
        event_log: list[dict] | None = None,
        session_id: str | None = None,
        source_node_id: str | None = None,
        source_port_id: str | None = None,
    ) -> None:
        if not (0 <= node_index < len(executable_nodes)):
            return
        node_id = executable_nodes[node_index]["node_id"]
        if repeat_mode is not True:
            if node_id in executed_node_ids or node_id in queued_node_ids:
                return
            queued_node_ids.add(node_id)
        pending_node_entries.append(
            {
                "node_index": node_index,
                "repeat_mode": repeat_mode,
            }
        )
        if event_log is not None:
            event_log.append(
                {
                    "event_kind": "token.enqueued",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "source_node_id": source_node_id,
                    "source_port_id": source_port_id,
                    "target_node_id": node_id,
                    "target_node_kind": executable_nodes[node_index].get("node_kind"),
                    "repeat_mode": repeat_mode,
                }
            )

    def _enqueue_runtime_flow_graph_successors(
        self,
        *,
        source_node_id: str,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        repeat_mode: bool,
    ) -> None:
        for edge in control_edges_by_source.get(source_node_id, []):
            target_node_id = edge.get("to_node_id")
            target_node_index = (
                node_index_by_id.get(target_node_id)
                if isinstance(target_node_id, str)
                else None
            )
            if target_node_index is None:
                continue
            self._enqueue_runtime_flow_graph_node(
                pending_node_entries=pending_node_entries,
                queued_node_ids=queued_node_ids,
                executed_node_ids=executed_node_ids,
                executable_nodes=executable_nodes,
                node_index=target_node_index,
                repeat_mode=repeat_mode,
            )

    def _resolve_runtime_node_ports(self, executable_node: dict) -> dict[str, dict]:
        ports = executable_node.get("ports")
        if not isinstance(ports, list):
            return {}
        result: dict[str, dict] = {}
        for port in ports:
            if not isinstance(port, dict):
                continue
            port_id = port.get("port_id")
            if not isinstance(port_id, str) or not port_id.strip():
                continue
            result[port_id.strip()] = port
        return result

    def _build_control_port_aliases(
        self,
        *,
        port_id: str | None,
        semantic_slot: str | None,
        direction: str | None,
    ) -> set[str]:
        aliases: set[str] = set()
        if isinstance(port_id, str) and port_id.strip():
            normalized_port_id = port_id.strip()
            aliases.add(normalized_port_id)
            if normalized_port_id in {"in", "out"}:
                aliases.add("control")
        if isinstance(semantic_slot, str) and semantic_slot.strip():
            normalized_slot = semantic_slot.strip()
            aliases.add(normalized_slot)
            stripped_slot = normalized_slot
            for prefix in ("in.", "out.", "in:", "out:"):
                if stripped_slot.startswith(prefix):
                    stripped_slot = stripped_slot[len(prefix):].strip()
                    break
            if stripped_slot:
                aliases.add(stripped_slot)
                if stripped_slot == "control" and direction in {"input", "output"}:
                    aliases.add("in" if direction == "input" else "out")
        return aliases

    def _control_port_matches_expected(
        self,
        *,
        port_id: str | None,
        semantic_slot: str | None,
        direction: str | None,
        expected: str,
    ) -> bool:
        aliases = self._build_control_port_aliases(
            port_id=port_id,
            semantic_slot=semantic_slot,
            direction=direction,
        )
        if expected in {"in", "out"}:
            if "control" in aliases:
                return True
            return any(
                alias == expected
                or alias.startswith(f"{expected}.")
                or alias.startswith(f"{expected}:")
                for alias in aliases
            )
        return expected in aliases

    def _count_control_ports_with_prefix(
        self,
        *,
        ports: list,
        prefix: str,
        direction: str | None = None,
    ) -> int:
        prefix_variants = {prefix}
        if ":" in prefix:
            prefix_variants.add(prefix.replace(":", ".", 1))
        if "." in prefix:
            prefix_variants.add(prefix.replace(".", ":", 1))
        count = 0
        for port in ports:
            port_direction = getattr(port, "direction", None)
            if direction is not None and port_direction != direction:
                continue
            aliases = self._build_control_port_aliases(
                port_id=getattr(port, "port_id", None),
                semantic_slot=getattr(port, "semantic_slot", None),
                direction=port_direction,
            )
            if any(
                alias.startswith(candidate_prefix)
                for alias in aliases
                for candidate_prefix in prefix_variants
            ):
                count += 1
        return count

    def _count_control_ports_with_semantic_prefix(
        self,
        *,
        ports: list,
        prefix: str,
        direction: str | None = None,
    ) -> int:
        count = 0
        for port in ports:
            port_direction = getattr(port, "direction", None)
            if direction is not None and port_direction != direction:
                continue
            semantic_slot = getattr(port, "semantic_slot", None)
            if isinstance(semantic_slot, str) and semantic_slot.strip():
                normalized_slot = semantic_slot.strip()
                if normalized_slot.startswith(prefix):
                    count += 1
        return count

    def _resolve_graph_port_by_reference(
        self,
        *,
        node,
        port_id: str | None,
        direction: str | None = None,
    ):
        if node is None or not isinstance(port_id, str) or not port_id.strip():
            return None
        expected = port_id.strip()
        for port in getattr(node, "ports", []):
            if self._control_port_matches_expected(
                port_id=getattr(port, "port_id", None),
                semantic_slot=getattr(port, "semantic_slot", None),
                direction=getattr(port, "direction", None),
                expected=expected,
            ):
                if direction is None or getattr(port, "direction", None) == direction:
                    return port
        return None

    def _derive_runtime_output_binding_keys(
        self,
        *,
        from_port_id: str,
        semantic_slot: object,
    ) -> list[str]:
        normalized_port_id = from_port_id.strip()
        candidate_keys: list[str] = [normalized_port_id]
        if ":" in normalized_port_id:
            suffix = normalized_port_id.split(":", 1)[1].strip()
            if suffix:
                candidate_keys.append(suffix)
        if "." in normalized_port_id:
            suffix = normalized_port_id.rsplit(".", 1)[-1].strip()
            if suffix:
                candidate_keys.append(suffix)
        if normalized_port_id.startswith("out."):
            candidate_keys.append(normalized_port_id[4:].strip())
        if normalized_port_id.startswith("out:"):
            candidate_keys.append(normalized_port_id[4:].strip())
        if isinstance(semantic_slot, str) and semantic_slot.strip():
            normalized_slot = semantic_slot.strip()
            candidate_keys.append(normalized_slot)
            slot_suffix = normalized_slot
            if normalized_slot.startswith("out."):
                slot_suffix = normalized_slot[4:].strip()
            elif normalized_slot.startswith("out:"):
                slot_suffix = normalized_slot[4:].strip()
            if slot_suffix:
                candidate_keys.append(slot_suffix)
        deduped: list[str] = []
        seen: set[str] = set()
        for key in candidate_keys:
            normalized_key = key.strip()
            if not normalized_key or normalized_key in seen:
                continue
            deduped.append(normalized_key)
            seen.add(normalized_key)
        return deduped

    def _build_runtime_data_edges_by_target(self, relation_edges: list[dict]) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for edge in relation_edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("relation_layer") != "data":
                continue
            target_node_id = edge.get("to_node_id")
            if not isinstance(target_node_id, str) or not target_node_id.strip():
                continue
            result.setdefault(target_node_id.strip(), []).append(dict(edge))
        return result

    def _build_runtime_relation_edges_by_target(
        self,
        *,
        relation_edges: list[dict],
        relation_layer: str,
    ) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for edge in relation_edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("relation_layer") != relation_layer:
                continue
            target_node_id = edge.get("to_node_id")
            if not isinstance(target_node_id, str) or not target_node_id.strip():
                continue
            result.setdefault(target_node_id.strip(), []).append(dict(edge))
        return result

    def _is_runtime_concurrent_fanout_node_kind(self, node_kind: object) -> bool:
        if not isinstance(node_kind, str) or not node_kind.strip():
            return True
        return node_kind not in {
            "control.if",
            "control.switch",
            "control.failover",
            "control.while",
            "control.retry",
            "control.jump_to_step",
        }

    def _is_runtime_exclusive_fanout_node_kind(self, node_kind: object) -> bool:
        return isinstance(node_kind, str) and node_kind in {
            "control.if",
            "control.switch",
            "control.failover",
            "control.while",
            "control.retry",
            "control.jump_to_step",
        }

    def _resolve_runtime_exclusive_control_origin(
        self,
        *,
        source_node_id: str,
        control_edges_by_source: dict[str, list[dict]],
        control_edges_by_target: dict[str, list[dict]],
        node_kind_by_id: dict[str, object],
    ) -> tuple[str, str] | None:
        current_node_id = source_node_id
        visited_node_ids: set[str] = set()
        while current_node_id not in visited_node_ids:
            visited_node_ids.add(current_node_id)
            incoming_edges = control_edges_by_target.get(current_node_id, [])
            if len(incoming_edges) != 1:
                return None
            incoming_edge = incoming_edges[0]
            upstream_node_id = incoming_edge.get("from_node_id")
            if not isinstance(upstream_node_id, str) or not upstream_node_id.strip():
                return None
            normalized_upstream_node_id = upstream_node_id.strip()
            upstream_outgoing_edges = control_edges_by_source.get(normalized_upstream_node_id, [])
            upstream_kind = node_kind_by_id.get(normalized_upstream_node_id)
            if (
                len(upstream_outgoing_edges) > 1
                and self._is_runtime_exclusive_fanout_node_kind(upstream_kind)
            ):
                branch_key = incoming_edge.get("from_port_id")
                if isinstance(branch_key, str) and branch_key.strip():
                    return normalized_upstream_node_id, branch_key.strip()
                branch_slot = incoming_edge.get("from_port_semantic_slot")
                if isinstance(branch_slot, str) and branch_slot.strip():
                    return normalized_upstream_node_id, branch_slot.strip()
                return None
            current_node_id = normalized_upstream_node_id
        return None

    def _incoming_runtime_control_edges_are_mutually_exclusive(
        self,
        *,
        incoming_control_edges: list[dict],
        control_edges_by_source: dict[str, list[dict]],
        control_edges_by_target: dict[str, list[dict]],
        node_kind_by_id: dict[str, object],
    ) -> bool:
        origins: list[tuple[str, str]] = []
        for edge in incoming_control_edges:
            if not isinstance(edge, dict):
                return False
            source_node_id = edge.get("from_node_id")
            if not isinstance(source_node_id, str) or not source_node_id.strip():
                return False
            origin = self._resolve_runtime_exclusive_control_origin(
                source_node_id=source_node_id.strip(),
                control_edges_by_source=control_edges_by_source,
                control_edges_by_target=control_edges_by_target,
                node_kind_by_id=node_kind_by_id,
            )
            if origin is None:
                return False
            origins.append(origin)
        if len(origins) < 2:
            return False
        origin_node_ids = {item[0] for item in origins}
        if len(origin_node_ids) != 1:
            return False
        return len({item[1] for item in origins}) == len(origins)

    def _resolve_runtime_parallel_fork_join_tokens(
        self,
        *,
        incoming_control_edges: list[dict],
        control_edges_by_source: dict[str, list[dict]],
        control_edges_by_target: dict[str, list[dict]],
        node_kind_by_id: dict[str, object],
    ) -> list[str]:
        if len(incoming_control_edges) <= 1:
            return []
        if self._incoming_runtime_control_edges_are_mutually_exclusive(
            incoming_control_edges=incoming_control_edges,
            control_edges_by_source=control_edges_by_source,
            control_edges_by_target=control_edges_by_target,
            node_kind_by_id=node_kind_by_id,
        ):
            return []
        tokens: list[str] = []
        seen_tokens: set[str] = set()
        for edge in incoming_control_edges:
            if not isinstance(edge, dict):
                continue
            edge_id = edge.get("edge_id")
            if isinstance(edge_id, str) and edge_id.strip():
                token = f"edge:{edge_id.strip()}"
            else:
                source_node_id = str(edge.get("from_node_id") or "").strip()
                target_node_id = str(edge.get("to_node_id") or "").strip()
                token = f"path:{source_node_id}:{target_node_id}:{len(tokens)}"
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            tokens.append(token)
        return sorted(tokens) if len(tokens) > 1 else []

    def _resolve_runtime_parallel_fork_branch_token(
        self,
        *,
        source_node_id: str,
        control_edges_by_source: dict[str, list[dict]],
        control_edges_by_target: dict[str, list[dict]],
        node_kind_by_id: dict[str, object],
    ) -> str | None:
        current_node_id = source_node_id
        visited_node_ids: set[str] = set()
        while current_node_id not in visited_node_ids:
            visited_node_ids.add(current_node_id)
            incoming_edges = control_edges_by_target.get(current_node_id, [])
            if len(incoming_edges) > 1:
                candidate_tokens: list[str] = []
                seen_tokens: set[str] = set()
                for incoming_edge in incoming_edges:
                    upstream_node_id = incoming_edge.get("from_node_id")
                    if not isinstance(upstream_node_id, str) or not upstream_node_id.strip():
                        return None
                    token = self._resolve_runtime_parallel_fork_branch_token(
                        source_node_id=upstream_node_id.strip(),
                        control_edges_by_source=control_edges_by_source,
                        control_edges_by_target=control_edges_by_target,
                        node_kind_by_id=node_kind_by_id,
                    )
                    if not isinstance(token, str) or not token.strip():
                        return None
                    normalized_token = token.strip()
                    if normalized_token in seen_tokens:
                        continue
                    seen_tokens.add(normalized_token)
                    candidate_tokens.append(normalized_token)
                if len(candidate_tokens) == 1:
                    return candidate_tokens[0]
                return None
            if len(incoming_edges) != 1:
                return None
            incoming_edge = incoming_edges[0]
            upstream_node_id = incoming_edge.get("from_node_id")
            if not isinstance(upstream_node_id, str) or not upstream_node_id.strip():
                return None
            normalized_upstream_node_id = upstream_node_id.strip()
            if node_kind_by_id.get(normalized_upstream_node_id) == "control.parallel_fork":
                branch_port_id = incoming_edge.get("from_port_id")
                return branch_port_id.strip() if isinstance(branch_port_id, str) and branch_port_id.strip() else None
            upstream_outgoing_edges = control_edges_by_source.get(normalized_upstream_node_id, [])
            if (
                len(upstream_outgoing_edges) > 1
                and self._is_runtime_concurrent_fanout_node_kind(
                    node_kind_by_id.get(normalized_upstream_node_id)
                )
            ):
                edge_id = incoming_edge.get("edge_id")
                if isinstance(edge_id, str) and edge_id.strip():
                    return f"edge:{edge_id.strip()}"
                branch_port_id = incoming_edge.get("from_port_id")
                if isinstance(branch_port_id, str) and branch_port_id.strip():
                    return f"path:{normalized_upstream_node_id}:{branch_port_id.strip()}:{current_node_id}"
                return f"path:{normalized_upstream_node_id}:{current_node_id}"
            current_node_id = normalized_upstream_node_id
        return None

    def _resolve_runtime_data_edge_value(
        self,
        *,
        edge: dict,
        runtime_context: RuntimeContext,
    ) -> object:
        source_node_id = edge.get("from_node_id")
        if not isinstance(source_node_id, str) or not source_node_id.strip():
            return None
        source_output = runtime_context.node_outputs.get(source_node_id.strip())
        if source_output is None:
            return None
        current_value: object = source_output
        from_port_id = edge.get("from_port_id")
        if isinstance(from_port_id, str) and from_port_id.strip():
            candidates = self._derive_runtime_output_binding_keys(
                from_port_id=from_port_id,
                semantic_slot=edge.get("from_port_semantic_slot"),
            )
            resolved = False
            for candidate in candidates:
                if isinstance(current_value, dict) and candidate in current_value:
                    current_value = current_value[candidate]
                    resolved = True
                    break
            if resolved is not True and isinstance(current_value, dict) and "value" in current_value:
                    current_value = current_value["value"]
        return current_value

    def _derive_runtime_input_binding_keys(
        self,
        *,
        to_port_id: str,
        semantic_slot: object,
    ) -> tuple[str | None, list[str]]:
        normalized_port_id = to_port_id.strip()
        candidate_keys = [normalized_port_id]
        primary_key: str | None = None

        if ":" in normalized_port_id:
            suffix = normalized_port_id.split(":", 1)[1].strip()
            if suffix:
                candidate_keys.append(suffix)
                if primary_key is None:
                    primary_key = suffix
        if "." in normalized_port_id:
            suffix = normalized_port_id.rsplit(".", 1)[-1].strip()
            if suffix:
                candidate_keys.append(suffix)
                if primary_key is None:
                    primary_key = suffix

        if isinstance(semantic_slot, str) and semantic_slot.strip():
            normalized_slot = semantic_slot.strip()
            candidate_keys.append(normalized_slot)
            slot_suffix = normalized_slot
            if normalized_slot.startswith("in."):
                slot_suffix = normalized_slot[3:].strip()
            elif normalized_slot.startswith("in:"):
                slot_suffix = normalized_slot[3:].strip()
            if slot_suffix:
                candidate_keys.append(slot_suffix)
                primary_key = slot_suffix

        if primary_key is None:
            primary_key = normalized_port_id

        deduped_keys: list[str] = []
        seen: set[str] = set()
        for key in candidate_keys:
            if not isinstance(key, str):
                continue
            normalized_key = key.strip()
            if not normalized_key or normalized_key in seen:
                continue
            deduped_keys.append(normalized_key)
            seen.add(normalized_key)
        return primary_key, deduped_keys

    def _inject_runtime_data_edge_inputs(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        data_edges_by_target: dict[str, list[dict]],
    ) -> None:
        runtime_inputs: dict[str, object] = {}
        runtime_component_inputs: dict[str, object] = {}
        target_node_id = executable_node.get("node_id")
        if not isinstance(target_node_id, str) or not target_node_id.strip():
            executable_node.pop("__runtime_input_overrides__", None)
            executable_node.pop("__runtime_component_input_overrides__", None)
            return
        target_ports = self._resolve_runtime_node_ports(executable_node)
        for edge in data_edges_by_target.get(target_node_id.strip(), []):
            to_port_id = edge.get("to_port_id")
            if not isinstance(to_port_id, str) or not to_port_id.strip():
                continue
            port_meta = target_ports.get(to_port_id.strip(), {})
            semantic_slot = port_meta.get("semantic_slot")
            primary_key, candidate_keys = self._derive_runtime_input_binding_keys(
                to_port_id=to_port_id,
                semantic_slot=semantic_slot,
            )
            value = self._resolve_runtime_data_edge_value(edge=edge, runtime_context=runtime_context)
            for key in candidate_keys:
                if isinstance(key, str) and key.strip():
                    runtime_inputs[key.strip()] = deepcopy(value)
            if isinstance(primary_key, str) and primary_key.strip():
                runtime_component_inputs[primary_key.strip()] = deepcopy(value)
        if runtime_inputs:
            executable_node["__runtime_input_overrides__"] = runtime_inputs
        else:
            executable_node.pop("__runtime_input_overrides__", None)
        if runtime_component_inputs:
            executable_node["__runtime_component_input_overrides__"] = runtime_component_inputs
        else:
            executable_node.pop("__runtime_component_input_overrides__", None)

    def _resolve_runtime_component_inputs(
        self,
        *,
        executable_node: dict,
        node_config: dict,
    ) -> object:
        raw_inputs = node_config.get("inputs")
        component_input_overrides = executable_node.get("__runtime_component_input_overrides__")
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            return raw_inputs
        merged_inputs = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
        if isinstance(component_input_overrides, dict):
            for key, value in component_input_overrides.items():
                if isinstance(key, str) and key.strip():
                    merged_inputs[key.strip()] = value
        return merged_inputs

    def _collect_graph_node_connected_input_names(
        self,
        *,
        graph_model: GraphModel,
        node,
    ) -> set[str]:
        target_node_id = getattr(node, "node_id", None)
        if not isinstance(target_node_id, str) or not target_node_id.strip():
            return set()
        port_map = {
            port.port_id: port
            for port in getattr(node, "ports", [])
            if isinstance(getattr(port, "port_id", None), str) and port.port_id.strip()
        }
        connected_input_names: set[str] = set()
        for edge in graph_model.edges:
            if edge.relation_layer != "data" or edge.to_node_id != target_node_id:
                continue
            if not isinstance(edge.to_port_id, str) or not edge.to_port_id.strip():
                continue
            port_meta = port_map.get(edge.to_port_id.strip())
            semantic_slot = port_meta.semantic_slot if port_meta is not None else None
            primary_key, _ = self._derive_runtime_input_binding_keys(
                to_port_id=edge.to_port_id,
                semantic_slot=semantic_slot,
            )
            if isinstance(primary_key, str) and primary_key.strip():
                connected_input_names.add(primary_key.strip())
        return connected_input_names

    def _resolve_runtime_edge_target_ports(
        self,
        *,
        source_node_id: str,
        source_port_id: str | None,
        control_edges_by_source: dict[str, list[dict]],
        source_node: dict | None = None,
    ) -> list[dict]:
        source_aliases = self._build_control_port_aliases(
            port_id=source_port_id,
            semantic_slot=self._resolve_runtime_port_semantic_slot(
                executable_node=source_node or {},
                port_id=source_port_id,
                direction="output",
            ),
            direction="output",
        )
        matched_edges: list[dict] = []
        for edge in control_edges_by_source.get(source_node_id, []):
            if source_port_id is not None:
                edge_from_port_id = edge.get("from_port_id")
                if edge_from_port_id in {None, source_port_id}:
                    matched_edges.append(edge)
                    continue
                if (
                    isinstance(source_node, dict)
                    and isinstance(edge_from_port_id, str)
                    and edge_from_port_id.strip()
                ):
                    edge_aliases = self._build_control_port_aliases(
                        port_id=edge_from_port_id,
                        semantic_slot=self._resolve_runtime_port_semantic_slot(
                            executable_node=source_node,
                            port_id=edge_from_port_id,
                            direction="output",
                        ),
                        direction="output",
                    )
                    if source_aliases.intersection(edge_aliases):
                        matched_edges.append(edge)
                continue
            matched_edges.append(edge)
        return matched_edges

    def _resolve_runtime_wait_all_tokens(
        self,
        *,
        executable_node: dict,
    ) -> list[str]:
        node_kind = executable_node.get("node_kind")
        ports = self._resolve_runtime_node_ports(executable_node)
        if node_kind in {"control.if", "control.while"}:
            return []
        if node_kind == "control.join":
            return sorted(
                port_id
                for port_id, port_meta in ports.items()
                if port_meta.get("direction") == "input"
                and (
                    (
                        isinstance(port_id, str)
                        and port_id.startswith("in:")
                    )
                    or (
                        isinstance(port_meta.get("semantic_slot"), str)
                        and (
                            port_meta.get("semantic_slot").startswith("in.branch:")
                            or port_meta.get("semantic_slot").startswith("in:")
                        )
                    )
                )
            )
        if node_kind in {"flow.start", "control.parallel_fork"}:
            return []
        control_input_ports = sorted(
            port_id
            for port_id, port_meta in ports.items()
            if port_meta.get("direction") == "input"
            and port_meta.get("relation_layer") == "control"
        )
        if len(control_input_ports) > 1:
            return control_input_ports
        return []

    def _queue_runtime_control_edge_with_wait_all(
        self,
        *,
        edge: dict,
        repeat_mode_value: bool,
        control_edges_by_source: dict[str, list[dict]],
        control_edges_by_target: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        target_node_id = edge.get("to_node_id")
        if not isinstance(target_node_id, str):
            return
        target_node_index = node_index_by_id.get(target_node_id)
        if target_node_index is None:
            return
        target_node_kind = node_kind_by_id.get(target_node_id)
        effective_repeat_mode = repeat_mode_value or target_node_kind == "control.retry"
        if target_node_kind == "control.if":
            target_port_id = edge.get("to_port_id")
            if target_port_id == "repeat":
                self._enqueue_runtime_flow_graph_node(
                    pending_node_entries=pending_node_entries,
                    queued_node_ids=queued_node_ids,
                    executed_node_ids=executed_node_ids,
                    executable_nodes=executable_nodes,
                    node_index=target_node_index,
                    repeat_mode=True,
                    event_log=event_log,
                    session_id=session_id,
                    source_node_id=edge.get("from_node_id")
                    if isinstance(edge.get("from_node_id"), str)
                    else None,
                    source_port_id=edge.get("from_port_id")
                    if isinstance(edge.get("from_port_id"), str)
                    else None,
                )
                return
            self._enqueue_runtime_flow_graph_node(
                pending_node_entries=pending_node_entries,
                queued_node_ids=queued_node_ids,
                executed_node_ids=executed_node_ids,
                executable_nodes=executable_nodes,
                node_index=target_node_index,
                repeat_mode=False,
                event_log=event_log,
                session_id=session_id,
                source_node_id=edge.get("from_node_id")
                if isinstance(edge.get("from_node_id"), str)
                else None,
                source_port_id=edge.get("from_port_id")
                if isinstance(edge.get("from_port_id"), str)
                else None,
            )
            return
        if target_node_kind == "control.while":
            target_port_id = edge.get("to_port_id")
            if target_port_id == "repeat":
                self._enqueue_runtime_flow_graph_node(
                    pending_node_entries=pending_node_entries,
                    queued_node_ids=queued_node_ids,
                    executed_node_ids=executed_node_ids,
                    executable_nodes=executable_nodes,
                    node_index=target_node_index,
                    repeat_mode=True,
                    event_log=event_log,
                    session_id=session_id,
                    source_node_id=edge.get("from_node_id")
                    if isinstance(edge.get("from_node_id"), str)
                    else None,
                    source_port_id=edge.get("from_port_id")
                    if isinstance(edge.get("from_port_id"), str)
                    else None,
                )
                return
            else:
                effective_repeat_mode = False
                self._enqueue_runtime_flow_graph_node(
                    pending_node_entries=pending_node_entries,
                    queued_node_ids=queued_node_ids,
                    executed_node_ids=executed_node_ids,
                    executable_nodes=executable_nodes,
                    node_index=target_node_index,
                    repeat_mode=False,
                    event_log=event_log,
                    session_id=session_id,
                    source_node_id=edge.get("from_node_id")
                    if isinstance(edge.get("from_node_id"), str)
                    else None,
                    source_port_id=edge.get("from_port_id")
                    if isinstance(edge.get("from_port_id"), str)
                    else None,
                )
                return
        target_node = executable_nodes[target_node_index]
        required_tokens = self._resolve_runtime_wait_all_tokens(executable_node=target_node)
        if not required_tokens and target_node_kind != "control.join":
            required_tokens = self._resolve_runtime_parallel_fork_join_tokens(
                incoming_control_edges=control_edges_by_target.get(target_node_id, []),
                control_edges_by_source=control_edges_by_source,
                control_edges_by_target=control_edges_by_target,
                node_kind_by_id=node_kind_by_id,
            )
        if required_tokens:
            join_state = join_state_by_node_id.setdefault(
                target_node_id,
                {"arrived_tokens": set(), "join_mode": "explicit" if target_node_kind == "control.join" else "implicit"},
            )
            arrived_tokens = join_state.get("arrived_tokens")
            if not isinstance(arrived_tokens, set):
                arrived_tokens = set()
                join_state["arrived_tokens"] = arrived_tokens
            token: str | None = None
            if target_node_kind == "control.join":
                to_port_id = edge.get("to_port_id")
                if isinstance(to_port_id, str) and to_port_id.strip():
                    token = to_port_id.strip()
            else:
                expects_parallel_branch_tokens = any(
                    isinstance(required_token, str)
                    and (
                        required_token.startswith("branch:")
                        or required_token.startswith("edge:")
                        or required_token.startswith("path:")
                    )
                    for required_token in required_tokens
                )
                if expects_parallel_branch_tokens:
                    edge_id = edge.get("edge_id")
                    if isinstance(edge_id, str) and edge_id.strip():
                        token = f"edge:{edge_id.strip()}"
                    else:
                        source_node_id = edge.get("from_node_id")
                        if isinstance(source_node_id, str) and source_node_id.strip():
                            token = self._resolve_runtime_parallel_fork_branch_token(
                                source_node_id=source_node_id.strip(),
                                control_edges_by_source=control_edges_by_source,
                                control_edges_by_target=control_edges_by_target,
                                node_kind_by_id=node_kind_by_id,
                            )
                if token is None:
                    to_port_id = edge.get("to_port_id")
                    if isinstance(to_port_id, str) and to_port_id.strip():
                        token = to_port_id.strip()
            if token is not None:
                arrived_tokens.add(token)
            if not all(required_token in arrived_tokens for required_token in required_tokens):
                if event_log is not None:
                    event_log.append(
                        {
                            "event_kind": "join.waiting",
                            "recorded_at": datetime.now(timezone.utc).isoformat(),
                            "session_id": session_id,
                            "node_id": target_node_id,
                            "join_mode": join_state.get("join_mode"),
                            "arrived_input_ports": sorted(arrived_tokens),
                            "required_input_ports": required_tokens,
                        }
                    )
                return
            if event_log is not None:
                event_log.append(
                    {
                        "event_kind": "join.released",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "session_id": session_id,
                        "node_id": target_node_id,
                        "join_mode": join_state.get("join_mode"),
                    }
                )
        self._enqueue_runtime_flow_graph_node(
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            node_index=target_node_index,
            repeat_mode=effective_repeat_mode,
            event_log=event_log,
            session_id=session_id,
            source_node_id=edge.get("from_node_id")
            if isinstance(edge.get("from_node_id"), str)
            else None,
            source_port_id=edge.get("from_port_id")
            if isinstance(edge.get("from_port_id"), str)
            else None,
        )

    def _queue_runtime_control_edges(
        self,
        *,
        source_node_id: str,
        source_port_id: str | None,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        repeat_mode: bool,
        event_log: list[dict] | None = None,
        session_id: str | None = None,
        source_node: dict | None = None,
    ) -> None:
        for edge in self._resolve_runtime_edge_target_ports(
            source_node_id=source_node_id,
            source_port_id=source_port_id,
            control_edges_by_source=control_edges_by_source,
            source_node=source_node,
        ):
            self._queue_runtime_control_edge_with_wait_all(
                edge=edge,
                repeat_mode_value=repeat_mode,
                control_edges_by_source=control_edges_by_source,
                control_edges_by_target=control_edges_by_target,
                node_index_by_id=node_index_by_id,
                node_kind_by_id=node_kind_by_id,
                join_state_by_node_id=join_state_by_node_id,
                pending_node_entries=pending_node_entries,
                queued_node_ids=queued_node_ids,
                executed_node_ids=executed_node_ids,
                executable_nodes=executable_nodes,
                event_log=event_log,
                session_id=session_id,
            )

    def _evaluate_runtime_control_condition(self, node_config: dict, runtime_context: RuntimeContext) -> bool:
        expression = node_config.get("expression")
        if isinstance(expression, str) and expression.strip():
            try:
                return bool(_safe_eval_expression(expression.strip(), runtime_context.variables))
            except Exception:
                return False
        condition = node_config.get("condition")
        if condition is not None:
            resolved = _resolve_value(condition, runtime_context)
            return bool(resolved)
        return False

    def _queue_runtime_if_successors(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        selected_port_id = "true" if self._evaluate_runtime_control_condition(
            executable_node.get("node_config", {}),
            runtime_context,
        ) else "false"
        if event_log is not None:
            event_log.append(
                {
                    "event_kind": "branch.selected",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": executable_node["node_id"],
                    "selected_port_id": selected_port_id,
                }
            )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=selected_port_id,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=False,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_switch_successors(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        selector = node_config.get("selector")
        if isinstance(selector, str) and selector.strip():
            normalized_selector = selector.strip()
            if normalized_selector in runtime_context.variables:
                selected_value = runtime_context.variables.get(normalized_selector)
            else:
                selected_value = _resolve_value(normalized_selector, runtime_context)
        else:
            selected_value = _resolve_value(node_config.get("value"), runtime_context)
        selected_key = str(selected_value) if selected_value is not None else ""
        matched_port_id = None
        if selected_key:
            for port_id in self._resolve_runtime_node_ports(executable_node):
                if port_id == f"case:{selected_key}":
                    matched_port_id = port_id
                    break
        if matched_port_id is None:
            matched_port_id = "default"
        if event_log is not None:
            event_log.append(
                {
                    "event_kind": "branch.selected",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": executable_node["node_id"],
                    "selected_port_id": matched_port_id,
                    "selected_value": selected_value,
                }
            )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=matched_port_id,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=False,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_parallel_fork_successors(
        self,
        *,
        executable_node: dict,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=None,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=False,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_join_successors(
        self,
        *,
        executable_node: dict,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        if event_log is not None:
            event_log.append(
                {
                    "event_kind": "join.released",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": executable_node["node_id"],
                }
            )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id="out",
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=False,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_while_successors(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        join_state_by_node_id.pop(executable_node["node_id"], None)
        loop_selected = self._evaluate_runtime_control_condition(
            executable_node.get("node_config", {}),
            runtime_context,
        )
        selected_port_id = "loop" if loop_selected else "done"
        if loop_selected:
            iteration_by_node_id = runtime_context.flow_runtime.setdefault(
                "loop_iteration_by_node_id",
                {},
            )
            if not isinstance(iteration_by_node_id, dict):
                iteration_by_node_id = {}
                runtime_context.flow_runtime["loop_iteration_by_node_id"] = iteration_by_node_id
            iteration_index = int(iteration_by_node_id.get(executable_node["node_id"], 0)) + 1
            iteration_by_node_id[executable_node["node_id"]] = iteration_index
            if event_log is not None:
                event_log.append(
                    {
                        "event_kind": "loop.iteration",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "session_id": session_id,
                        "node_id": executable_node["node_id"],
                        "iteration_index": iteration_index,
                    }
                )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=selected_port_id,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=loop_selected,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_retry_successors(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        retry_state_by_node_id: dict[str, dict[str, object]],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        state = retry_state_by_node_id.setdefault(
            executable_node["node_id"],
            {"attempts": 0},
        )
        attempts = state.get("attempts")
        if not isinstance(attempts, int):
            attempts = 0
        attempts += 1
        state["attempts"] = attempts
        max_attempts = node_config.get("max_attempts")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            max_attempts = 1
        success_expression = node_config.get("success_expression")
        if isinstance(success_expression, str) and success_expression.strip():
            try:
                succeeded = bool(
                    _safe_eval_expression(success_expression.strip(), runtime_context.variables)
                )
            except Exception:
                succeeded = False
        else:
            succeeded = attempts >= max_attempts
        should_exit = succeeded or attempts >= max_attempts
        selected_port_id = "exhausted" if should_exit else "attempt"
        if selected_port_id == "attempt" and event_log is not None:
            event_log.append(
                {
                    "event_kind": "retry.scheduled",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": executable_node["node_id"],
                    "attempt_index": attempts,
                    "max_attempts": max_attempts,
                }
            )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=selected_port_id,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=not should_exit,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _queue_runtime_failover_successors(
        self,
        *,
        executable_node: dict,
        runtime_context: RuntimeContext,
        control_edges_by_source: dict[str, list[dict]],
        node_index_by_id: dict[str, int],
        node_kind_by_id: dict[str, object],
        control_edges_by_target: dict[str, list[dict]],
        join_state_by_node_id: dict[str, dict[str, object]],
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids: set[str],
        executable_nodes: list[dict],
        event_log: list[dict] | None = None,
        session_id: str | None = None,
    ) -> None:
        node_config = executable_node.get("node_config")
        if not isinstance(node_config, dict):
            node_config = {}
        use_fallback = False
        fallback_expression = node_config.get("fallback_expression")
        if isinstance(fallback_expression, str) and fallback_expression.strip():
            try:
                use_fallback = bool(
                    _safe_eval_expression(fallback_expression.strip(), runtime_context.variables)
                )
            except Exception:
                use_fallback = False
        selected_port_id = None
        ports = self._resolve_runtime_node_ports(executable_node)
        if use_fallback:
            fallback_ports = sorted(
                port_id
                for port_id in ports
                if isinstance(port_id, str) and port_id.startswith("fallback:")
            )
            if fallback_ports:
                selected_port_id = fallback_ports[0]
            else:
                selected_port_id = "failed"
        else:
            if "primary" in ports:
                selected_port_id = "primary"
            else:
                selected_port_id = "failed"
        if use_fallback and selected_port_id is not None and event_log is not None:
            event_log.append(
                {
                    "event_kind": "failover.switched",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "node_id": executable_node["node_id"],
                    "selected_port_id": selected_port_id,
                }
            )
        self._queue_runtime_control_edges(
            source_node_id=executable_node["node_id"],
            source_port_id=selected_port_id,
            control_edges_by_source=control_edges_by_source,
            node_index_by_id=node_index_by_id,
            node_kind_by_id=node_kind_by_id,
            control_edges_by_target=control_edges_by_target,
            join_state_by_node_id=join_state_by_node_id,
            pending_node_entries=pending_node_entries,
            queued_node_ids=queued_node_ids,
            executed_node_ids=executed_node_ids,
            executable_nodes=executable_nodes,
            repeat_mode=False,
            event_log=event_log,
            session_id=session_id,
            source_node=executable_node,
        )

    def _resolve_runtime_jump_target_index(
        self,
        *,
        executable_node: dict,
        jump_output: dict,
        node_index_by_id: dict[str, int],
    ) -> int | None:
        target_node_id = jump_output.get("target_node_id")
        if isinstance(target_node_id, str) and target_node_id in node_index_by_id:
            return node_index_by_id[target_node_id]
        target_step = jump_output.get("target_step")
        if isinstance(target_step, int):
            target_index = target_step - 1
            if 0 <= target_index < len(node_index_by_id):
                return target_index
        if isinstance(target_step, str) and target_step.strip().isdigit():
            target_index = int(target_step.strip()) - 1
            if 0 <= target_index < len(node_index_by_id):
                return target_index
        legacy_step = executable_node.get("node_config", {}).get("legacy_step")
        if isinstance(legacy_step, dict):
            step_id = legacy_step.get("step_id")
            if isinstance(step_id, str) and step_id in node_index_by_id:
                return node_index_by_id[step_id]
        return None

    def save_graph_document(
        self,
        graph_document_payload: dict,
        *,
        expected_graph_document_save_revision: int | None = None,
    ) -> dict:
        self._refresh_state_from_store()
        try:
            graph_model = GraphModel.model_validate(graph_document_payload)
        except ValidationError as exc:
            raise ValueError(f"graph document payload is invalid: {exc.errors()[0]['loc']}") from exc
        graph_model, _ = self._normalize_graph_model(graph_model)
        self._persist_graph_document(
            graph_model,
            expected_graph_document_save_revision=expected_graph_document_save_revision,
        )
        self._refresh_workspace_graph_validation_snapshot()
        project_runtime = self._get_project_runtime()
        project_file_path = project_runtime.get("project_file_path")
        if isinstance(project_file_path, str) and project_file_path.strip():
            self._write_project_storage_layout(Path(project_file_path))
        return {
            "status": "saved",
            "graph_model": graph_model,
            "view": self._build_graph_document_view(graph_model),
        }

    def validate_graph_document(self, graph_document_payload: dict) -> dict:
        try:
            graph_model = GraphModel.model_validate(graph_document_payload)
        except ValidationError as exc:
            raise ValueError(f"graph document payload is invalid: {exc.errors()[0]['loc']}") from exc
        graph_model, _ = self._normalize_graph_model(graph_model)

        diagnostics = self._collect_graph_validation_diagnostics(graph_model)
        diagnostic_entries = self._materialize_graph_validation_diagnostic_entries(
            graph_model,
            diagnostics,
            diagnostic_id_prefix="graph-validate",
        )
        error_count = len(
            [entry for entry in diagnostic_entries if entry.severity in {"error", "fatal"}]
        )
        warning_count = len(
            [entry for entry in diagnostic_entries if entry.severity in {"warning", "degraded"}]
        )
        return {
            "status": "valid" if error_count == 0 else "invalid",
            "graph_model": graph_model,
            "summary": {
                "error_count": error_count,
                "warning_count": warning_count,
            },
            "diagnostics": [entry.model_dump(mode="json") for entry in diagnostic_entries],
        }

    def compile_graph_document(self, graph_document_payload: dict | None) -> dict:
        started_at = perf_counter()
        self._refresh_state_from_store()
        if graph_document_payload is None:
            graph_model = self._get_graph_document_model()
        else:
            try:
                graph_model = GraphModel.model_validate(graph_document_payload)
            except ValidationError as exc:
                raise ValueError(f"graph document payload is invalid: {exc.errors()[0]['loc']}") from exc
            graph_model, _ = self._normalize_graph_model(graph_model)
            self._persist_graph_document(graph_model)
        graph_document_meta = self._get_graph_document_meta()

        diagnostics = self._collect_graph_validation_diagnostics(graph_model)
        diagnostic_entries = self._materialize_graph_validation_diagnostic_entries(
            graph_model,
            diagnostics,
            diagnostic_id_prefix="graph-validate",
        )
        blocking_diagnostics = [
            item
            for item in diagnostics
            if self._resolve_graph_validation_diagnostic_severity(item) in {"error", "fatal"}
        ]
        if blocking_diagnostics:
            request_sequence, compilation_id = self._reserve_compile_request(
                compilation_id_prefix="graph-compile"
            )
            result = self._build_invalid_graph_compile_result(
                graph_model,
                blocking_diagnostics,
                compilation_id=compilation_id,
                duration_ms=self._resolve_duration_ms(started_at),
            )
            last_compile = self._build_last_compile_snapshot(
                status="failed",
                request_sequence=request_sequence,
                source_kind="graph_workspace",
                entry_document=graph_model.graph_model_id,
                view=result["view"],
            )
            last_compile["request_origin"] = "graph_document"
            last_compile["requested_graph_model_id"] = graph_model.graph_model_id
            last_compile["requested_graph_save_revision"] = graph_document_meta["save_revision"]
            last_compile["requested_graph_saved_at"] = graph_document_meta["saved_at"]
            self._remember_compile(last_compile)
            return result

        source_text = json.dumps(
            graph_model.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        compile_result, last_compile = self._compile_source_internal(
            source_kind="graph_workspace",
            entry_document=graph_model.graph_model_id,
            source_text=source_text,
        )
        if diagnostic_entries:
            compile_result["outcome"].diagnostic_catalog.entries.extend(diagnostic_entries)
        total_duration_ms = self._resolve_duration_ms(started_at)
        self._apply_duration_to_result(compile_result, total_duration_ms)
        last_compile["duration_ms"] = total_duration_ms
        last_compile["request_origin"] = "graph_document"
        last_compile["requested_graph_model_id"] = graph_model.graph_model_id
        last_compile["requested_graph_save_revision"] = graph_document_meta["save_revision"]
        last_compile["requested_graph_saved_at"] = graph_document_meta["saved_at"]
        self._remember_compile(last_compile)
        compile_result["request"] = {
            "compilation_id": compile_result["request"].compilation_id,
            "source_kind": "graph_workspace",
            "entry_document": graph_model.graph_model_id,
            "request_origin": "graph_document",
            "requested_graph_model_id": graph_model.graph_model_id,
            "requested_graph_save_revision": graph_document_meta["save_revision"],
            "requested_graph_saved_at": graph_document_meta["saved_at"],
            "source": {
                "kind": "graph_workspace",
                "entry_document": graph_model.graph_model_id,
                "source_text": source_text,
            },
        }
        return compile_result

    def prepare_runtime_session(self, graph_document_payload: dict | None) -> dict:
        graph_model, request_meta = self._resolve_graph_document_request(graph_document_payload)
        compile_result = self._compile_graph_document_transient(
            graph_model,
            compilation_id_prefix="runtime",
        )
        runtime_status = "ready" if compile_result["status"] == "succeeded" else "failed"
        runtime_plan = (
            self._build_runtime_plan(compile_result["outcome"].graph_model)
            if compile_result["outcome"].graph_model is not None
            and compile_result["status"] == "succeeded"
            else None
        )
        return {
            "status": runtime_status,
            "request": {
                "compilation_id": compile_result["request"]["compilation_id"],
                "request_origin": request_meta["request_origin"],
                "requested_graph_model_id": request_meta["requested_graph_model_id"],
                "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                "compile_status": compile_result["status"],
            },
            "runtime_session": {
                "session_id": f"runtime-session-{uuid.uuid4().hex[:12]}",
                "status": "prepared" if runtime_status == "ready" else "diagnostic_blocked",
                "execution_supported": False,
                "debug_snapshot": self._build_runtime_debug_snapshot(
                    scheduler_mode=runtime_plan.get("scheduler_mode") if isinstance(runtime_plan, dict) else None,
                    pending_node_entries=[],
                    queued_node_ids=set(),
                    executed_node_ids_in_order=[],
                    join_state_by_node_id={},
                    retry_state_by_node_id={},
                    executable_nodes=runtime_plan.get("executable_nodes", []) if isinstance(runtime_plan, dict) else [],
                    current_program_counter=None,
                    current_repeat_mode=False,
                ),
            },
            "runtime_plan": runtime_plan,
            "diagnostics": self._build_compilation_diagnostics_summary(compile_result),
        }

    def prepare_debug_session(self, graph_document_payload: dict | None) -> dict:
        graph_model, request_meta = self._resolve_graph_document_request(graph_document_payload)
        compile_result = self._compile_graph_document_transient(
            graph_model,
            compilation_id_prefix="debug",
        )
        debug_graph_model = compile_result["outcome"].graph_model or graph_model
        debug_status = "ready" if compile_result["status"] == "succeeded" else "failed"
        runtime_preview_plan = (
            self._build_runtime_plan(debug_graph_model)
            if compile_result["outcome"].graph_model is not None
            and compile_result["status"] == "succeeded"
            else None
        )
        return {
            "status": debug_status,
            "request": {
                "compilation_id": compile_result["request"]["compilation_id"],
                "request_origin": request_meta["request_origin"],
                "requested_graph_model_id": request_meta["requested_graph_model_id"],
                "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                "compile_status": compile_result["status"],
            },
            "debug_session": {
                "session_id": f"debug-session-{uuid.uuid4().hex[:12]}",
                "status": "prepared" if debug_status == "ready" else "diagnostic_blocked",
                "resume_supported": False,
                "breakpoint_slots": [],
            },
            "stage_timeline": [
                {
                    "stage": stage.stage,
                    "status": stage.status,
                    "diagnostic_count": stage.diagnostic_count,
                }
                for stage in compile_result["outcome"].compilation_summary.stage_outcomes
            ],
            "object_index": self._build_debug_object_index(debug_graph_model),
            "diagnostic_links": self._build_debug_diagnostic_links(compile_result),
            "runtime_preview": self._build_runtime_debug_snapshot(
                scheduler_mode=(
                    runtime_preview_plan.get("scheduler_mode")
                    if isinstance(runtime_preview_plan, dict)
                    else None
                ),
                pending_node_entries=[],
                queued_node_ids=set(),
                executed_node_ids_in_order=[],
                join_state_by_node_id={},
                retry_state_by_node_id={},
                executable_nodes=(
                    runtime_preview_plan.get("executable_nodes", [])
                    if isinstance(runtime_preview_plan, dict)
                    else []
                ),
                current_program_counter=None,
                current_repeat_mode=False,
            ),
            "runtime_preview_summary": self._build_runtime_preview_summary(
                self._build_runtime_debug_snapshot(
                    scheduler_mode=(
                        runtime_preview_plan.get("scheduler_mode")
                        if isinstance(runtime_preview_plan, dict)
                        else None
                    ),
                    pending_node_entries=[],
                    queued_node_ids=set(),
                    executed_node_ids_in_order=[],
                    join_state_by_node_id={},
                    retry_state_by_node_id={},
                    executable_nodes=(
                        runtime_preview_plan.get("executable_nodes", [])
                        if isinstance(runtime_preview_plan, dict)
                        else []
                    ),
                    current_program_counter=None,
                    current_repeat_mode=False,
                )
            ),
        }

    def start_debug_session(self, graph_document_payload: dict | None) -> dict:
        graph_model, request_meta = self._resolve_graph_document_request(graph_document_payload)
        compile_result = self._compile_graph_document_transient(
            graph_model,
            compilation_id_prefix="debug",
        )
        debug_graph_model = compile_result["outcome"].graph_model or graph_model
        runtime_preview_plan = (
            self._build_runtime_plan(debug_graph_model)
            if compile_result["outcome"].graph_model is not None
            and compile_result["status"] == "succeeded"
            else None
        )
        stage_timeline = [
            {
                "stage": stage.stage,
                "status": stage.status,
                "diagnostic_count": stage.diagnostic_count,
            }
            for stage in compile_result["outcome"].compilation_summary.stage_outcomes
        ]
        object_index = self._build_debug_object_index(debug_graph_model)
        diagnostic_links = self._build_debug_diagnostic_links(compile_result)
        if compile_result["status"] != "succeeded":
            return {
                "status": "failed",
                "request": {
                    "compilation_id": compile_result["request"]["compilation_id"],
                    "request_origin": request_meta["request_origin"],
                    "requested_graph_model_id": request_meta["requested_graph_model_id"],
                    "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                    "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                    "compile_status": compile_result["status"],
                },
                "debug_session": {
                    "session_id": None,
                    "status": "diagnostic_blocked",
                    "resume_supported": False,
                    "breakpoint_slots": [],
                },
                "stage_timeline": stage_timeline,
                "object_index": object_index,
                "diagnostic_links": diagnostic_links,
                "runtime_preview": self._build_runtime_debug_snapshot(
                    scheduler_mode=None,
                    pending_node_entries=[],
                    queued_node_ids=set(),
                    executed_node_ids_in_order=[],
                    join_state_by_node_id={},
                    retry_state_by_node_id={},
                    executable_nodes=[],
                    current_program_counter=None,
                    current_repeat_mode=False,
                ),
            }

        prepared_at = datetime.now(timezone.utc).isoformat()
        session_document = {
            "request": {
                "compilation_id": compile_result["request"]["compilation_id"],
                "request_origin": request_meta["request_origin"],
                "requested_graph_model_id": request_meta["requested_graph_model_id"],
                "requested_graph_save_revision": request_meta["requested_graph_save_revision"],
                "requested_graph_saved_at": request_meta["requested_graph_saved_at"],
                "compile_status": compile_result["status"],
            },
            "debug_session": {
                "session_id": f"debug-session-{uuid.uuid4().hex[:12]}",
                "status": "prepared",
                "resume_supported": False,
                "breakpoint_slots": [],
                "started_at": prepared_at,
                "prepared_at": prepared_at,
            },
            "stage_timeline": stage_timeline,
            "object_index": object_index,
            "diagnostic_links": diagnostic_links,
            "runtime_preview": self._build_runtime_debug_snapshot(
                scheduler_mode=(
                    runtime_preview_plan.get("scheduler_mode")
                    if isinstance(runtime_preview_plan, dict)
                    else None
                ),
                pending_node_entries=[],
                queued_node_ids=set(),
                executed_node_ids_in_order=[],
                join_state_by_node_id={},
                retry_state_by_node_id={},
                executable_nodes=(
                    runtime_preview_plan.get("executable_nodes", [])
                    if isinstance(runtime_preview_plan, dict)
                    else []
                ),
                current_program_counter=None,
                current_repeat_mode=False,
            ),
        }
        session_document["runtime_preview_summary"] = self._build_runtime_preview_summary(
            session_document["runtime_preview"]
        )
        self._remember_debug_session(session_document)
        return {
            "status": "started",
            **session_document,
        }

    def compile_source(
        self,
        *,
        source_kind: str,
        entry_document: str,
        source_text: str,
    ) -> dict:
        compile_result, last_compile = self._compile_source_internal(
            source_kind=source_kind,
            entry_document=entry_document,
            source_text=source_text,
        )
        self._remember_compile(last_compile)
        return compile_result

    def _compile_source_internal(
        self,
        *,
        source_kind: str,
        entry_document: str,
        source_text: str,
    ) -> tuple[dict, dict]:
        started_at = perf_counter()
        request_sequence, compilation_id = self._reserve_compile_request()

        if source_kind not in {
            "graph_workspace",
            "native_flow",
            "webcontrol_main_flow",
            "webcontrol_blueprint",
        }:
            outcome = CompilationOutcome(
                graph_model=None,
                compilation_summary=create_initial_summary(compilation_id),
                diagnostic_catalog=DiagnosticCatalog(
                    entries=[
                        Diagnostic(
                            diagnostic_id="unsupported-source-kind",
                            stage="parse",
                            severity="fatal",
                            category="source.unsupported_kind",
                            message=f"unsupported source kind: {source_kind}",
                        )
                    ]
                ),
            )
            outcome.compilation_summary.stage_outcomes[0].status = "failed"
            outcome.compilation_summary.stage_outcomes[0].diagnostic_count = 1
            duration_ms = self._resolve_duration_ms(started_at)
            outcome.compilation_summary.duration_ms = duration_ms
            view = self._build_compile_view(
                status="unsupported",
                outcome=outcome,
                duration_ms=duration_ms,
            )
            last_compile = self._build_last_compile_snapshot(
                status="unsupported",
                request_sequence=request_sequence,
                source_kind=source_kind,
                entry_document=entry_document,
                view=view,
            )
            return (
                {
                    "status": "unsupported",
                    "request": {
                        "compilation_id": compilation_id,
                        "source_kind": source_kind,
                        "entry_document": entry_document,
                    },
                    "outcome": outcome,
                    "view": view,
                },
                last_compile,
            )

        request = CompilationRequest(
            compilation_id=compilation_id,
            source=CompilationSource(
                kind=source_kind,
                entry_document=entry_document,
                source_text=source_text,
            ),
        )
        try:
            outcome = self._compiler.compile(request)
            status = "succeeded"
        except CompilationAbortedError as exc:
            outcome = exc.outcome
            status = exc.status

        duration_ms = self._resolve_duration_ms(started_at)
        outcome.compilation_summary.duration_ms = duration_ms
        view = self._build_compile_view(
            status=status,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        last_compile = self._build_last_compile_snapshot(
            status=status,
            request_sequence=request_sequence,
            source_kind=source_kind,
            entry_document=entry_document,
            view=view,
        )
        return (
            {
                "status": status,
                "request": request,
                "outcome": outcome,
                "view": view,
            },
            last_compile,
        )

    def _build_compile_view(
        self,
        *,
        status: str,
        outcome: CompilationOutcome,
        duration_ms: int | None,
    ) -> dict:
        graph_model = outcome.graph_model
        diagnostics = outcome.diagnostic_catalog.entries
        stage_cards = [
            {
                "stage": item.stage,
                "status": item.status,
                "diagnostic_count": item.diagnostic_count,
            }
            for item in outcome.compilation_summary.stage_outcomes
        ]
        diagnostic_groups = [
            {
                "stage": entry.stage,
                "category": entry.category,
                "severity": entry.severity,
                "count": len(
                    [
                        item
                        for item in diagnostics
                        if item.stage == entry.stage
                        and item.category == entry.category
                        and item.severity == entry.severity
                    ]
                ),
                "message": entry.message,
            }
            for entry in self._unique_diagnostic_groups(diagnostics)
        ]
        primary_diagnostic = self._select_primary_diagnostic(diagnostics)
        stage_overview = self._build_stage_overview(stage_cards)

        return {
            "status": status,
            "duration_ms": duration_ms,
            "stage_cards": stage_cards,
            "stage_overview": stage_overview,
            "diagnostic_groups": diagnostic_groups,
            "diagnostic_summary": {
                "total_count": len(diagnostics),
                "highest_severity": self._resolve_highest_severity(diagnostics),
            },
            "primary_diagnostic": (
                {
                    "stage": primary_diagnostic.stage,
                    "category": primary_diagnostic.category,
                    "severity": primary_diagnostic.severity,
                    "message": primary_diagnostic.message,
                }
                if primary_diagnostic is not None
                else None
            ),
            "graph_stats": {
                "graph_model_id": graph_model.graph_model_id if graph_model else None,
                "node_count": len(graph_model.nodes) if graph_model else 0,
                "edge_count": len(graph_model.edges) if graph_model else 0,
                "effective_diagnostic_anchor_count": (
                    len(graph_model.graph_effective_diagnostic_anchor_refs) if graph_model else 0
                ),
            },
        }

    def _unique_diagnostic_groups(self, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        seen: set[tuple[str, str, str]] = set()
        unique_entries: list[Diagnostic] = []
        for entry in diagnostics:
            key = (entry.stage, entry.category, entry.severity)
            if key in seen:
                continue
            seen.add(key)
            unique_entries.append(entry)
        return unique_entries

    def _resolve_highest_severity(self, diagnostics: list[Diagnostic]) -> str | None:
        if not diagnostics:
            return None
        return max(diagnostics, key=lambda entry: DIAGNOSTIC_SEVERITY_RANK[entry.severity]).severity

    def _select_primary_diagnostic(self, diagnostics: list[Diagnostic]) -> Diagnostic | None:
        if not diagnostics:
            return None
        return max(diagnostics, key=lambda entry: DIAGNOSTIC_SEVERITY_RANK[entry.severity])

    def _build_last_compile_snapshot(
        self,
        *,
        status: str,
        request_sequence: int,
        source_kind: str,
        entry_document: str,
        view: dict,
    ) -> dict:
        return {
            "status": status,
            "request_sequence": request_sequence,
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": view.get("duration_ms"),
            "source_kind": source_kind,
            "entry_document": entry_document,
            "stage_cards": view["stage_cards"],
            "stage_overview": view["stage_overview"],
            "diagnostic_summary": view["diagnostic_summary"],
            "primary_diagnostic": view["primary_diagnostic"],
            "graph_stats": view["graph_stats"],
        }

    def _build_stage_overview(self, stage_cards: list[dict]) -> dict:
        terminal_stage = None
        for item in stage_cards:
            if item["status"] in {"succeeded", "failed"}:
                terminal_stage = item["stage"]

        return {
            "total_stage_count": len(stage_cards),
            "succeeded_stage_count": len(
                [item for item in stage_cards if item["status"] == "succeeded"]
            ),
            "failed_stage_count": len([item for item in stage_cards if item["status"] == "failed"]),
            "terminal_stage": terminal_stage,
        }

    def _remember_compile(self, snapshot: dict) -> None:
        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            current_state["last_compile"] = snapshot
            current_state["compile_history"].insert(0, snapshot)
            if len(current_state["compile_history"]) > MAX_COMPILE_HISTORY:
                current_state["compile_history"] = current_state["compile_history"][
                    :MAX_COMPILE_HISTORY
                ]
            return current_state

        self._state = self._state_store.mutate(mutation)

    def _reserve_compile_request(self, *, compilation_id_prefix: str = "comp") -> tuple[int, str]:
        compilation_id = f"{compilation_id_prefix}-{uuid.uuid4().hex[:12]}"
        request_sequence_holder: dict[str, int] = {}

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            current_state["workbench"]["compile_counter"] += 1
            request_sequence_holder["value"] = current_state["workbench"]["compile_counter"]
            return current_state

        self._state = self._state_store.mutate(mutation)
        return request_sequence_holder["value"], compilation_id

    def _build_initial_workspace_state(
        self,
        *,
        project_name: str = "WeConduct Workspace",
        project_id: str | None = None,
        project_file_path: str | Path | None = None,
        mark_project_dirty: bool = False,
    ) -> dict:
        project_slug = project_name.strip().lower().replace(" ", "-")
        if not project_slug:
            project_slug = "weconduct-project"
        resolved_project_id = project_id or f"{project_slug}-{uuid.uuid4().hex[:8]}"
        resolved_project_file_path = (
            str(Path(project_file_path).resolve()) if project_file_path is not None else None
        )
        workspace_root = (
            str(Path(resolved_project_file_path).parent)
            if resolved_project_file_path is not None
            else str(Path(__file__).resolve().parents[3])
        )
        return {
            "workspace_state_version": WORKSPACE_STATE_VERSION,
            "workbench": {
                "host_mode": "python_core",
                "api_version": "0.4.1",
                "workspace_session_id": f"ws-{uuid.uuid4().hex[:12]}",
                "service_started_at": datetime.now(timezone.utc).isoformat(),
                "compile_counter": 0,
            },
            "project": {
                "project_id": resolved_project_id,
                "project_name": project_name,
                "project_schema_version": "project-v1",
                "project_status": "ready",
                "workspace_root": workspace_root,
                "source_of_truth": "graph_document",
                "main_graph_document_id": "graph:workspace",
                "resource_registry_revision": 0,
            },
            "project_runtime": {
                "project_file_path": resolved_project_file_path,
                "is_dirty": mark_project_dirty,
            },
            "last_compile": None,
            "compile_history": [],
            "recent_projects": [],
            "resource_registry": self._build_initial_resource_registry(),
            "editor_history": {
                "undo_stack": [],
                "redo_stack": [],
            },
            "execution_history": {
                "runtime_runs": [],
                "debug_sessions": [],
            },
            "runtime_sessions": [],
            "debug_sessions": [],
            "graph_document": create_empty_graph_model("graph:workspace", None).model_dump(),
            "graph_document_meta": {
                "save_revision": 0,
                "saved_at": None,
            },
            "graph_validation_snapshot": {
                "graph_model_id": "graph:workspace",
                "graph_document_save_revision": 0,
                "resource_registry_revision": 0,
                "status": "valid",
                "summary": {
                    "error_count": 0,
                    "warning_count": 0,
                },
                "diagnostics": [],
            },
            "pending_recovery": None,
        }

    def _build_workbench_metadata(self) -> dict:
        return {
            **dict(self._state["workbench"]),
            "workspace_state_version": self._state["workspace_state_version"],
        }

    def _build_project_metadata(self) -> dict:
        raw_project = self._state.get("project")
        if not isinstance(raw_project, dict):
            raw_project = self._build_initial_workspace_state()["project"]
        project_runtime = self._get_project_runtime()
        recent_projects = self._get_recent_projects()
        last_compile = self._state["last_compile"]
        execution_history = self._get_execution_history()
        last_runtime_run = execution_history["runtime_runs"][0] if execution_history["runtime_runs"] else None
        last_debug_session = execution_history["debug_sessions"][0] if execution_history["debug_sessions"] else None
        return {
            "loaded": True,
            "project_id": raw_project["project_id"],
            "project_name": raw_project["project_name"],
            "project_schema_version": raw_project["project_schema_version"],
            "project_status": raw_project["project_status"],
            "workspace_root": raw_project["workspace_root"],
            "source_of_truth": raw_project["source_of_truth"],
            "main_graph_document_id": raw_project["main_graph_document_id"],
            "resource_registry_revision": raw_project["resource_registry_revision"],
            "project_file_path": project_runtime["project_file_path"],
            "project_file_name": (
                Path(project_runtime["project_file_path"]).name
                if project_runtime["project_file_path"] is not None
                else None
            ),
            "is_dirty": project_runtime["is_dirty"],
            "pending_recovery": self._build_pending_recovery_metadata(),
            "recent_project_count": len(recent_projects),
            "recent_projects": recent_projects,
            "has_persisted_workspace_state": self._has_persisted_workspace_state(),
            "last_compile_status": last_compile["status"] if last_compile is not None else None,
            "last_compile_request_sequence": (
                last_compile["request_sequence"] if last_compile is not None else None
            ),
            "last_runtime_status": last_runtime_run["status"] if last_runtime_run is not None else None,
            "last_runtime_session_id": last_runtime_run["session_id"] if last_runtime_run is not None else None,
            "last_debug_status": last_debug_session["status"] if last_debug_session is not None else None,
            "last_debug_session_id": last_debug_session["session_id"] if last_debug_session is not None else None,
            "execution_overview": {
                "runtime_run_count": len(execution_history["runtime_runs"]),
                "debug_session_count": len(execution_history["debug_sessions"]),
                "runtime_status_counts": self._build_execution_status_counts(execution_history["runtime_runs"]),
                "debug_status_counts": self._build_execution_status_counts(execution_history["debug_sessions"]),
            },
        }

    def _build_capabilities_metadata(self) -> dict:
        return {
            "compiler_available": True,
            "graph_workspace_available": True,
            "runtime_available": True,
            "debug_available": True,
        }

    def _build_entrypoints_metadata(self) -> dict:
        return {
            "snapshot": "/api/workbench/snapshot",
            "compile_action": "/api/workbench/compile",
            "graph_document": "/api/workbench/graph",
            "graph_source_projection": "/api/workbench/graph/source-projection",
            "project_document": "/api/workbench/project",
            "project_documents": "/api/workbench/project/documents",
            "recent_projects": "/api/workbench/recent-projects",
            "project_new_action": "/api/workbench/project/new",
            "project_open_action": "/api/workbench/project/open",
            "project_save_action": "/api/workbench/project/save",
            "project_save_as_action": "/api/workbench/project/save-as",
            "project_convert_webcontrol_action": "/api/workbench/project/convert-webcontrol",
            "recent_project_remove_action": "/api/workbench/recent-projects/remove",
            "resources_document": "/api/workbench/resources",
            "component_library": "/api/workbench/component-library",
            "resource_import_action": "/api/workbench/resources/import",
            "resource_export_action": "/api/workbench/resources/export",
            "editor_history": "/api/workbench/editor/history",
            "editor_history_record_action": "/api/workbench/editor/history/record",
            "execution_history": "/api/workbench/execution-history",
            "runtime_sessions": "/api/workbench/runtime/sessions",
            "runtime_start_action": "/api/workbench/runtime/start",
            "debug_sessions": "/api/workbench/debug/sessions",
            "debug_start_action": "/api/workbench/debug/start",
            "graph_validate_action": "/api/workbench/graph/validate",
            "graph_compile_action": "/api/workbench/graph/compile",
            "runtime_prepare_action": "/api/workbench/runtime/prepare",
            "debug_prepare_action": "/api/workbench/debug/prepare",
            "host_info": "/api/host/info",
        }

    def _build_source_templates(self) -> dict:
        return {
            source_kind: dict(template)
            for source_kind, template in SOURCE_TEMPLATES.items()
        }

    def _find_graph_node_draft_resource(self, resource_key: str) -> dict | None:
        for item in self._get_resource_registry():
            if item.get("resource_key") == resource_key or item.get("resource_id") == resource_key:
                return dict(item)
        return None

    def _build_graph_node_draft_definition(self, *, resource: dict, resource_key: str) -> dict:
        resource_type = resource.get("resource_type")
        if resource_type == "custom_node_graph":
            return self._build_custom_node_graph_instance_draft_definition(resource)
        if resource_type in {"user_component", "subgraph_resource"}:
            return {
                "lowered_kind": "execution",
                "expansion_role": "module:component",
                "ports": [],
                "node_config": {
                    "inputs": {},
                    "outputs": {},
                },
                "parameter_schema": {},
            }
        draft_definition = get_graph_node_draft_definition(resource_key)
        if draft_definition is not None:
            return draft_definition
        return {
            "lowered_kind": "execution",
            "expansion_role": self._infer_default_graph_node_expansion_role(resource_key),
            "ports": [],
            "node_config": {},
            "parameter_schema": {},
        }

    def _build_custom_node_graph_instance_draft_definition(self, resource: dict) -> dict:
        input_schema = resource.get("input_schema")
        output_schema = resource.get("output_schema")
        if not isinstance(input_schema, dict):
            input_schema = {}
        if not isinstance(output_schema, dict):
            output_schema = {}

        input_defaults: dict[str, object] = {}
        output_defaults: dict[str, str] = {}
        normalized_input_properties: dict[str, dict] = {}
        normalized_output_properties: dict[str, dict] = {}

        for input_name, input_meta in input_schema.items():
            if not isinstance(input_name, str) or not input_name.strip():
                continue
            normalized_name = input_name.strip()
            if not isinstance(input_meta, dict):
                input_meta = {}
            normalized_input_properties[normalized_name] = deepcopy(input_meta)
            input_defaults[normalized_name] = (
                deepcopy(input_meta["default_value"])
                if "default_value" in input_meta
                else self._build_type_compatible_custom_node_graph_input_default(input_meta)
            )

        for output_name, output_meta in output_schema.items():
            if not isinstance(output_name, str) or not output_name.strip():
                continue
            normalized_name = output_name.strip()
            if not isinstance(output_meta, dict):
                output_meta = {}
            normalized_output_properties[normalized_name] = deepcopy(output_meta)
            output_defaults[normalized_name] = normalized_name

        return {
            "lowered_kind": "execution",
            "expansion_role": "action:custom_node_graph",
            "ports": [],
            "node_config": {
                "inputs": input_defaults,
                "outputs": output_defaults,
            },
            "parameter_schema": {
                "inputs": {
                    "type": "object",
                    "properties": normalized_input_properties,
                },
                "outputs": {
                    "type": "object",
                    "properties": normalized_output_properties,
                },
            },
        }

    def _build_type_compatible_custom_node_graph_input_default(self, input_meta: dict) -> object:
        raw_type = input_meta.get("type")
        if isinstance(raw_type, str):
            normalized_type = raw_type.strip().lower()
        else:
            normalized_type = ""

        if normalized_type == "number":
            return 0
        if normalized_type == "boolean":
            return False
        if normalized_type == "array":
            return []
        if normalized_type == "object":
            return {}
        return ""

    def _infer_default_graph_node_expansion_role(self, resource_key: str) -> str:
        if resource_key == "flow.start":
            return "flow:start"
        if resource_key.startswith("control."):
            return f"control:{resource_key.removeprefix('control.')}"
        if resource_key.startswith("data."):
            return f"action:{resource_key.removeprefix('data.')}"
        if resource_key.startswith("browser."):
            return f"action:{resource_key.removeprefix('browser.')}"
        if resource_key.startswith("excel."):
            return f"action:{resource_key.removeprefix('excel.')}"
        if resource_key.startswith("file."):
            return f"action:{resource_key.removeprefix('file.')}"
        if resource_key.startswith("http."):
            return f"action:{resource_key.removeprefix('http.')}"
        if resource_key.startswith("python."):
            return f"action:{resource_key.removeprefix('python.')}"
        return resource_key

    def _build_graph_node_draft_node_id(self, *, node_id: str | None) -> str:
        if isinstance(node_id, str) and node_id.strip():
            return node_id.strip()
        return f"node-{uuid.uuid4().hex[:12]}"

    def _normalize_graph_model(self, graph_model: GraphModel) -> tuple[GraphModel, bool]:
        changed = False
        normalized_nodes: list[dict] = []

        for node in graph_model.nodes:
            normalized_node = node.model_dump(mode="python")
            normalized_node_config = deepcopy(normalized_node.get("node_config", {}))
            if not isinstance(normalized_node_config, dict):
                normalized_node_config = {}
            legacy_normalized_node, legacy_call_changed = self._normalize_legacy_call_node_to_custom_node_graph(
                normalized_node=normalized_node,
                normalized_node_config=normalized_node_config,
            )
            if legacy_call_changed:
                normalized_node = legacy_normalized_node
                normalized_node_config = deepcopy(normalized_node.get("node_config", {}))
                changed = True

            normalized_branches, branch_config_changed = self._normalize_control_branch_entries(
                node_kind=normalized_node.get("node_kind"),
                node_config=normalized_node_config,
                existing_ports=normalized_node.get("ports", []),
            )
            if branch_config_changed:
                changed = True

            normalized_ports, ports_changed = self._normalize_control_branch_ports(
                node_kind=normalized_node.get("node_kind"),
                branches=normalized_branches,
                existing_ports=normalized_node.get("ports", []),
            )
            if ports_changed:
                changed = True

            normalized_node["node_config"] = normalized_node_config
            normalized_node["ports"] = normalized_ports
            normalized_nodes.append(normalized_node)

        if not changed:
            return graph_model, False

        normalized_graph_payload = graph_model.model_dump(mode="python")
        normalized_graph_payload["nodes"] = normalized_nodes
        return GraphModel.model_validate(normalized_graph_payload), True

    def _normalize_legacy_call_node_to_custom_node_graph(
        self,
        *,
        normalized_node: dict,
        normalized_node_config: dict,
    ) -> tuple[dict, bool]:
        node_kind = normalized_node.get("node_kind")
        target_resource = None
        if node_kind == "graph.call_subgraph":
            subgraph_id = normalized_node_config.get("subgraph_id")
            if isinstance(subgraph_id, str) and subgraph_id.strip():
                target_resource = self._find_subgraph_resource(subgraph_id.strip())
        elif node_kind == "call_blueprint":
            blueprint_id = normalized_node_config.get("blueprint_id")
            if isinstance(blueprint_id, str) and blueprint_id.strip():
                target_resource = self._find_component_resource_for_blueprint(blueprint_id.strip())
        if not isinstance(target_resource, dict):
            return normalized_node, False
        if target_resource.get("resource_type") != "custom_node_graph":
            return normalized_node, False

        resource_ref = target_resource.get("resource_key") or target_resource.get("resource_id")
        if not isinstance(resource_ref, str) or not resource_ref.strip():
            return normalized_node, False

        inputs = normalized_node_config.get("inputs")
        outputs = normalized_node_config.get("outputs")
        normalized_replacement_config = {
            "inputs": deepcopy(inputs) if isinstance(inputs, dict) else {},
            "outputs": deepcopy(outputs) if isinstance(outputs, dict) else {},
        }
        replacement_node = dict(normalized_node)
        replacement_node["node_kind"] = resource_ref.strip()
        replacement_node["expansion_role"] = "action:custom_node_graph"
        replacement_node["node_config"] = normalized_replacement_config
        return replacement_node, True

    def _normalize_control_branch_entries(
        self,
        *,
        node_kind: str | None,
        node_config: dict,
        existing_ports: list | None,
    ) -> tuple[list[dict], bool]:
        if node_kind not in {"control.parallel_fork", "control.join"}:
            return [], False

        raw_branches = node_config.get("branches")
        branch_entries: list[dict] = []
        changed = False
        seen_keys: set[str] = set()

        if isinstance(raw_branches, list):
            for item in raw_branches:
                if not isinstance(item, dict):
                    changed = True
                    continue
                raw_key = item.get("key")
                if not isinstance(raw_key, str) or not raw_key.strip():
                    changed = True
                    continue
                branch_key = raw_key.strip()
                if branch_key in seen_keys:
                    changed = True
                    continue
                seen_keys.add(branch_key)
                raw_label = item.get("label")
                branch_label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else branch_key
                normalized_item = {"key": branch_key, "label": branch_label}
                if normalized_item != item:
                    changed = True
                branch_entries.append(normalized_item)
        else:
            branch_entries = self._derive_control_branch_entries_from_ports(
                node_kind=node_kind,
                existing_ports=existing_ports,
            )
            if raw_branches != branch_entries:
                changed = True

        if node_config.get("branches") != branch_entries:
            node_config["branches"] = branch_entries
            changed = True

        return branch_entries, changed

    def _derive_control_branch_entries_from_ports(
        self,
        *,
        node_kind: str,
        existing_ports: list | None,
    ) -> list[dict]:
        if not isinstance(existing_ports, list):
            return []

        entries: list[dict] = []
        seen_keys: set[str] = set()

        for port in existing_ports:
            if not isinstance(port, dict):
                continue
            port_id = port.get("port_id")
            semantic_slot = port.get("semantic_slot")

            branch_key: str | None = None
            if node_kind == "control.parallel_fork":
                branch_key = self._extract_control_branch_key(
                    port_id=port_id,
                    semantic_slot=semantic_slot,
                    port_direction=port.get("direction"),
                    expected_direction="output",
                    port_id_prefix="branch:",
                    semantic_prefix="out.branch:",
                )
            elif node_kind == "control.join":
                branch_key = self._extract_control_branch_key(
                    port_id=port_id,
                    semantic_slot=semantic_slot,
                    port_direction=port.get("direction"),
                    expected_direction="input",
                    port_id_prefix="in:",
                    semantic_prefix="in.branch:",
                )

            if not branch_key or branch_key in seen_keys:
                continue

            seen_keys.add(branch_key)
            raw_label = port.get("display_name")
            branch_label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else branch_key
            entries.append({"key": branch_key, "label": branch_label})

        return entries

    def _extract_control_branch_key(
        self,
        *,
        port_id: object,
        semantic_slot: object,
        port_direction: object,
        expected_direction: str,
        port_id_prefix: str,
        semantic_prefix: str,
    ) -> str | None:
        if isinstance(port_direction, str) and port_direction != expected_direction:
            return None
        if isinstance(semantic_slot, str) and semantic_slot.startswith(semantic_prefix):
            branch_key = semantic_slot.removeprefix(semantic_prefix).strip()
            if branch_key:
                return branch_key
        if isinstance(port_id, str) and port_id.startswith(port_id_prefix):
            branch_key = port_id.removeprefix(port_id_prefix).strip()
            if branch_key:
                return branch_key
        return None

    def _normalize_control_branch_ports(
        self,
        *,
        node_kind: str | None,
        branches: list[dict],
        existing_ports: list | None,
    ) -> tuple[list[dict], bool]:
        if node_kind == "control.parallel_fork":
            def existing_port_id_for_slot(slot: str, direction: str, fallback: str) -> str:
                if isinstance(existing_ports, list):
                    for port in existing_ports:
                        if not isinstance(port, dict):
                            continue
                        if port.get("direction") != direction:
                            continue
                        semantic_slot = port.get("semantic_slot")
                        port_id = port.get("port_id")
                        if semantic_slot == slot and isinstance(port_id, str) and port_id.strip():
                            return port_id.strip()
                return fallback

            normalized_ports = [
                {
                    "port_id": existing_port_id_for_slot("in.control", "input", "in"),
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "in.control",
                    "display_name": None,
                    "max_connections": None,
                }
            ]
            for branch in branches:
                branch_key = branch["key"]
                normalized_ports.append(
                    {
                        "port_id": existing_port_id_for_slot(
                            f"out.branch:{branch_key}",
                            "output",
                            f"branch:{branch_key}",
                        ),
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": f"out.branch:{branch_key}",
                        "display_name": branch["label"],
                        "max_connections": None,
                    }
                )
            return normalized_ports, self._ports_changed(existing_ports, normalized_ports)

        if node_kind == "control.join":
            def existing_port_id_for_slot(slot: str, direction: str, fallback: str) -> str:
                if isinstance(existing_ports, list):
                    for port in existing_ports:
                        if not isinstance(port, dict):
                            continue
                        if port.get("direction") != direction:
                            continue
                        semantic_slot = port.get("semantic_slot")
                        port_id = port.get("port_id")
                        if semantic_slot == slot and isinstance(port_id, str) and port_id.strip():
                            return port_id.strip()
                return fallback

            normalized_ports = []
            for branch in branches:
                branch_key = branch["key"]
                normalized_ports.append(
                    {
                        "port_id": existing_port_id_for_slot(
                            f"in.branch:{branch_key}",
                            "input",
                            f"in:{branch_key}",
                        ),
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": f"in.branch:{branch_key}",
                        "display_name": branch["label"],
                        "max_connections": None,
                    }
                )
            normalized_ports.append(
                {
                    "port_id": existing_port_id_for_slot("out.control", "output", "out"),
                    "direction": "output",
                    "relation_layer": "control",
                    "semantic_slot": "out.control",
                    "display_name": None,
                    "max_connections": None,
                }
            )
            return normalized_ports, self._ports_changed(existing_ports, normalized_ports)

        if not isinstance(existing_ports, list):
            return [], False
        return deepcopy(existing_ports), False

    def _ports_changed(self, existing_ports: list | None, normalized_ports: list[dict]) -> bool:
        if not isinstance(existing_ports, list):
            return bool(normalized_ports)
        try:
            existing_serialized = GraphModel.model_validate(
                {
                    "graph_model_id": "graph:compare",
                    "compilation_id": None,
                    "nodes": [
                        {
                            "node_id": "node-compare",
                            "lowered_kind": "control",
                            "source_anchor_ref": "n-compare",
                            "expansion_role": "compare",
                            "ports": existing_ports,
                            "node_config": {},
                        }
                    ],
                    "edges": [],
                    "graph_effective_diagnostic_anchor_refs": [],
                }
            ).nodes[0].ports
        except ValidationError:
            return True

        existing_dump = [port.model_dump(mode="python") for port in existing_serialized]
        return existing_dump != normalized_ports

    def _resolve_resource_display_name(self, resource: dict) -> str:
        preferences = self._preferences_service.get_preferences_document()
        program_settings = preferences.get("program_settings", {})
        preferred_locale = program_settings.get("resource_language")
        display_name_i18n = resource.get("display_name_i18n", {})
        if (
            isinstance(preferred_locale, str)
            and preferred_locale.strip()
            and isinstance(display_name_i18n, dict)
        ):
            localized = display_name_i18n.get(preferred_locale.strip())
            if isinstance(localized, str) and localized.strip():
                return localized.strip()
        display_name = resource.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
        return resource.get("resource_key", "Unnamed Node")

    def _build_resource_registry_summary(self, resources: list[dict]) -> dict:
        builtin_count = len([item for item in resources if item["resource_type"] == "builtin_component"])
        user_count = len(
            [
                item
                for item in resources
                if item["resource_type"] in {
                    "user_component",
                    "subgraph_resource",
                    "custom_node_graph",
                }
            ]
        )
        enabled_count = len([item for item in resources if item["enabled"] is True])
        return {
            "total_resource_count": len(resources),
            "builtin_resource_count": builtin_count,
            "user_resource_count": user_count,
            "enabled_resource_count": enabled_count,
        }

    def _refresh_state_from_store(self) -> None:
        loaded_state = self._state_store.load()
        state, changed = self._normalize_workspace_state(loaded_state)
        if changed:
            state = self._state_store.mutate(
                lambda current: self._normalize_workspace_state(current)[0]
            )
        self._state = state

    def _has_persisted_workspace_state(self) -> bool:
        if not isinstance(self._state_store, FileWorkspaceStateStore):
            return False
        state_path = getattr(self._state_store, "_path", None)
        if not (isinstance(state_path, Path) and state_path.exists()):
            return False
        return (
            self._state["workbench"]["compile_counter"] > 0
            or self._state["last_compile"] is not None
            or len(self._state["compile_history"]) > 0
            or self._get_project_runtime()["project_file_path"] is not None
            or len(self._get_recent_projects()) > 0
            or self._get_resource_registry_revision() > 0
        )

    def _get_graph_document_model(self) -> GraphModel:
        raw_graph_document = self._state.get("graph_document")
        if raw_graph_document is None:
            graph_model = create_empty_graph_model("graph:workspace", None)
            self._state["graph_document"] = graph_model.model_dump()
            return graph_model
        graph_model = GraphModel.model_validate(raw_graph_document)
        normalized_graph_model, changed = self._normalize_graph_model(graph_model)
        if changed:
            self._persist_graph_document(normalized_graph_model)
            return normalized_graph_model
        return graph_model

    def _build_graph_document_view(self, graph_model: GraphModel) -> dict:
        graph_workspace = self._build_graph_workspace_metadata(graph_model)
        return {
            **graph_workspace,
            "is_editable": True,
        }

    def _persist_graph_document(
        self,
        graph_model: GraphModel,
        *,
        expected_graph_document_save_revision: int | None = None,
    ) -> None:
        save_conflict_policy = self._get_graph_save_conflict_policy()

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            raw_meta = current_state.get("graph_document_meta")
            if not isinstance(raw_meta, dict):
                raw_meta = {}
            save_revision = raw_meta.get("save_revision", 0)
            if not isinstance(save_revision, int):
                save_revision = 0
            if (
                expected_graph_document_save_revision is not None
                and expected_graph_document_save_revision != save_revision
                and save_conflict_policy == "strict"
            ):
                raise GraphDocumentRevisionConflictError(
                    expected_revision=expected_graph_document_save_revision,
                    current_revision=save_revision,
                )
            current_state["graph_document"] = graph_model.model_dump()
            current_state["graph_document_meta"] = {
                "save_revision": save_revision + 1,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            project_runtime = self._extract_project_runtime(current_state)
            project_runtime["is_dirty"] = True
            current_state["project_runtime"] = project_runtime
            return current_state

        self._state = self._state_store.mutate(mutation)

    def _get_graph_document_meta(self) -> dict:
        raw_meta = self._state.get("graph_document_meta")
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        save_revision = raw_meta.get("save_revision", 0)
        saved_at = raw_meta.get("saved_at")
        return {
            "save_revision": save_revision if isinstance(save_revision, int) else 0,
            "saved_at": saved_at if isinstance(saved_at, str) or saved_at is None else None,
        }

    def _build_graph_workspace_metadata(self, graph_model: GraphModel) -> dict:
        meta = self._get_graph_document_meta()
        last_compile = self._state.get("last_compile")
        last_compiled_graph_model_id = None
        last_compiled_graph_save_revision = None
        last_compiled_graph_saved_at = None
        last_compile_matches_saved_graph = None

        if isinstance(last_compile, dict) and last_compile.get("request_origin") == "graph_document":
            last_compiled_graph_model_id = last_compile.get("requested_graph_model_id")
            last_compiled_graph_save_revision = last_compile.get("requested_graph_save_revision")
            last_compiled_graph_saved_at = last_compile.get("requested_graph_saved_at")
            last_compile_matches_saved_graph = (
                last_compiled_graph_model_id == graph_model.graph_model_id
                and last_compiled_graph_save_revision == meta["save_revision"]
            )

        return {
            "authority_mode": "workspace_graph_draft",
            "compile_source_authority": "graph_document",
            "graph_model_id": graph_model.graph_model_id,
            "graph_schema_version": graph_model.graph_schema_version,
            "node_count": len(graph_model.nodes),
            "edge_count": len(graph_model.edges),
            "graph_document_save_revision": meta["save_revision"],
            "graph_document_saved_at": meta["saved_at"],
            "last_compiled_graph_model_id": last_compiled_graph_model_id,
            "last_compiled_graph_save_revision": last_compiled_graph_save_revision,
            "last_compiled_graph_saved_at": last_compiled_graph_saved_at,
            "last_compile_matches_saved_graph": last_compile_matches_saved_graph,
            "validation_summary": self._build_workspace_graph_validation_summary(graph_model),
            "validation_diagnostics": self._build_workspace_graph_validation_diagnostics(graph_model),
            "graph_preferences": self._get_graph_preferences(),
            "preferences_state": self._build_preferences_state(),
        }

    def _refresh_workspace_graph_validation_snapshot(self) -> None:
        self._refresh_state_from_store()
        graph_document = self._get_graph_document_model().model_dump(mode="json")
        validation = self.validate_graph_document(graph_document)
        self._set_workspace_graph_validation_snapshot(validation)

    def _set_workspace_graph_validation_snapshot(self, validation: dict) -> None:
        graph_model = validation.get("graph_model")
        if not isinstance(graph_model, GraphModel):
            raise ValueError("validation payload missing graph_model")
        summary = validation.get("summary")
        diagnostics = validation.get("diagnostics")
        if not isinstance(summary, dict):
            summary = {"error_count": 0, "warning_count": 0}
        if not isinstance(diagnostics, list):
            diagnostics = []
        graph_document_meta = self._get_graph_document_meta()
        snapshot = {
            "graph_model_id": graph_model.graph_model_id,
            "graph_document_save_revision": graph_document_meta["save_revision"],
            "resource_registry_revision": self._get_resource_registry_revision(),
            "status": validation.get("status") if isinstance(validation.get("status"), str) else "invalid",
            "summary": {
                "error_count": summary.get("error_count", 0),
                "warning_count": summary.get("warning_count", 0),
            },
            "diagnostics": diagnostics,
        }

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            current_state["graph_validation_snapshot"] = snapshot
            return current_state

        self._state = self._state_store.mutate(mutation)

    def _build_workspace_graph_validation_summary(self, graph_model: GraphModel) -> dict:
        snapshot = self._get_graph_validation_snapshot(graph_model)
        summary = snapshot.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        return {
            "status": snapshot.get("status"),
            "error_count": summary.get("error_count", 0),
            "warning_count": summary.get("warning_count", 0),
        }

    def _build_workspace_graph_validation_diagnostics(self, graph_model: GraphModel) -> list[dict]:
        snapshot = self._get_graph_validation_snapshot(graph_model)
        diagnostics = snapshot.get("diagnostics")
        if not isinstance(diagnostics, list):
            return []
        return diagnostics

    def _get_graph_validation_snapshot(self, graph_model: GraphModel) -> dict:
        snapshot = self._extract_graph_validation_snapshot(self._state)
        graph_document_meta = self._get_graph_document_meta()
        if (
            snapshot.get("graph_model_id") != graph_model.graph_model_id
            or snapshot.get("graph_document_save_revision") != graph_document_meta["save_revision"]
            or snapshot.get("resource_registry_revision") != self._get_resource_registry_revision()
        ):
            self._refresh_workspace_graph_validation_snapshot()
            snapshot = self._extract_graph_validation_snapshot(self._state)
        return snapshot

    def _extract_graph_validation_snapshot(self, state: dict | None) -> dict:
        raw_snapshot = state.get("graph_validation_snapshot") if isinstance(state, dict) else None
        if not isinstance(raw_snapshot, dict):
            raw_snapshot = {}
        raw_summary = raw_snapshot.get("summary")
        if not isinstance(raw_summary, dict):
            raw_summary = {}
        raw_diagnostics = raw_snapshot.get("diagnostics")
        if not isinstance(raw_diagnostics, list):
            raw_diagnostics = []
        graph_model_id = raw_snapshot.get("graph_model_id")
        status = raw_snapshot.get("status")
        graph_document_save_revision = raw_snapshot.get("graph_document_save_revision")
        resource_registry_revision = raw_snapshot.get("resource_registry_revision")
        return {
            "graph_model_id": (
                graph_model_id.strip()
                if isinstance(graph_model_id, str) and graph_model_id.strip()
                else "graph:workspace"
            ),
            "graph_document_save_revision": (
                graph_document_save_revision if isinstance(graph_document_save_revision, int) else 0
            ),
            "resource_registry_revision": (
                resource_registry_revision if isinstance(resource_registry_revision, int) else 0
            ),
            "status": status.strip() if isinstance(status, str) and status.strip() else "valid",
            "summary": {
                "error_count": raw_summary.get("error_count") if isinstance(raw_summary.get("error_count"), int) else 0,
                "warning_count": (
                    raw_summary.get("warning_count") if isinstance(raw_summary.get("warning_count"), int) else 0
                ),
            },
            "diagnostics": raw_diagnostics,
        }

    def _collect_graph_validation_diagnostics(self, graph_model: GraphModel) -> list[dict]:
        diagnostics: list[dict] = []
        node_ids_seen: set[str] = set()
        node_by_id = {node.node_id: node for node in graph_model.nodes}
        port_map_by_node_id = {
            node.node_id: {port.port_id: port for port in node.ports}
            for node in graph_model.nodes
        }
        entry_node_ids = [
            node.node_id
            for node in graph_model.nodes
            if node.node_kind == "flow.start"
        ]
        reachable_node_ids = self._collect_flow_graph_reachable_node_ids(graph_model)
        resource_by_key_or_id: dict[str, dict] = {}
        for resource in self._get_resource_registry():
            resource_by_key_or_id[resource["resource_id"]] = resource
            resource_by_key_or_id[resource["resource_key"]] = resource

        diagnostics.extend(
            self._collect_flow_start_validation_diagnostics(
                graph_model=graph_model,
                entry_node_ids=entry_node_ids,
            )
        )

        for node in graph_model.nodes:
            if node.node_id in node_ids_seen:
                diagnostics.append(
                    {
                        "category": "graph.node.duplicate_node_id",
                        "message": f"duplicate node_id: {node.node_id}",
                        "object_ref": node.node_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=node.node_id,
                            rule="graph.node.unique_node_id",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "node_id": node.node_id,
                            },
                        ),
                    }
                )
                continue
            node_ids_seen.add(node.node_id)

            if node.node_kind:
                resource = resource_by_key_or_id.get(node.node_kind)
                if resource is not None and resource.get("enabled") is not True:
                    diagnostics.append(
                        {
                            "category": "graph.node.resource_disabled",
                            "message": (
                                f"node resource is disabled: "
                                f"{resource['resource_id']}"
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="graph.node.resource_enabled",
                                result="failed",
                                graph_ref={
                                    "graph_model_id": graph_model.graph_model_id,
                                    "node_id": node.node_id,
                                    "node_kind": node.node_kind,
                                    "resource_id": resource["resource_id"],
                                    "resource_status": "disabled",
                                },
                            ),
                        }
                    )

            if entry_node_ids and node.node_kind != "flow.start" and node.node_id not in reachable_node_ids:
                diagnostics.append(
                    {
                        "category": "graph.node.unreachable_in_flow_graph",
                        "message": (
                            f"node is unreachable from flow.start: {node.node_id}"
                        ),
                        "object_ref": node.node_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=node.node_id,
                            rule="graph.node.reachable_from_flow_start",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "node_id": node.node_id,
                                "entry_node_ids": entry_node_ids,
                            },
                        ),
                    }
                )

            diagnostics.extend(
                self._collect_custom_node_graph_validation_diagnostics(
                    graph_model=graph_model,
                    node=node,
                    resource_by_key_or_id=resource_by_key_or_id,
                )
            )

            diagnostics.extend(
                self._collect_graph_call_subgraph_validation_diagnostics(
                    graph_model=graph_model,
                    node=node,
                )
            )
            diagnostics.extend(
                self._collect_flow_control_node_validation_diagnostics(
                    graph_model=graph_model,
                    node=node,
                    port_map=port_map_by_node_id.get(node.node_id, {}),
                )
            )
            diagnostics.extend(
                self._collect_builtin_parameter_validation_diagnostics(
                    graph_model=graph_model,
                    node=node,
                )
            )

            port_ids_seen: set[str] = set()
            for port in node.ports:
                if port.port_id in port_ids_seen:
                    diagnostics.append(
                        {
                            "category": "graph.node.duplicate_port_id",
                            "message": (
                                f"duplicate port_id on node {node.node_id}: {port.port_id}"
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="graph.node.unique_port_id",
                                result="failed",
                                graph_ref={
                                    "graph_model_id": graph_model.graph_model_id,
                                    "node_id": node.node_id,
                                    "port_id": port.port_id,
                                },
                            ),
                        }
                    )
                    continue
                port_ids_seen.add(port.port_id)

        for edge in graph_model.edges:
            if edge.relation_layer == "observe":
                diagnostics.append(
                    {
                        "category": "graph.edge.observe_unsupported",
                        "message": f"observe relation layer is not supported yet: {edge.edge_id}",
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.observe_unsupported",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "relation_layer": edge.relation_layer,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )
                continue
            source_node = node_by_id.get(edge.from_node_id)
            target_node = node_by_id.get(edge.to_node_id)

            if source_node is None:
                diagnostics.append(
                    {
                        "category": "graph.edge.missing_source_node",
                        "message": f"edge source node not found: {edge.from_node_id}",
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.source_node_exists",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )
                continue

            if target_node is None:
                diagnostics.append(
                    {
                        "category": "graph.edge.missing_target_node",
                        "message": f"edge target node not found: {edge.to_node_id}",
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.target_node_exists",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )
                continue

            if edge.from_port_id is not None and self._resolve_graph_port_by_reference(
                node=source_node,
                port_id=edge.from_port_id,
                direction="output",
            ) is None:
                diagnostics.append(
                    {
                        "category": "graph.edge.missing_source_port",
                        "message": (
                            f"edge source port not found on node {edge.from_node_id}: "
                            f"{edge.from_port_id}"
                        ),
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.source_port_exists",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )

            if edge.to_port_id is not None and self._resolve_graph_port_by_reference(
                node=target_node,
                port_id=edge.to_port_id,
                direction="input",
            ) is None:
                diagnostics.append(
                    {
                        "category": "graph.edge.missing_target_port",
                        "message": (
                            f"edge target port not found on node {edge.to_node_id}: "
                            f"{edge.to_port_id}"
                        ),
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.target_port_exists",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )

            source_port = None
            if source_node is not None and edge.from_port_id is not None:
                source_port = self._resolve_graph_port_by_reference(
                    node=source_node,
                    port_id=edge.from_port_id,
                    direction="output",
                )
            target_port = None
            if target_node is not None and edge.to_port_id is not None:
                target_port = self._resolve_graph_port_by_reference(
                    node=target_node,
                    port_id=edge.to_port_id,
                    direction="input",
                )

            if (
                source_port is not None
                and target_port is not None
                and (
                    source_port.relation_layer != edge.relation_layer
                    or target_port.relation_layer != edge.relation_layer
                )
            ):
                diagnostics.append(
                    {
                        "category": "graph.edge.relation_layer_mismatch",
                        "message": (
                            f"edge relation_layer does not match connected ports: {edge.edge_id}"
                        ),
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.edge.relation_layer_matches_ports",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "from_node_id": edge.from_node_id,
                                "to_node_id": edge.to_node_id,
                                "from_port_id": edge.from_port_id,
                                "to_port_id": edge.to_port_id,
                                "edge_relation_layer": edge.relation_layer,
                                "from_port_relation_layer": source_port.relation_layer,
                                "to_port_relation_layer": target_port.relation_layer,
                            },
                        ),
                    }
                )

        diagnostics.extend(
            self._collect_port_max_connections_validation_diagnostics(
                graph_model=graph_model,
                port_map_by_node_id=port_map_by_node_id,
            )
        )

        return diagnostics

    def _collect_builtin_parameter_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        node,
    ) -> list[dict]:
        node_kind = getattr(node, "node_kind", None)
        if not isinstance(node_kind, str) or not node_kind.strip():
            return []
        normalized_node_kind = node_kind.strip()
        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            node_config = {}

        draft_definition = get_graph_node_draft_definition(normalized_node_kind)
        if not isinstance(draft_definition, dict):
            return []
        parameter_schema = draft_definition.get("parameter_schema")
        if not isinstance(parameter_schema, dict):
            return []

        required_parameters = [
            parameter_name
            for parameter_name, parameter_definition in parameter_schema.items()
            if isinstance(parameter_definition, dict)
            and parameter_definition.get("required") is True
        ]
        if not required_parameters:
            return []

        diagnostics: list[dict] = []
        for parameter_name in required_parameters:
            parameter_value = node_config.get(parameter_name)
            if isinstance(parameter_value, str):
                is_blank = not parameter_value.strip()
            else:
                is_blank = parameter_value is None
            if not is_blank:
                continue
            diagnostics.append(
                {
                    "category": "graph.node.parameter_blank_required",
                    "message": (
                        f"{normalized_node_kind}.{parameter_name} is required and must not be blank"
                    ),
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.node.required_parameter_present",
                        result="failed",
                        graph_ref={
                            "graph_model_id": graph_model.graph_model_id,
                            "node_id": node.node_id,
                            "node_kind": normalized_node_kind,
                            "parameter_name": parameter_name,
                        },
                    ),
                }
            )
        return diagnostics

    def _collect_flow_start_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        entry_node_ids: list[str],
    ) -> list[dict]:
        diagnostics: list[dict] = []
        if len(entry_node_ids) > 1:
            diagnostics.append(
                {
                    "category": "graph.flow_start.invalid_entry_count",
                    "message": "graph must not contain more than one flow.start node",
                    "object_ref": entry_node_ids[0],
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=entry_node_ids[0],
                        rule="graph.flow_start.single_entry_node",
                        result="failed",
                        graph_ref={
                            "graph_model_id": graph_model.graph_model_id,
                            "entry_node_ids": entry_node_ids,
                            "entry_count": len(entry_node_ids),
                        },
                    ),
                }
            )

        entry_node_id_set = set(entry_node_ids)
        for edge in graph_model.edges:
            if (
                edge.relation_layer == "control"
                and edge.to_node_id in entry_node_id_set
            ):
                diagnostics.append(
                    {
                        "category": "graph.flow_start.control_input_forbidden",
                        "message": (
                            f"flow.start cannot accept incoming control edges: {edge.to_node_id}"
                        ),
                        "object_ref": edge.edge_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=edge.edge_id,
                            rule="graph.flow_start.no_control_inputs",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "edge_id": edge.edge_id,
                                "entry_node_id": edge.to_node_id,
                                "from_node_id": edge.from_node_id,
                                "to_port_id": edge.to_port_id,
                            },
                        ),
                    }
                )
        return diagnostics

    def _collect_flow_control_node_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        node,
        port_map: dict[str, object],
    ) -> list[dict]:
        node_kind = getattr(node, "node_kind", None)
        if not isinstance(node_kind, str):
            return []
        normalized_node_kind = node_kind.strip()
        if normalized_node_kind not in {
            "control.if",
            "control.switch",
            "control.parallel_fork",
            "control.join",
            "control.while",
            "control.retry",
            "control.failover",
        }:
            return []

        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            node_config = {}

        ports = list(port_map.values())
        diagnostics: list[dict] = []

        def append_missing_port(required_port_id: str) -> None:
            diagnostics.append(
                {
                    "category": f"graph.{normalized_node_kind}.missing_required_port",
                    "message": (
                        f"{normalized_node_kind} requires port: {required_port_id}"
                    ),
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule=f"{normalized_node_kind}.required_ports_present",
                        result="failed",
                        graph_ref={
                            "graph_model_id": graph_model.graph_model_id,
                            "node_id": node.node_id,
                            "node_kind": normalized_node_kind,
                            "port_id": required_port_id,
                        },
                    ),
                }
            )

        def has_port(port_id: str) -> bool:
            for port in ports:
                if self._control_port_matches_expected(
                    port_id=getattr(port, "port_id", None),
                    semantic_slot=getattr(port, "semantic_slot", None),
                    direction=getattr(port, "direction", None),
                    expected=port_id,
                ):
                    return True
            return False

        def count_prefixed_ports(*, prefix: str, direction: str | None = None) -> int:
            return self._count_control_ports_with_prefix(
                ports=ports,
                prefix=prefix,
                direction=direction,
            )

        def count_semantic_prefixed_ports(*, prefix: str, direction: str | None = None) -> int:
            return self._count_control_ports_with_semantic_prefix(
                ports=ports,
                prefix=prefix,
                direction=direction,
            )

        def has_condition_input() -> bool:
            for port in ports:
                if port.direction != "input" or port.relation_layer != "data":
                    continue
                if port.port_id == "condition":
                    return True
                if port.semantic_slot in {"in.condition", "condition"}:
                    return True
            return False

        def has_selector_input() -> bool:
            for port in ports:
                if port.direction != "input" or port.relation_layer != "data":
                    continue
                if port.port_id == "selector":
                    return True
                if port.semantic_slot in {"in.selector", "selector"}:
                    return True
            return False

        def append_simple_diagnostic(category_suffix: str, message: str, **graph_ref_extra) -> None:
            diagnostics.append(
                {
                    "category": f"graph.{normalized_node_kind}.{category_suffix}",
                    "message": message,
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule=f"{normalized_node_kind}.{category_suffix}",
                        result="failed",
                        graph_ref={
                            "graph_model_id": graph_model.graph_model_id,
                            "node_id": node.node_id,
                            "node_kind": normalized_node_kind,
                            **graph_ref_extra,
                        },
                    ),
                }
            )

        if normalized_node_kind == "control.if":
            for required_port_id in ("in", "true", "false"):
                if not has_port(required_port_id):
                    append_missing_port(required_port_id)
            expression = node_config.get("expression")
            if not has_condition_input() and not (
                isinstance(expression, str) and expression.strip()
            ):
                append_simple_diagnostic(
                    "condition_missing",
                    "control.if requires a condition input or node_config.expression",
                )
            return diagnostics

        if normalized_node_kind == "control.switch":
            if not has_port("in"):
                append_missing_port("in")
            if count_prefixed_ports(prefix="case:", direction="output") < 1:
                append_simple_diagnostic(
                    "case_count_invalid",
                    "control.switch requires at least one case:* output port",
                )
            selector = node_config.get("selector")
            expression = node_config.get("expression")
            if not has_selector_input() and not (
                isinstance(selector, str)
                and selector.strip()
                or isinstance(expression, str)
                and expression.strip()
            ):
                append_simple_diagnostic(
                    "selector_missing",
                    "control.switch requires a selector input or node_config.selector/expression",
                )
            return diagnostics

        if normalized_node_kind == "control.parallel_fork":
            if not has_port("in"):
                append_missing_port("in")
            branch_count = count_semantic_prefixed_ports(prefix="out.branch:", direction="output")
            if branch_count < 2:
                append_simple_diagnostic(
                    "branch_count_invalid",
                    "control.parallel_fork requires at least two branch:* output ports",
                    branch_count=branch_count,
                )
            return diagnostics

        if normalized_node_kind == "control.join":
            branch_count = count_semantic_prefixed_ports(prefix="in.branch:", direction="input")
            if branch_count < 2:
                append_simple_diagnostic(
                    "branch_count_invalid",
                    "control.join requires at least two in:* input ports",
                    branch_count=branch_count,
                )
            if not has_port("out"):
                append_missing_port("out")
            if node_config.get("mode") == "quorum":
                quorum = node_config.get("quorum")
                if not isinstance(quorum, int) or quorum < 1 or quorum > branch_count:
                    append_simple_diagnostic(
                        "quorum_invalid",
                        "control.join quorum must be a positive integer within input branch count",
                        branch_count=branch_count,
                        quorum=quorum,
                    )
            return diagnostics

        if normalized_node_kind == "control.while":
            for required_port_id in ("in", "repeat", "loop", "done"):
                if not has_port(required_port_id):
                    append_missing_port(required_port_id)
            expression = node_config.get("expression")
            if not has_condition_input() and not (
                isinstance(expression, str) and expression.strip()
            ):
                append_simple_diagnostic(
                    "condition_missing",
                    "control.while requires a condition input or node_config.expression",
                )
            return diagnostics

        if normalized_node_kind == "control.retry":
            max_attempts = node_config.get("max_attempts")
            if not isinstance(max_attempts, int) or max_attempts < 1:
                append_simple_diagnostic(
                    "max_attempts_invalid",
                    "control.retry requires node_config.max_attempts >= 1",
                    max_attempts=max_attempts,
                )
            return diagnostics

        if normalized_node_kind == "control.failover":
            has_primary = has_port("primary")
            fallback_count = count_prefixed_ports(prefix="fallback:", direction="output")
            if not has_primary and fallback_count < 1:
                append_simple_diagnostic(
                    "branch_count_invalid",
                    "control.failover requires primary or fallback:* output ports",
                    primary_present=has_primary,
                    fallback_count=fallback_count,
                )
            if not has_port("failed"):
                append_missing_port("failed")
            return diagnostics

        return diagnostics

    def _collect_port_max_connections_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        port_map_by_node_id: dict[str, dict[str, object]],
    ) -> list[dict]:
        connection_edge_ids_by_port_ref: dict[tuple[str, str], list[str]] = {}
        for edge in graph_model.edges:
            if edge.from_port_id is not None:
                connection_edge_ids_by_port_ref.setdefault(
                    (edge.from_node_id, edge.from_port_id),
                    [],
                ).append(edge.edge_id)
            if edge.to_port_id is not None:
                connection_edge_ids_by_port_ref.setdefault(
                    (edge.to_node_id, edge.to_port_id),
                    [],
                ).append(edge.edge_id)

        diagnostics: list[dict] = []
        for node_id, port_map in port_map_by_node_id.items():
            for port_id, port in port_map.items():
                if port.max_connections is None:
                    continue
                edge_ids = connection_edge_ids_by_port_ref.get((node_id, port_id), [])
                if len(edge_ids) <= port.max_connections:
                    continue
                diagnostics.append(
                    {
                        "category": "graph.port.max_connections_exceeded",
                        "message": (
                            f"port exceeds max_connections: {node_id}.{port_id}"
                        ),
                        "object_ref": node_id,
                        "stage_extension": self._build_graph_validation_stage_extension(
                            graph_model,
                            subject_ref=node_id,
                            rule="graph.port.max_connections_respected",
                            result="failed",
                            graph_ref={
                                "graph_model_id": graph_model.graph_model_id,
                                "node_id": node_id,
                                "port_id": port_id,
                                "relation_layer": port.relation_layer,
                                "max_connections": port.max_connections,
                                "connection_count": len(edge_ids),
                                "edge_ids": edge_ids,
                            },
                        ),
                    }
                )
        return diagnostics

    def _collect_custom_node_graph_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        node,
        resource_by_key_or_id: dict[str, dict],
    ) -> list[dict]:
        node_kind = getattr(node, "node_kind", None)
        if not isinstance(node_kind, str) or not node_kind.strip():
            return []
        normalized_node_kind = node_kind.strip()

        custom_resource = resource_by_key_or_id.get(normalized_node_kind)
        if isinstance(custom_resource, dict):
            if custom_resource.get("resource_type") != "custom_node_graph":
                return []
            normalized_resource_ref = str(
                custom_resource.get("resource_key")
                or custom_resource.get("resource_id")
                or normalized_node_kind
            )
        elif normalized_node_kind.startswith(CUSTOM_NODE_GRAPH_RESOURCE_PREFIX):
            custom_resource = None
            normalized_resource_ref = normalized_node_kind
        else:
            return []

        diagnostics: list[dict] = []
        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            node_config = {}

        graph_ref = {
            "graph_model_id": graph_model.graph_model_id,
            "node_id": node.node_id,
            "node_kind": normalized_node_kind,
            "resource_ref": normalized_resource_ref,
        }

        if custom_resource is None:
            diagnostics.append(
                {
                    "category": "custom_node_graph.missing",
                    "message": f"custom node graph was not found: {normalized_resource_ref}",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="custom_node_graph.exists",
                        result="failed",
                        graph_ref=graph_ref,
                    ),
                }
            )
            return diagnostics

        if custom_resource.get("enabled") is not True:
            diagnostics.append(
                {
                    "category": "custom_node_graph.disabled",
                    "message": f"custom node graph is disabled: {normalized_resource_ref}",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="custom_node_graph.enabled",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "resource_id": custom_resource.get("resource_id"),
                            "resource_status": "disabled",
                        },
                    ),
                }
            )

        raw_inputs = node_config.get("inputs")
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            diagnostics.append(
                {
                    "category": "custom_node_graph.input_mapping_invalid",
                    "message": "custom node graph node_config.inputs must be an object mapping",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="custom_node_graph.inputs_mapping_shape",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "mapping_field": "inputs",
                        },
                    ),
                }
            )
        elif isinstance(raw_inputs, dict):
            connected_input_names = self._collect_graph_node_connected_input_names(
                graph_model=graph_model,
                node=node,
            )
            input_schema = custom_resource.get("input_schema")
            if isinstance(input_schema, dict) and input_schema:
                missing_required_inputs = [
                    input_name
                    for input_name, input_meta in input_schema.items()
                    if isinstance(input_name, str)
                    and input_name.strip()
                    and isinstance(input_meta, dict)
                    and input_meta.get("required") is True
                    and input_name.strip() not in raw_inputs
                    and input_name.strip() not in connected_input_names
                ]
                if missing_required_inputs:
                    diagnostics.append(
                        {
                            "category": "custom_node_graph.input_mapping_missing_required",
                            "message": (
                                "custom node graph is missing required schema inputs: "
                                + ", ".join(sorted(missing_required_inputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="custom_node_graph.inputs_cover_required_schema",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "missing_required_inputs": sorted(missing_required_inputs),
                                },
                            ),
                        }
                    )
                invalid_typed_inputs = [
                    input_name
                    for input_name, input_meta in input_schema.items()
                    if isinstance(input_name, str)
                    and input_name.strip()
                    and input_name.strip() in raw_inputs
                    and input_name.strip() not in connected_input_names
                    and isinstance(input_meta, dict)
                    and not self._schema_value_matches_type(
                        raw_inputs[input_name.strip()],
                        input_meta.get("type"),
                    )
                ]
                if invalid_typed_inputs:
                    diagnostics.append(
                        {
                            "category": "custom_node_graph.input_mapping_type_mismatch",
                            "message": (
                                "custom node graph schema input type mismatch: "
                                + ", ".join(sorted(invalid_typed_inputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="custom_node_graph.inputs_match_schema_types",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "invalid_typed_inputs": sorted(invalid_typed_inputs),
                                },
                            ),
                        }
                    )

        raw_outputs = node_config.get("outputs")
        if raw_outputs is not None and not isinstance(raw_outputs, dict):
            diagnostics.append(
                {
                    "category": "custom_node_graph.output_mapping_invalid",
                    "message": "custom node graph node_config.outputs must be an object mapping",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="custom_node_graph.outputs_mapping_shape",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "mapping_field": "outputs",
                        },
                    ),
                }
            )
        elif isinstance(raw_outputs, dict):
            output_schema = custom_resource.get("output_schema")
            if isinstance(output_schema, dict) and output_schema:
                unknown_outputs = [
                    child_name
                    for child_name in raw_outputs
                    if isinstance(child_name, str)
                    and child_name.strip()
                    and child_name.strip() not in output_schema
                ]
                if unknown_outputs:
                    diagnostics.append(
                        {
                            "category": "custom_node_graph.output_mapping_unknown_output",
                            "message": (
                                "custom node graph maps unknown schema outputs: "
                                + ", ".join(sorted(unknown_outputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="custom_node_graph.outputs_exist_in_schema",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "unknown_outputs": sorted(unknown_outputs),
                                },
                            ),
                        }
                    )

        return diagnostics

    def _collect_graph_call_subgraph_validation_diagnostics(
        self,
        *,
        graph_model: GraphModel,
        node,
    ) -> list[dict]:
        if getattr(node, "node_kind", None) != "graph.call_subgraph":
            return []

        diagnostics: list[dict] = []
        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            node_config = {}

        subgraph_id = node_config.get("subgraph_id")
        normalized_subgraph_id = subgraph_id.strip() if isinstance(subgraph_id, str) else None
        graph_ref = {
            "graph_model_id": graph_model.graph_model_id,
            "node_id": node.node_id,
            "node_kind": "graph.call_subgraph",
        }

        if not normalized_subgraph_id:
            diagnostics.append(
                {
                    "category": "graph.call_subgraph.subgraph_id_required",
                    "message": "graph.call_subgraph requires node_config.subgraph_id",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.call_subgraph.subgraph_id_present",
                        result="failed",
                        graph_ref=graph_ref,
                    ),
                }
            )
            return diagnostics

        subgraph_resource = self._find_subgraph_resource(normalized_subgraph_id)
        if subgraph_resource is None:
            diagnostics.append(
                {
                    "category": "graph.call_subgraph.subgraph_missing",
                    "message": f"graph.call_subgraph subgraph was not found: {normalized_subgraph_id}",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.call_subgraph.subgraph_exists",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "subgraph_id": normalized_subgraph_id,
                        },
                    ),
                }
            )
        elif subgraph_resource.get("enabled") is not True:
            diagnostics.append(
                {
                    "category": "graph.call_subgraph.subgraph_disabled",
                    "message": f"graph.call_subgraph subgraph is disabled: {normalized_subgraph_id}",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.call_subgraph.subgraph_enabled",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "subgraph_id": normalized_subgraph_id,
                            "resource_id": subgraph_resource.get("resource_id"),
                            "resource_status": "disabled",
                        },
                    ),
                }
            )

        raw_inputs = node_config.get("inputs")
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            diagnostics.append(
                {
                    "category": "graph.call_subgraph.input_mapping_invalid",
                    "message": "graph.call_subgraph node_config.inputs must be an object mapping",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.call_subgraph.inputs_mapping_shape",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "subgraph_id": normalized_subgraph_id,
                            "mapping_field": "inputs",
                        },
                    ),
                }
            )
        elif isinstance(raw_inputs, dict) and isinstance(subgraph_resource, dict):
            connected_input_names = self._collect_graph_node_connected_input_names(
                graph_model=graph_model,
                node=node,
            )
            input_schema = subgraph_resource.get("input_schema")
            if isinstance(input_schema, dict) and input_schema:
                missing_required_inputs = [
                    input_name
                    for input_name, input_meta in input_schema.items()
                    if isinstance(input_name, str)
                    and input_name.strip()
                    and isinstance(input_meta, dict)
                    and input_meta.get("required") is True
                    and input_name.strip() not in raw_inputs
                    and input_name.strip() not in connected_input_names
                ]
                if missing_required_inputs:
                    diagnostics.append(
                        {
                            "category": "graph.call_subgraph.input_mapping_missing_required",
                            "message": (
                                "graph.call_subgraph is missing required schema inputs: "
                                + ", ".join(sorted(missing_required_inputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="graph.call_subgraph.inputs_cover_required_schema",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "subgraph_id": normalized_subgraph_id,
                                    "missing_required_inputs": sorted(missing_required_inputs),
                                },
                            ),
                        }
                    )
                invalid_typed_inputs = [
                    input_name
                    for input_name, input_meta in input_schema.items()
                    if isinstance(input_name, str)
                    and input_name.strip()
                    and input_name.strip() in raw_inputs
                    and input_name.strip() not in connected_input_names
                    and isinstance(input_meta, dict)
                    and not self._schema_value_matches_type(
                        raw_inputs[input_name.strip()],
                        input_meta.get("type"),
                    )
                ]
                if invalid_typed_inputs:
                    diagnostics.append(
                        {
                            "category": "graph.call_subgraph.input_mapping_type_mismatch",
                            "message": (
                                "graph.call_subgraph schema input type mismatch: "
                                + ", ".join(sorted(invalid_typed_inputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="graph.call_subgraph.inputs_match_schema_types",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "subgraph_id": normalized_subgraph_id,
                                    "invalid_typed_inputs": sorted(invalid_typed_inputs),
                                },
                            ),
                        }
                    )

        raw_outputs = node_config.get("outputs")
        if raw_outputs is not None and not isinstance(raw_outputs, dict):
            diagnostics.append(
                {
                    "category": "graph.call_subgraph.output_mapping_invalid",
                    "message": "graph.call_subgraph node_config.outputs must be an object mapping",
                    "object_ref": node.node_id,
                    "stage_extension": self._build_graph_validation_stage_extension(
                        graph_model,
                        subject_ref=node.node_id,
                        rule="graph.call_subgraph.outputs_mapping_shape",
                        result="failed",
                        graph_ref={
                            **graph_ref,
                            "subgraph_id": normalized_subgraph_id,
                            "mapping_field": "outputs",
                        },
                    ),
                }
            )
        elif isinstance(raw_outputs, dict) and isinstance(subgraph_resource, dict):
            output_schema = subgraph_resource.get("output_schema")
            if isinstance(output_schema, dict) and output_schema:
                unknown_outputs = [
                    child_name
                    for child_name in raw_outputs
                    if isinstance(child_name, str)
                    and child_name.strip()
                    and child_name.strip() not in output_schema
                ]
                if unknown_outputs:
                    diagnostics.append(
                        {
                            "category": "graph.call_subgraph.output_mapping_unknown_output",
                            "message": (
                                "graph.call_subgraph maps unknown schema outputs: "
                                + ", ".join(sorted(unknown_outputs))
                            ),
                            "object_ref": node.node_id,
                            "stage_extension": self._build_graph_validation_stage_extension(
                                graph_model,
                                subject_ref=node.node_id,
                                rule="graph.call_subgraph.outputs_exist_in_schema",
                                result="failed",
                                graph_ref={
                                    **graph_ref,
                                    "subgraph_id": normalized_subgraph_id,
                                    "unknown_outputs": sorted(unknown_outputs),
                                },
                            ),
                        }
                    )

        return diagnostics

    def _build_graph_control_successors(self, graph_model: GraphModel) -> dict[str, list[str]]:
        control_successors: dict[str, list[str]] = {}
        for edge in graph_model.edges:
            if edge.relation_layer != "control":
                continue
            if edge.from_node_id not in control_successors:
                control_successors[edge.from_node_id] = []
            control_successors[edge.from_node_id].append(edge.to_node_id)
        return control_successors

    def _build_runtime_static_node_order(self, graph_model: GraphModel) -> dict[str, int]:
        node_ids_in_model_order = [node.node_id for node in graph_model.nodes]
        if not node_ids_in_model_order:
            return {}

        control_successors = self._build_graph_control_successors(graph_model)
        entry_node_ids = [
            node.node_id
            for node in graph_model.nodes
            if node.node_kind == "flow.start"
        ]

        if not entry_node_ids:
            return {node_id: index for index, node_id in enumerate(node_ids_in_model_order)}

        static_order: dict[str, int] = {}
        queued_node_ids: set[str] = set()
        pending_node_ids: list[str] = []

        for node_id in entry_node_ids:
            if node_id in queued_node_ids:
                continue
            queued_node_ids.add(node_id)
            pending_node_ids.append(node_id)

        while pending_node_ids:
            current_node_id = pending_node_ids.pop(0)
            if current_node_id not in static_order:
                static_order[current_node_id] = len(static_order)
            for target_node_id in control_successors.get(current_node_id, []):
                if target_node_id in queued_node_ids:
                    continue
                queued_node_ids.add(target_node_id)
                pending_node_ids.append(target_node_id)

        for node_id in node_ids_in_model_order:
            if node_id not in static_order:
                static_order[node_id] = len(static_order)

        return static_order

    def _sort_runtime_node_states_for_display(self, node_states: list[dict]) -> list[dict]:
        def sort_key(item: dict) -> tuple[int, int, int]:
            runtime_order = item.get("runtime_order")
            static_order = item.get("static_order")
            plan_index = item.get("plan_index")
            if isinstance(runtime_order, int):
                return (0, runtime_order, plan_index if isinstance(plan_index, int) else 10**9)
            return (
                1,
                static_order if isinstance(static_order, int) else 10**9,
                plan_index if isinstance(plan_index, int) else 10**9,
            )

        return [
            dict(item)
            for item in sorted(
                (item for item in node_states if isinstance(item, dict)),
                key=sort_key,
            )
        ]

    def _decorate_runtime_node_states_for_display(self, node_states: list[dict]) -> list[dict]:
        decorated = self._sort_runtime_node_states_for_display(node_states)
        for item in decorated:
            item.pop("plan_index", None)
        return decorated

    def _collect_flow_graph_reachable_node_ids(self, graph_model: GraphModel) -> set[str]:
        entry_node_ids = [
            node.node_id
            for node in graph_model.nodes
            if node.node_kind == "flow.start"
        ]
        if not entry_node_ids:
            return {node.node_id for node in graph_model.nodes}

        control_successors = self._build_graph_control_successors(graph_model)
        reachable_node_ids = set(entry_node_ids)
        pending_node_ids = list(entry_node_ids)
        while pending_node_ids:
            current_node_id = pending_node_ids.pop(0)
            for target_node_id in control_successors.get(current_node_id, []):
                if target_node_id not in reachable_node_ids:
                    reachable_node_ids.add(target_node_id)
                    pending_node_ids.append(target_node_id)
        return reachable_node_ids

    def _build_graph_validation_stage_extension(
        self,
        graph_model: GraphModel,
        *,
        subject_ref: str,
        rule: str,
        result: str,
        graph_ref: dict,
    ) -> dict:
        return {
            "subject_ref": subject_ref,
            "action": "validated graph document",
            "rule": rule,
            "result": result,
            "graph_ref": graph_ref,
        }

    def _materialize_graph_validation_diagnostic_entries(
        self,
        graph_model: GraphModel,
        diagnostics: list[dict],
        *,
        diagnostic_id_prefix: str,
    ) -> list[Diagnostic]:
        return [
            Diagnostic(
                diagnostic_id=f"{diagnostic_id_prefix}-{index + 1}",
                stage="validate",
                severity=self._resolve_graph_validation_diagnostic_severity(item),
                category=item["category"],
                message=item["message"],
                object_ref=item.get("object_ref"),
                stage_extension=item.get(
                    "stage_extension",
                    {
                        "subject_ref": graph_model.graph_model_id,
                        "action": "validated graph document",
                        "rule": "graph.structure",
                        "result": "failed",
                    },
                ),
            )
            for index, item in enumerate(diagnostics)
        ]

    def _resolve_graph_validation_diagnostic_severity(self, diagnostic: dict) -> str:
        if diagnostic.get("category") == "graph.node.unreachable_in_flow_graph":
            return "warning"
        return "fatal"

    def _build_invalid_graph_compile_result(
        self,
        graph_model: GraphModel,
        diagnostics: list[dict],
        *,
        compilation_id: str,
        duration_ms: int | None,
    ) -> dict:
        graph_document_meta = self._get_graph_document_meta()
        summary = create_initial_summary(compilation_id)
        for stage_outcome in summary.stage_outcomes:
            if stage_outcome.stage == "validate":
                stage_outcome.status = "failed"
                stage_outcome.diagnostic_count = len(diagnostics)
                break
        summary.duration_ms = duration_ms

        outcome = CompilationOutcome(
            graph_model=graph_model,
            compilation_summary=summary,
            diagnostic_catalog=DiagnosticCatalog(
                entries=self._materialize_graph_validation_diagnostic_entries(
                    graph_model,
                    diagnostics,
                    diagnostic_id_prefix=f"{compilation_id}:graph-validate",
                )
            ),
        )
        view = self._build_compile_view(
            status="failed",
            outcome=outcome,
            duration_ms=duration_ms,
        )
        return {
            "status": "failed",
            "request": {
                "compilation_id": compilation_id,
                "source_kind": "graph_workspace",
                "entry_document": graph_model.graph_model_id,
                "request_origin": "graph_document",
                "requested_graph_model_id": graph_model.graph_model_id,
                "requested_graph_save_revision": graph_document_meta["save_revision"],
                "requested_graph_saved_at": graph_document_meta["saved_at"],
                "source": {
                    "kind": "graph_workspace",
                    "entry_document": graph_model.graph_model_id,
                    "source_text": None,
                },
            },
            "outcome": outcome,
            "view": view,
        }

    def _resolve_duration_ms(self, started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))

    def _apply_duration_to_result(self, result: dict, duration_ms: int | None) -> None:
        view = result.get("view")
        if isinstance(view, dict):
            view["duration_ms"] = duration_ms
        outcome = result.get("outcome")
        if isinstance(outcome, CompilationOutcome):
            outcome.compilation_summary.duration_ms = duration_ms

    def _normalize_workspace_state(self, state: dict | None) -> tuple[dict, bool]:
        if state is None:
            return self._build_initial_workspace_state(
                project_id="weconduct-workspace"
            ), True

        changed = False
        if "project" not in state or not isinstance(state.get("project"), dict):
            state["project"] = self._build_initial_workspace_state(
                project_id="weconduct-workspace"
            )["project"]
            changed = True
        if "project_runtime" not in state or not isinstance(state.get("project_runtime"), dict):
            state["project_runtime"] = self._build_initial_workspace_state()["project_runtime"]
            changed = True
        else:
            normalized_runtime = self._extract_project_runtime(state)
            if normalized_runtime != state["project_runtime"]:
                state["project_runtime"] = normalized_runtime
                changed = True
        normalized_recent_projects = self._extract_recent_projects(state)
        if normalized_recent_projects != state.get("recent_projects"):
            state["recent_projects"] = normalized_recent_projects
            changed = True
        normalized_resource_registry = self._extract_resource_registry(state)
        if normalized_resource_registry != state.get("resource_registry"):
            state["resource_registry"] = normalized_resource_registry
            changed = True
        normalized_editor_history = self._extract_editor_history(state)
        if normalized_editor_history != state.get("editor_history"):
            state["editor_history"] = normalized_editor_history
            changed = True
        normalized_execution_history = self._extract_execution_history(state)
        if normalized_execution_history != state.get("execution_history"):
            state["execution_history"] = normalized_execution_history
            changed = True
        normalized_runtime_sessions = self._extract_runtime_sessions(state)
        if normalized_runtime_sessions != state.get("runtime_sessions"):
            state["runtime_sessions"] = normalized_runtime_sessions
            changed = True
        normalized_debug_sessions = self._extract_debug_sessions(state)
        if normalized_debug_sessions != state.get("debug_sessions"):
            state["debug_sessions"] = normalized_debug_sessions
            changed = True
        if "graph_document" not in state:
            state["graph_document"] = create_empty_graph_model(
                "graph:workspace", None
            ).model_dump()
            changed = True
        if "graph_document_meta" not in state:
            state["graph_document_meta"] = {
                "save_revision": 0,
                "saved_at": None,
            }
            changed = True
        normalized_pending_recovery = self._extract_pending_recovery(state)
        if normalized_pending_recovery != state.get("pending_recovery"):
            state["pending_recovery"] = normalized_pending_recovery
            changed = True
        if (
            isinstance(self._state_store, FileWorkspaceStateStore)
            and self._allow_dirty_workspace_recovery_conversion
            and not self._suppress_dirty_workspace_recovery
            and state.get("pending_recovery") is None
            and self._extract_project_runtime(state).get("is_dirty") is True
        ):
            state = self._convert_dirty_workspace_state_to_pending_recovery(state)
            changed = True
        if self._normalize_compile_records_in_state(state):
            changed = True
        return state, changed

    def _get_project_runtime(self) -> dict:
        return self._extract_project_runtime(self._state)

    def _resolve_runtime_project_directory(self) -> Path | None:
        project_runtime = self._get_project_runtime()
        project_file_path = project_runtime.get("project_file_path")
        if not isinstance(project_file_path, str) or not project_file_path.strip():
            return None
        return Path(project_file_path).resolve().parent

    def _resolve_runtime_workspace_root(self) -> Path | None:
        raw_project = self._state.get("project")
        workspace_root = raw_project.get("workspace_root") if isinstance(raw_project, dict) else None
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return None
        return Path(workspace_root).resolve()

    def _extract_project_runtime(self, state: dict | None) -> dict:
        raw_runtime = state.get("project_runtime") if isinstance(state, dict) else None
        if not isinstance(raw_runtime, dict):
            raw_runtime = {}
        project_file_path = raw_runtime.get("project_file_path")
        normalized_project_file_path = None
        if isinstance(project_file_path, str) and project_file_path.strip():
            normalized_project_file_path = str(Path(project_file_path).resolve())
        return {
            "project_file_path": normalized_project_file_path,
            "is_dirty": bool(raw_runtime.get("is_dirty", False)),
        }

    def _extract_pending_recovery(self, state: dict | None) -> dict | None:
        raw_pending = state.get("pending_recovery") if isinstance(state, dict) else None
        if not isinstance(raw_pending, dict):
            return None
        if raw_pending.get("status") != "pending":
            return None
        project_id = raw_pending.get("project_id")
        project_name = raw_pending.get("project_name")
        project_file_path = raw_pending.get("project_file_path")
        workspace_state = raw_pending.get("workspace_state")
        if not isinstance(project_id, str) or not project_id.strip():
            return None
        if not isinstance(project_name, str) or not project_name.strip():
            return None
        if not isinstance(project_file_path, str) or not project_file_path.strip():
            return None
        if not isinstance(workspace_state, dict):
            return None
        return {
            "status": "pending",
            "project_id": project_id.strip(),
            "project_name": project_name.strip(),
            "project_file_path": str(Path(project_file_path).resolve()),
            "workspace_state": deepcopy(workspace_state),
        }

    def _convert_dirty_workspace_state_to_pending_recovery(self, state: dict) -> dict:
        current_state, _ = self._normalize_workspace_state_without_recovery_conversion(
            deepcopy(state)
        )
        project_runtime = self._extract_project_runtime(current_state)
        project_file_path = project_runtime.get("project_file_path")
        raw_project = current_state.get("project")
        if not isinstance(raw_project, dict) or project_file_path is None:
            return current_state

        recovery_workspace_state = deepcopy(current_state)
        recovery_workspace_state["pending_recovery"] = None
        next_state = self._build_initial_workspace_state(
            project_name=raw_project.get("project_name", "Recovered Project"),
            project_id=raw_project.get("project_id"),
            project_file_path=project_file_path,
            mark_project_dirty=False,
        )
        next_state["recent_projects"] = self._extract_recent_projects(current_state)
        next_state["pending_recovery"] = {
            "status": "pending",
            "project_id": raw_project.get("project_id"),
            "project_name": raw_project.get("project_name"),
            "project_file_path": str(Path(project_file_path).resolve()),
            "workspace_state": recovery_workspace_state,
        }
        return next_state

    def _normalize_workspace_state_without_recovery_conversion(
        self,
        state: dict | None,
    ) -> tuple[dict, bool]:
        if state is None:
            return self._build_initial_workspace_state(
                project_id="weconduct-workspace"
            ), True

        changed = False
        if "project" not in state or not isinstance(state.get("project"), dict):
            state["project"] = self._build_initial_workspace_state(
                project_id="weconduct-workspace"
            )["project"]
            changed = True
        if "project_runtime" not in state or not isinstance(state.get("project_runtime"), dict):
            state["project_runtime"] = self._build_initial_workspace_state()["project_runtime"]
            changed = True
        else:
            normalized_runtime = self._extract_project_runtime(state)
            if normalized_runtime != state["project_runtime"]:
                state["project_runtime"] = normalized_runtime
                changed = True
        normalized_recent_projects = self._extract_recent_projects(state)
        if normalized_recent_projects != state.get("recent_projects"):
            state["recent_projects"] = normalized_recent_projects
            changed = True
        normalized_resource_registry = self._extract_resource_registry(state)
        if normalized_resource_registry != state.get("resource_registry"):
            state["resource_registry"] = normalized_resource_registry
            changed = True
        normalized_editor_history = self._extract_editor_history(state)
        if normalized_editor_history != state.get("editor_history"):
            state["editor_history"] = normalized_editor_history
            changed = True
        normalized_execution_history = self._extract_execution_history(state)
        if normalized_execution_history != state.get("execution_history"):
            state["execution_history"] = normalized_execution_history
            changed = True
        normalized_runtime_sessions = self._extract_runtime_sessions(state)
        if normalized_runtime_sessions != state.get("runtime_sessions"):
            state["runtime_sessions"] = normalized_runtime_sessions
            changed = True
        normalized_debug_sessions = self._extract_debug_sessions(state)
        if normalized_debug_sessions != state.get("debug_sessions"):
            state["debug_sessions"] = normalized_debug_sessions
            changed = True
        if "graph_document" not in state:
            state["graph_document"] = create_empty_graph_model(
                "graph:workspace", None
            ).model_dump()
            changed = True
        if "graph_document_meta" not in state:
            state["graph_document_meta"] = {
                "save_revision": 0,
                "saved_at": None,
            }
            changed = True
        normalized_graph_validation_snapshot = self._extract_graph_validation_snapshot(state)
        if normalized_graph_validation_snapshot != state.get("graph_validation_snapshot"):
            state["graph_validation_snapshot"] = normalized_graph_validation_snapshot
            changed = True
        normalized_pending_recovery = self._extract_pending_recovery(state)
        if normalized_pending_recovery != state.get("pending_recovery"):
            state["pending_recovery"] = normalized_pending_recovery
            changed = True
        if self._normalize_compile_records_in_state(state):
            changed = True
        return state, changed

    def _build_pending_recovery_metadata(self) -> dict | None:
        pending_recovery = self._extract_pending_recovery(self._state)
        if pending_recovery is None:
            return None
        workspace_state = pending_recovery["workspace_state"]
        graph_model = GraphModel.model_validate(workspace_state["graph_document"])
        graph_document_meta = workspace_state.get("graph_document_meta", {})
        return {
            "status": "pending",
            "project_id": pending_recovery["project_id"],
            "project_name": pending_recovery["project_name"],
            "project_file_path": pending_recovery["project_file_path"],
            "node_count": len(graph_model.nodes),
            "edge_count": len(graph_model.edges),
            "graph_document_save_revision": graph_document_meta.get("save_revision", 0),
            "graph_document_saved_at": graph_document_meta.get("saved_at"),
        }

    def _get_recent_projects(self) -> list[dict]:
        return self._extract_recent_projects(self._state)

    def _extract_recent_projects(self, state: dict | None) -> list[dict]:
        raw_items = state.get("recent_projects") if isinstance(state, dict) else None
        if not isinstance(raw_items, list):
            return []
        normalized_items: list[dict] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            project_name = item.get("project_name")
            project_path = item.get("project_path")
            if not isinstance(project_name, str) or not project_name.strip():
                continue
            if not isinstance(project_path, str) or not project_path.strip():
                continue
            normalized_items.append(
                {
                    "project_name": project_name.strip(),
                    "project_path": str(Path(project_path).resolve()),
                }
            )
        return normalized_items[: self._get_recent_project_limit()]

    def _resolve_project_path(self, project_path: str | Path) -> Path:
        if isinstance(project_path, Path):
            candidate = project_path
        elif isinstance(project_path, str) and project_path.strip():
            candidate = Path(project_path.strip())
        else:
            raise ValueError("project_path must be a non-empty path")
        return candidate.resolve()

    def _resolve_project_directory(self, project_directory: str | Path) -> Path:
        if isinstance(project_directory, Path):
            candidate = project_directory
        elif isinstance(project_directory, str) and project_directory.strip():
            candidate = Path(project_directory.strip())
        else:
            raise ValueError("project_directory must be a non-empty path")
        return candidate.resolve()

    def _get_default_project_directory(self) -> Path | None:
        preferences = self._preferences_service.get_preferences_document()
        program_settings = preferences.get("program_settings")
        if not isinstance(program_settings, dict):
            return None
        default_project_directory = program_settings.get("default_project_directory")
        if not isinstance(default_project_directory, str) or not default_project_directory.strip():
            return None
        return self._resolve_project_directory(default_project_directory)

    def _get_graph_preferences(self) -> dict:
        preferences = self._preferences_service.get_preferences_document()
        graph_settings = preferences.get("graph_settings")
        if not isinstance(graph_settings, dict):
            return {
                "auto_sync_mode": "responsive",
                "save_conflict_policy": "prefer_current_graph",
                "show_node_id_on_node": True,
                "show_disabled_resource_badge": True,
                "snap_to_grid": True,
                "grid_enabled": True,
                "auto_open_node_on_drop": True,
                "confirm_delete_node": True,
                "show_inline_config_summary": True,
            }
        return {
            "auto_sync_mode": graph_settings.get("auto_sync_mode", "responsive"),
            "save_conflict_policy": graph_settings.get(
                "save_conflict_policy",
                "prefer_current_graph",
            ),
            "show_node_id_on_node": graph_settings.get("show_node_id_on_node", True),
            "show_disabled_resource_badge": graph_settings.get(
                "show_disabled_resource_badge",
                True,
            ),
            "snap_to_grid": graph_settings.get("snap_to_grid", True),
            "grid_enabled": graph_settings.get("grid_enabled", True),
            "auto_open_node_on_drop": graph_settings.get("auto_open_node_on_drop", True),
            "confirm_delete_node": graph_settings.get("confirm_delete_node", True),
            "show_inline_config_summary": graph_settings.get(
                "show_inline_config_summary",
                True,
            ),
        }

    def _build_runtime_execution_settings(self) -> dict:
        preferences = self._preferences_service.get_preferences_document()
        security_settings = preferences.get("security_settings")
        python_runtime_settings = preferences.get("python_runtime_settings")
        return {
            "confirm_high_risk_actions": (
                security_settings.get("confirm_high_risk_actions", True)
                if isinstance(security_settings, dict)
                else True
            ),
            "allow_file_access": (
                security_settings.get("allow_file_access", True)
                if isinstance(security_settings, dict)
                else True
            ),
            "allow_external_programs": (
                security_settings.get("allow_external_programs", False)
                if isinstance(security_settings, dict)
                else False
            ),
            "allow_browser_executor": (
                security_settings.get("allow_browser_executor", False)
                if isinstance(security_settings, dict)
                else False
            ),
            "allow_local_network_access": (
                security_settings.get("allow_local_network_access", False)
                if isinstance(security_settings, dict)
                else False
            ),
            "python_timeout_seconds": (
                python_runtime_settings.get("timeout_seconds", 60)
                if isinstance(python_runtime_settings, dict)
                else 60
            ),
            "python_sandbox_mode": (
                python_runtime_settings.get("sandbox_mode", "restricted")
                if isinstance(python_runtime_settings, dict)
                else "restricted"
            ),
            "python_executable_path": (
                python_runtime_settings.get("python_executable_path")
                if isinstance(python_runtime_settings, dict)
                else None
            ),
            "capture_stdout_stderr": (
                python_runtime_settings.get("capture_stdout_stderr", True)
                if isinstance(python_runtime_settings, dict)
                else True
            ),
        }

    def _build_preferences_state(self) -> dict:
        preferences = self._preferences_service.get_preferences_document()
        return {
            "program_settings": {
                "language": "stored_only",
                "resource_language": "stored_only",
                "theme": "stored_only",
                "default_window_size": "active",
                "startup_action": "stored_only",
                "default_project_directory": "active",
                "recent_project_limit": "active",
                "preferences_auto_save": "active",
                "font_scale": "stored_only",
            },
            "compile_settings": {
                "default_source_kind": "stored_only",
                "diagnostic_level": "stored_only",
                "block_on_disabled_components": "stored_only",
                "allow_degraded_compile": "stored_only",
                "stop_on_first_error": "stored_only",
                "emit_runtime_plan": "stored_only",
                "emit_debug_plan": "stored_only",
            },
            "security_settings": {
                "confirm_high_risk_actions": "stored_only",
                "allow_external_programs": "active",
                "allow_file_access": "active",
                "allow_browser_executor": "active",
                "allow_local_network_access": "active",
            },
            "python_runtime_settings": {
                "python_executable_path": "active",
                "timeout_seconds": "active",
                "sandbox_mode": "active",
                "capture_stdout_stderr": "active",
            },
            "graph_settings": {
                "auto_sync_mode": "active",
                "save_conflict_policy": "active",
                "show_node_id_on_node": "active",
                "show_disabled_resource_badge": "active",
                "snap_to_grid": "active",
                "grid_enabled": "active",
                "auto_open_node_on_drop": "active",
                "confirm_delete_node": "active",
                "show_inline_config_summary": "active",
            },
            "other_settings": {
                "workspace_draft_recovery_enabled": "stored_only",
                "workspace_draft_recovery_ttl_minutes": "stored_only",
            },
            "preferences_file_version": preferences.get("preferences_file_version"),
        }

    def _get_graph_save_conflict_policy(self) -> str:
        graph_preferences = self._get_graph_preferences()
        policy = graph_preferences.get("save_conflict_policy")
        if policy == "strict":
            return "strict"
        return "prefer_current_graph"

    def _save_project_to_path(self, project_path: Path) -> dict:
        serialized_path = str(project_path.resolve())
        self._write_project_storage_layout(project_path)

        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            current_state["project"]["workspace_root"] = str(project_path.parent)
            current_state["project_runtime"] = {
                "project_file_path": serialized_path,
                "is_dirty": False,
            }
            current_state["recent_projects"] = self._upsert_recent_project_record(
                self._extract_recent_projects(current_state),
                project_name=current_state["project"]["project_name"],
                project_path=project_path,
            )
            return current_state

        self._state = self._state_store.mutate(mutation)
        graph_model = self._get_graph_document_model()
        return {
            "status": "saved",
            "project": self._build_project_metadata(),
            "graph_document": graph_model,
        }

    def _build_project_file_document(self, project_path: Path) -> dict:
        return self._build_legacy_project_file_document(project_path)

    def _build_legacy_project_file_document(self, project_path: Path) -> dict:
        graph_model = self._get_graph_document_model()
        graph_document_meta = self._get_graph_document_meta()
        raw_project = self._state.get("project")
        if not isinstance(raw_project, dict):
            raw_project = self._build_initial_workspace_state()["project"]
        project_document = dict(raw_project)
        project_document["workspace_root"] = str(project_path.parent)
        return {
            "project_file_schema_version": PROJECT_FILE_SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "project": project_document,
            "resource_registry": self._get_resource_registry(),
            "editor_history": self._get_editor_history(),
            "execution_history": self._get_execution_history(),
            "graph_document": graph_model.model_dump(),
            "graph_document_meta": graph_document_meta,
        }

    def _build_project_storage_layout(self, project_path: Path) -> dict:
        resources = self._get_resource_registry()
        builtin_resource_refs = self._build_builtin_resource_refs(resources)
        project_resource_refs = self._build_project_resource_refs(resources, project_path=project_path)
        return {
            "project_manifest": self._build_project_manifest_document(
                project_path,
                builtin_resource_refs=builtin_resource_refs,
                project_resource_refs=project_resource_refs,
            ),
            "graph_document": self._get_graph_document_model().model_dump(),
            "project_owned_resources_index": self._build_project_owned_resource_index(
                resources,
                project_path=project_path,
            ),
            "resource_overrides": self._build_resource_overrides_document(resources),
        }

    def _write_project_storage_layout(self, project_path: Path) -> None:
        layout = self._build_project_storage_layout(project_path)
        graph_document = layout["graph_document"]
        project_owned_resources_index = layout["project_owned_resources_index"]
        resource_overrides = layout["resource_overrides"]
        project_manifest = layout["project_manifest"]

        project_path.parent.mkdir(parents=True, exist_ok=True)
        storage_root = self._resolve_project_storage_root(project_path)
        graphs_dir = storage_root / "graphs"
        resources_dir = storage_root / "resources"
        graphs_dir.mkdir(parents=True, exist_ok=True)
        resources_dir.mkdir(parents=True, exist_ok=True)

        self._write_json_file(graphs_dir / "workspace.graph.json", graph_document)
        written_resources = self._write_project_owned_resources(project_path, self._get_resource_registry())
        self._cleanup_stale_project_owned_resource_directories(
            project_path,
            written_resources,
        )
        self._write_json_file(resources_dir / "index.json", project_owned_resources_index)
        self._write_json_file(storage_root / "resource-overrides.json", resource_overrides)
        self._write_json_file(project_path, project_manifest)

    def _build_project_manifest_document(
        self,
        project_path: Path,
        *,
        builtin_resource_refs: list[dict],
        project_resource_refs: list[dict],
    ) -> dict:
        graph_document_meta = self._get_graph_document_meta()
        raw_project = self._state.get("project")
        if not isinstance(raw_project, dict):
            raw_project = self._build_initial_workspace_state()["project"]
        project_document = dict(raw_project)
        project_document["workspace_root"] = str(project_path.parent)
        project_document["project_schema_version"] = "project-v2"
        project_document["main_graph_path"] = f"{self._project_storage_directory_name(project_path)}/graphs/workspace.graph.json"
        project_document["project_resources_index_path"] = (
            f"{self._project_storage_directory_name(project_path)}/resources/index.json"
        )
        project_document["resource_overrides_path"] = (
            f"{self._project_storage_directory_name(project_path)}/resource-overrides.json"
        )
        return {
            "project_file_schema_version": PROJECT_FILE_SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "project": project_document,
            "builtin_resource_refs": builtin_resource_refs,
            "project_resource_refs": project_resource_refs,
            "editor_history": self._get_editor_history(),
            "execution_history": self._get_execution_history(),
            "graph_document_meta": graph_document_meta,
        }

    def _build_builtin_resource_refs(self, resources: list[dict]) -> list[dict]:
        refs: list[dict] = []
        for resource in resources:
            if resource.get("resource_type") != "builtin_component":
                continue
            refs.append(
                {
                    "resource_id": resource["resource_id"],
                    "resource_key": resource["resource_key"],
                    "resource_type": resource["resource_type"],
                    "origin": resource.get("origin", "builtin"),
                    "implementation_kind": resource.get("implementation_kind", "core_atomic"),
                    "compatibility_aliases": list(resource.get("compatibility_aliases", [])),
                    "definition_version": "builtin-registry-v1",
                }
            )
        return refs

    def _build_project_resource_refs(self, resources: list[dict], *, project_path: Path) -> list[dict]:
        refs: list[dict] = []
        storage_directory = self._project_storage_directory_name(project_path)
        for resource in resources:
            normalized_resource = self._normalize_project_storage_resource_record(resource)
            if normalized_resource is None:
                continue
            if normalized_resource.get("resource_type") != "custom_node_graph":
                continue
            directory_name = self._project_resource_directory_name(
                normalized_resource["resource_id"]
            )
            base_directory = self._project_resource_base_directory_name(normalized_resource)
            refs.append(
                {
                    "resource_id": normalized_resource["resource_id"],
                    "source_ref": f"{storage_directory}/resources/{base_directory}/{directory_name}",
                }
            )
        return refs

    def _build_project_owned_resource_index(
        self, resources: list[dict], *, project_path: Path
    ) -> dict:
        return {
            "project_resources_schema_version": 1,
            "resources": self._build_project_owned_resource_index_items(
                resources, project_path=project_path
            ),
        }

    def _build_project_owned_resource_index_items(
        self, resources: list[dict], project_path: Path | None
    ) -> list[dict]:
        items: list[dict] = []
        storage_prefix = ""
        if project_path is not None:
            storage_prefix = f"{self._project_storage_directory_name(project_path)}/"
        for resource in resources:
            normalized_resource = self._normalize_project_storage_resource_record(resource)
            if normalized_resource is None:
                continue
            if normalized_resource.get("resource_type") != "custom_node_graph":
                continue
            directory_name = self._project_resource_directory_name(normalized_resource["resource_id"])
            base_directory = self._project_resource_base_directory_name(normalized_resource)
            relative_directory = f"{storage_prefix}resources/{base_directory}/{directory_name}"
            items.append(
                {
                    "resource_id": normalized_resource["resource_id"],
                    "resource_key": normalized_resource["resource_key"],
                    "resource_type": normalized_resource["resource_type"],
                    "origin": normalized_resource.get("origin", "project"),
                    "implementation_kind": normalized_resource.get(
                        "implementation_kind", "project_component"
                    ),
                    "display_name": normalized_resource["display_name"],
                    "source_ref": relative_directory,
                    "manifest_path": f"{relative_directory}/manifest.json",
                    "graph_path": f"{relative_directory}/graph.json",
                    "enabled_by_default": True,
                    "compatibility_aliases": list(
                        normalized_resource.get("compatibility_aliases", [])
                    ),
                }
            )
        return items

    def _write_project_owned_resources(self, project_path: Path, resources: list[dict]) -> list[dict]:
        normalized_resources: list[dict] = []
        storage_root = self._resolve_project_storage_root(project_path)
        for resource in resources:
            normalized_resource = self._normalize_project_storage_resource_record(resource)
            if normalized_resource is None:
                continue
            if normalized_resource.get("resource_type") != "custom_node_graph":
                continue
            directory_name = self._project_resource_directory_name(normalized_resource["resource_id"])
            base_directory = self._project_resource_base_directory_name(normalized_resource)
            resource_dir = storage_root / "resources" / base_directory / directory_name
            resource_dir.mkdir(parents=True, exist_ok=True)
            self._write_json_file(
                resource_dir / "manifest.json",
                self._build_project_resource_manifest(normalized_resource),
            )
            self._write_json_file(
                resource_dir / "graph.json",
                self._build_project_resource_graph_document(normalized_resource),
            )
            normalized_resources.append(normalized_resource)
        return normalized_resources

    def _cleanup_stale_project_owned_resource_directories(
        self,
        project_path: Path,
        resources: list[dict],
    ) -> None:
        storage_root = self._resolve_project_storage_root(project_path)
        resources_root = storage_root / "resources"
        if not resources_root.exists():
            return
        expected_directories = {
            (
                self._project_resource_base_directory_name(resource),
                self._project_resource_directory_name(resource["resource_id"]),
            )
            for resource in resources
        }
        for base_directory in resources_root.iterdir():
            if not base_directory.is_dir():
                continue
            for resource_directory in base_directory.iterdir():
                if not resource_directory.is_dir():
                    continue
                directory_key = (base_directory.name, resource_directory.name)
                if directory_key not in expected_directories:
                    shutil.rmtree(resource_directory, ignore_errors=True)
            if not any(base_directory.iterdir()):
                base_directory.rmdir()

    def _build_project_resource_manifest(self, resource: dict) -> dict:
        return {
            "resource_manifest_schema_version": 1,
            "resource_id": resource["resource_id"],
            "resource_key": resource["resource_key"],
            "resource_type": resource["resource_type"],
            "origin": resource.get("origin", "project"),
            "implementation_kind": resource.get("implementation_kind", "project_component"),
            "display_name": resource["display_name"],
            "display_name_i18n": deepcopy(resource.get("display_name_i18n", {})),
            "description": resource.get("description"),
            "description_i18n": deepcopy(resource.get("description_i18n", {})),
            "compatibility_aliases": list(resource.get("compatibility_aliases", [])),
            "input_schema": deepcopy(resource.get("input_schema", {})),
            "output_schema": deepcopy(resource.get("output_schema", {})),
            "graph_document_id": resource.get("source_graph_document_id"),
            "graph_document_save_revision": resource.get("source_graph_document_save_revision"),
        }

    def _build_project_resource_graph_document(self, resource: dict) -> dict:
        source_graph_document = resource.get("source_graph_document")
        if not isinstance(source_graph_document, dict):
            return create_empty_graph_model("graph:workspace", None).model_dump()
        return deepcopy(source_graph_document)

    def _normalize_project_storage_resource_record(self, resource: dict | None) -> dict | None:
        normalized = self._normalize_resource_record(resource)
        if normalized is None:
            return None
        resource_type = normalized.get("resource_type")
        if resource_type == "user_component":
            next_resource = deepcopy(normalized)
            compatibility_aliases = set(next_resource.get("compatibility_aliases", []))
            compatibility_aliases.update(
                alias
                for alias in {
                    next_resource.get("resource_id"),
                    next_resource.get("resource_key"),
                }
                if isinstance(alias, str) and alias.strip()
            )
            legacy_resource_id = next_resource["resource_id"]
            suffix = legacy_resource_id.split(":", 1)[1] if ":" in legacy_resource_id else legacy_resource_id
            next_resource["resource_type"] = "custom_node_graph"
            next_resource["resource_id"] = f"{CUSTOM_NODE_GRAPH_RESOURCE_PREFIX}{suffix}"
            next_resource["resource_key"] = next_resource["resource_id"]
            next_resource["compatibility_aliases"] = sorted(
                {
                    alias.strip()
                    for alias in compatibility_aliases
                    if isinstance(alias, str) and alias.strip()
                }
            )
            return next_resource
        return normalized

    def _build_resource_overrides_document(self, resources: list[dict]) -> dict:
        overrides: dict[str, dict] = {}
        for resource in resources:
            normalized_resource = self._normalize_project_storage_resource_record(resource)
            if normalized_resource is None:
                continue
            overrides[normalized_resource["resource_id"]] = self._extract_resource_override_record(
                normalized_resource
            )
        return {
            "resource_overrides_schema_version": 1,
            "resources": overrides,
        }

    def _extract_resource_override_record(self, resource: dict) -> dict:
        source_graph_document = resource.get("source_graph_document")
        root_metadata = (
            source_graph_document.get("root_metadata")
            if isinstance(source_graph_document, dict)
            else None
        )
        return {
            "enabled": bool(resource.get("enabled", True)),
            "tags": self._extract_user_resource_tags(resource),
            "category_group_path": list(resource.get("category_group_path", [])),
            "display_name_i18n": deepcopy(resource.get("display_name_i18n", {})),
            "description_i18n": deepcopy(resource.get("description_i18n", {})),
            "default_node_config_override": deepcopy(
                root_metadata.get("default_node_config_override", {})
                if isinstance(root_metadata, dict)
                else {}
            ),
        }

    def _project_resource_directory_name(self, resource_id: str) -> str:
        return resource_id.replace(":", "_")

    def _project_resource_base_directory_name(self, resource: dict) -> str:
        if resource.get("resource_type") == "custom_node_graph":
            return "custom-node-graphs"
        return "components"

    def _project_storage_directory_name(self, project_path: Path) -> str:
        return f"{project_path.stem}.data"

    def _resolve_project_storage_root(self, project_path: Path) -> Path:
        return project_path.parent / self._project_storage_directory_name(project_path)

    def _write_json_file(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json_file(self, path: Path) -> dict:
        if not path.exists():
            raise ValueError(f"json file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"json file must be valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"json file must be a JSON object: {path}")
        return payload

    def _write_project_file(self, project_path: Path, payload: dict) -> None:
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_project_owned_resources_from_index(
        self, project_path: Path, index_payload: dict
    ) -> tuple[list[dict], list[dict]]:
        resources = index_payload.get("resources")
        if not isinstance(resources, list):
            raise ValueError(
                f"project resources index must contain array: resources ({project_path})"
            )
        loaded_resources: list[dict] = []
        issues: list[dict] = []
        for resource_ref in resources:
            if not isinstance(resource_ref, dict):
                continue
            loaded_resource, resource_issues = self._load_single_project_owned_resource(
                project_path, resource_ref
            )
            loaded_resources.append(loaded_resource)
            issues.extend(resource_issues)
        return loaded_resources, issues

    def _load_single_project_owned_resource(
        self, project_path: Path, resource_ref: dict
    ) -> tuple[dict, list[dict]]:
        manifest_path = resource_ref.get("manifest_path")
        graph_path = resource_ref.get("graph_path")
        resource_id = resource_ref.get("resource_id")
        resource_key = resource_ref.get("resource_key")
        display_name = resource_ref.get("display_name")
        if not isinstance(manifest_path, str) or not manifest_path.strip():
            raise ValueError(f"project resource missing manifest_path ({project_path})")
        if not isinstance(graph_path, str) or not graph_path.strip():
            raise ValueError(f"project resource missing graph_path ({project_path})")
        manifest_abspath = project_path.parent / manifest_path
        graph_abspath = project_path.parent / graph_path
        issues: list[dict] = []
        manifest_payload = None
        graph_payload = None
        if manifest_abspath.exists():
            manifest_payload = self._read_json_file(manifest_abspath)
        else:
            issues.append(
                {
                    "category": "project.resource.manifest_missing",
                    "message": f"project resource manifest file not found: {manifest_path}",
                    "resource_id": resource_id,
                    "path": str(manifest_abspath.resolve()),
                }
            )
        if graph_abspath.exists():
            graph_payload = self._read_json_file(graph_abspath)
        else:
            issues.append(
                {
                    "category": "project.resource.graph_missing",
                    "message": f"project resource graph file not found: {graph_path}",
                    "resource_id": resource_id,
                    "path": str(graph_abspath.resolve()),
                }
            )
        if isinstance(manifest_payload, dict) and isinstance(graph_payload, dict):
            return (
                {
                    "resource_id": manifest_payload["resource_id"],
                    "resource_type": manifest_payload["resource_type"],
                    "display_name": manifest_payload["display_name"],
                    "display_name_i18n": manifest_payload.get("display_name_i18n", {}),
                    "resource_key": manifest_payload.get(
                        "resource_key", manifest_payload["resource_id"]
                    ),
                    "enabled": resource_ref.get("enabled_by_default", True),
                    "origin": manifest_payload.get("origin", "project"),
                    "description": manifest_payload.get("description"),
                    "description_i18n": manifest_payload.get("description_i18n", {}),
                    "implementation_kind": manifest_payload.get(
                        "implementation_kind", "project_component"
                    ),
                    "compatibility_aliases": manifest_payload.get("compatibility_aliases", []),
                    "source_graph_document_id": manifest_payload.get("graph_document_id"),
                    "source_graph_document_save_revision": manifest_payload.get(
                        "graph_document_save_revision"
                    ),
                    "source_graph_document": graph_payload,
                    "input_schema": manifest_payload.get("input_schema", {}),
                    "output_schema": manifest_payload.get("output_schema", {}),
                    "tags": manifest_payload.get("tags", []),
                },
                issues,
            )
        placeholder_resource_id = (
            resource_id.strip()
            if isinstance(resource_id, str) and resource_id.strip()
            else (
                resource_key.strip()
                if isinstance(resource_key, str) and resource_key.strip()
                else f"{CUSTOM_NODE_GRAPH_RESOURCE_PREFIX}missing-{uuid.uuid4().hex[:8]}"
            )
        )
        placeholder_resource_key = (
            resource_key.strip()
            if isinstance(resource_key, str) and resource_key.strip()
            else placeholder_resource_id
        )
        placeholder_display_name = (
            display_name.strip()
            if isinstance(display_name, str) and display_name.strip()
            else placeholder_resource_id
        )
        return (
            {
                "resource_id": placeholder_resource_id,
                "resource_type": "custom_node_graph",
                "display_name": placeholder_display_name,
                "display_name_i18n": {"en-US": placeholder_display_name},
                "resource_key": placeholder_resource_key,
                "enabled": False,
                "origin": "project",
                "description": None,
                "description_i18n": {},
                "implementation_kind": "project_component",
                "compatibility_aliases": [],
                "source_graph_document_id": None,
                "source_graph_document_save_revision": None,
                "source_graph_document": (
                    graph_payload
                    if isinstance(graph_payload, dict)
                    else create_empty_graph_model("graph:workspace", None).model_dump()
                ),
                "input_schema": {},
                "output_schema": {},
                "tags": ["project:broken-resource"],
            },
            issues,
        )

    def _load_resource_overrides(self, project_path: Path, relative_path: str) -> dict:
        payload = self._read_json_file(project_path.parent / relative_path)
        resources = payload.get("resources")
        if not isinstance(resources, dict):
            raise ValueError(
                f"resource overrides file must contain object: resources ({project_path})"
            )
        return resources

    def _compose_effective_resource_registry(
        self,
        *,
        builtin_resource_refs: list[dict],
        project_resources: list[dict],
        resource_overrides: dict,
    ) -> list[dict]:
        builtin_by_id = {
            item["resource_id"]: deepcopy(item)
            for item in self._build_initial_resource_registry()
        }
        effective_resources: list[dict] = []
        requested_builtin_ids = {
            item.get("resource_id")
            for item in builtin_resource_refs
            if isinstance(item, dict) and isinstance(item.get("resource_id"), str)
        }
        if requested_builtin_ids:
            for resource_id in requested_builtin_ids:
                builtin = builtin_by_id.get(resource_id)
                if builtin is not None:
                    effective_resources.append(builtin)
        else:
            effective_resources.extend(deepcopy(list(builtin_by_id.values())))
        effective_resources.extend(deepcopy(project_resources))

        merged_resources: list[dict] = []
        for resource in effective_resources:
            override = resource_overrides.get(resource.get("resource_id"))
            merged_resources.append(self._apply_resource_override(resource, override))
        return self._extract_resource_registry({"resource_registry": merged_resources})

    def _apply_resource_override(self, resource: dict, override: object) -> dict:
        if not isinstance(override, dict):
            return resource
        updated_resource = dict(resource)
        if "enabled" in override:
            updated_resource["enabled"] = bool(override.get("enabled"))
        if "display_name_i18n" in override and isinstance(override.get("display_name_i18n"), dict):
            updated_resource["display_name_i18n"] = deepcopy(override["display_name_i18n"])
        if "description_i18n" in override and isinstance(override.get("description_i18n"), dict):
            updated_resource["description_i18n"] = deepcopy(override["description_i18n"])
        if "tags" in override:
            updated_resource["tags"] = self._normalize_user_tags(override.get("tags"))
        source_graph_document = updated_resource.get("source_graph_document")
        if isinstance(source_graph_document, dict):
            root_metadata = source_graph_document.get("root_metadata")
            if not isinstance(root_metadata, dict):
                root_metadata = {}
            if "default_node_config_override" in override and isinstance(
                override.get("default_node_config_override"), dict
            ):
                root_metadata["default_node_config_override"] = deepcopy(
                    override["default_node_config_override"]
                )
            if "tags" in override:
                root_metadata["resource_tags"] = self._normalize_user_tags(override.get("tags"))
            source_graph_document["root_metadata"] = root_metadata
            updated_resource["source_graph_document"] = source_graph_document
        return updated_resource

    def _extract_user_resource_tags(self, resource: dict) -> list[str]:
        user_tags = {
            tag
            for tag in self._normalize_user_tags(resource.get("tags"))
            if not (
                tag.startswith("type:")
                or tag.startswith("origin:")
                or tag.startswith("status:")
                or tag.startswith("taxonomy:")
                or tag.startswith("semantic:")
                or tag.startswith("domain:")
            )
        }
        source_graph_document = resource.get("source_graph_document")
        root_metadata = (
            source_graph_document.get("root_metadata")
            if isinstance(source_graph_document, dict)
            else None
        )
        if isinstance(root_metadata, dict):
            user_tags.update(self._normalize_user_tags(root_metadata.get("resource_tags")))
        return sorted(user_tags)

    def _read_project_file(self, project_path: Path) -> dict:
        if not project_path.exists():
            raise ValueError(f"project file not found: {project_path}")
        try:
            payload = json.loads(project_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"project file must be valid JSON: {project_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"project file must be a JSON object: {project_path}")
        schema_version = payload.get("project_file_schema_version")
        if schema_version == LEGACY_PROJECT_FILE_SCHEMA_VERSION:
            return self._read_legacy_project_file(project_path, payload)
        if schema_version != PROJECT_FILE_SCHEMA_VERSION:
            raise ValueError(
                "project file schema version mismatch: "
                f"expected {PROJECT_FILE_SCHEMA_VERSION}, got "
                f"{schema_version!r}"
            )
        return self._read_split_project_file(project_path, payload)

    def _read_legacy_project_file(self, project_path: Path, payload: dict) -> dict:
        raw_project = payload.get("project")
        raw_resource_registry = payload.get("resource_registry")
        raw_editor_history = payload.get("editor_history")
        raw_execution_history = payload.get("execution_history")
        raw_graph_document = payload.get("graph_document")
        raw_graph_document_meta = payload.get("graph_document_meta")
        if not isinstance(raw_project, dict):
            raise ValueError(f"project file missing required object: project ({project_path})")
        if raw_resource_registry is None:
            raw_resource_registry = self._build_initial_resource_registry()
        if raw_editor_history is None:
            raw_editor_history = {"undo_stack": [], "redo_stack": []}
        if raw_execution_history is None:
            raw_execution_history = {"runtime_runs": [], "debug_sessions": []}
        if not isinstance(raw_graph_document, dict):
            raise ValueError(f"project file missing required object: graph_document ({project_path})")
        if not isinstance(raw_graph_document_meta, dict):
            raw_graph_document_meta = {"save_revision": 0, "saved_at": None}
        normalized_state = self._build_initial_workspace_state(
            project_name=raw_project.get("project_name", "Opened Project"),
            project_id=raw_project.get("project_id"),
            project_file_path=project_path,
            mark_project_dirty=False,
        )
        normalized_project = dict(normalized_state["project"])
        normalized_project.update(raw_project)
        normalized_project["workspace_root"] = str(project_path.parent)
        graph_model = GraphModel.model_validate(raw_graph_document)
        graph_document_meta = {
            "save_revision": (
                raw_graph_document_meta.get("save_revision")
                if isinstance(raw_graph_document_meta.get("save_revision"), int)
                else 0
            ),
            "saved_at": (
                raw_graph_document_meta.get("saved_at")
                if isinstance(raw_graph_document_meta.get("saved_at"), str)
                or raw_graph_document_meta.get("saved_at") is None
                else None
            ),
        }
        return {
            "project": normalized_project,
            "resource_registry": self._extract_resource_registry(
                {"resource_registry": raw_resource_registry}
            ),
            "editor_history": self._extract_editor_history({"editor_history": raw_editor_history}),
            "execution_history": self._extract_execution_history(
                {"execution_history": raw_execution_history}
            ),
            "graph_document": graph_model.model_dump(),
            "graph_document_meta": graph_document_meta,
        }

    def _read_split_project_file(self, project_path: Path, payload: dict) -> dict:
        raw_project = payload.get("project")
        raw_builtin_resource_refs = payload.get("builtin_resource_refs")
        raw_editor_history = payload.get("editor_history")
        raw_execution_history = payload.get("execution_history")
        raw_graph_document_meta = payload.get("graph_document_meta")
        if not isinstance(raw_project, dict):
            raise ValueError(f"project file missing required object: project ({project_path})")
        if not isinstance(raw_builtin_resource_refs, list):
            raw_builtin_resource_refs = []
        if raw_editor_history is None:
            raw_editor_history = {"undo_stack": [], "redo_stack": []}
        if raw_execution_history is None:
            raw_execution_history = {"runtime_runs": [], "debug_sessions": []}
        if not isinstance(raw_graph_document_meta, dict):
            raw_graph_document_meta = {"save_revision": 0, "saved_at": None}

        normalized_state = self._build_initial_workspace_state(
            project_name=raw_project.get("project_name", "Opened Project"),
            project_id=raw_project.get("project_id"),
            project_file_path=project_path,
            mark_project_dirty=False,
        )
        normalized_project = dict(normalized_state["project"])
        normalized_project.update(raw_project)
        normalized_project["workspace_root"] = str(project_path.parent)

        main_graph_path = raw_project.get("main_graph_path")
        if not isinstance(main_graph_path, str) or not main_graph_path.strip():
            raise ValueError(f"project file missing required string: project.main_graph_path ({project_path})")
        graph_document_payload = self._read_json_file(project_path.parent / main_graph_path)
        graph_model = GraphModel.model_validate(graph_document_payload)

        graph_document_meta = {
            "save_revision": (
                raw_graph_document_meta.get("save_revision")
                if isinstance(raw_graph_document_meta.get("save_revision"), int)
                else 0
            ),
            "saved_at": (
                raw_graph_document_meta.get("saved_at")
                if isinstance(raw_graph_document_meta.get("saved_at"), str)
                or raw_graph_document_meta.get("saved_at") is None
                else None
            ),
        }

        resources_index_path = raw_project.get("project_resources_index_path")
        if not isinstance(resources_index_path, str) or not resources_index_path.strip():
            raise ValueError(
                f"project file missing required string: project.project_resources_index_path ({project_path})"
            )
        resource_index_payload = self._read_json_file(project_path.parent / resources_index_path)
        project_resources, project_resource_load_issues = self._load_project_owned_resources_from_index(
            project_path, resource_index_payload
        )

        resource_overrides_path = raw_project.get("resource_overrides_path")
        if not isinstance(resource_overrides_path, str) or not resource_overrides_path.strip():
            raise ValueError(
                f"project file missing required string: project.resource_overrides_path ({project_path})"
            )
        resource_overrides = self._load_resource_overrides(project_path, resource_overrides_path)
        effective_registry = self._compose_effective_resource_registry(
            builtin_resource_refs=raw_builtin_resource_refs,
            project_resources=project_resources,
            resource_overrides=resource_overrides,
        )
        for issue in project_resource_load_issues:
            issue_resource_id = issue.get("resource_id")
            if not isinstance(issue_resource_id, str) or not issue_resource_id.strip():
                continue
            for resource in effective_registry:
                if resource.get("resource_id") == issue_resource_id:
                    resource["enabled"] = False
                    tags = {
                        tag
                        for tag in resource.get("tags", [])
                        if isinstance(tag, str) and tag.strip()
                    }
                    tags.add("project:broken-resource")
                    resource["tags"] = sorted(tags)
                    break

        return {
            "project": normalized_project,
            "resource_registry": effective_registry,
            "editor_history": self._extract_editor_history({"editor_history": raw_editor_history}),
            "execution_history": self._extract_execution_history(
                {"execution_history": raw_execution_history}
            ),
            "graph_document": graph_model.model_dump(),
            "graph_document_meta": graph_document_meta,
        }

    def _build_project_resource_audit_document(self, project_path: Path) -> dict:
        resolved_project_path = project_path.resolve()
        project_manifest = self._read_json_file(resolved_project_path)
        raw_project = project_manifest.get("project")
        if not isinstance(raw_project, dict):
            raise ValueError(f"project file missing required object: project ({resolved_project_path})")
        resources_index_path = raw_project.get("project_resources_index_path")
        if not isinstance(resources_index_path, str) or not resources_index_path.strip():
            raise ValueError(
                f"project file missing required string: project.project_resources_index_path ({resolved_project_path})"
            )
        resources_index_payload = self._read_json_file(
            resolved_project_path.parent / resources_index_path
        )
        resources = resources_index_payload.get("resources")
        if not isinstance(resources, list):
            raise ValueError(
                f"project resources index must contain array: resources ({resolved_project_path})"
            )
        issues: list[dict] = []
        resource_entries: list[dict] = []
        for resource_ref in resources:
            if not isinstance(resource_ref, dict):
                continue
            source_ref = resource_ref.get("source_ref")
            manifest_path = resource_ref.get("manifest_path")
            graph_path = resource_ref.get("graph_path")
            resource_issues: list[dict] = []
            if not isinstance(source_ref, str) or not source_ref.strip():
                resource_issues.append(
                    {
                        "category": "project.resource.source_ref_missing",
                        "message": f"project resource source_ref is missing: {resource_ref.get('resource_id')}",
                        "resource_id": resource_ref.get("resource_id"),
                    }
                )
            if not isinstance(manifest_path, str) or not manifest_path.strip():
                resource_issues.append(
                    {
                        "category": "project.resource.manifest_path_missing",
                        "message": f"project resource manifest_path is missing: {resource_ref.get('resource_id')}",
                        "resource_id": resource_ref.get("resource_id"),
                    }
                )
            elif not (resolved_project_path.parent / manifest_path).exists():
                resource_issues.append(
                    {
                        "category": "project.resource.manifest_missing",
                        "message": f"project resource manifest file not found: {manifest_path}",
                        "resource_id": resource_ref.get("resource_id"),
                        "path": str((resolved_project_path.parent / manifest_path).resolve()),
                    }
                )
            if not isinstance(graph_path, str) or not graph_path.strip():
                resource_issues.append(
                    {
                        "category": "project.resource.graph_path_missing",
                        "message": f"project resource graph_path is missing: {resource_ref.get('resource_id')}",
                        "resource_id": resource_ref.get("resource_id"),
                    }
                )
            elif not (resolved_project_path.parent / graph_path).exists():
                resource_issues.append(
                    {
                        "category": "project.resource.graph_missing",
                        "message": f"project resource graph file not found: {graph_path}",
                        "resource_id": resource_ref.get("resource_id"),
                        "path": str((resolved_project_path.parent / graph_path).resolve()),
                    }
                )
            issues.extend(resource_issues)
            status = "healthy" if not resource_issues else resource_issues[0]["category"].removeprefix(
                "project.resource."
            )
            resource_entries.append(
                {
                    "resource_id": resource_ref.get("resource_id"),
                    "resource_key": resource_ref.get("resource_key"),
                    "display_name": resource_ref.get("display_name"),
                    "source_ref": source_ref,
                    "manifest_path": manifest_path,
                    "graph_path": graph_path,
                    "status": status,
                    "issue_categories": [item["category"] for item in resource_issues],
                }
            )
        healthy_count = sum(1 for item in resource_entries if item["status"] == "healthy")
        return {
            "status": "ready",
            "project_file_path": str(resolved_project_path),
            "storage_root": str(self._resolve_project_storage_root(resolved_project_path)),
            "project_file": project_manifest,
            "summary": {
                "resource_count": len(resource_entries),
                "issue_count": len(issues),
                "healthy_count": healthy_count,
            },
            "resources": resource_entries,
            "issues": issues,
        }

    def _upsert_recent_project_record(
        self,
        recent_projects: list[dict],
        *,
        project_name: str,
        project_path: Path,
    ) -> list[dict]:
        serialized_path = str(project_path.resolve())
        next_items = [
            item for item in recent_projects if item.get("project_path") != serialized_path
        ]
        next_items.insert(
            0,
            {
                "project_name": project_name,
                "project_path": serialized_path,
            },
        )
        return next_items[: self._get_recent_project_limit()]

    def _get_recent_project_limit(self) -> int:
        preferences = self._preferences_service.get_preferences_document()
        program_settings = preferences.get("program_settings")
        if not isinstance(program_settings, dict):
            return MAX_RECENT_PROJECTS
        raw_limit = program_settings.get("recent_project_limit")
        if not isinstance(raw_limit, int):
            return MAX_RECENT_PROJECTS
        if raw_limit < 1:
            return 1
        if raw_limit > MAX_RECENT_PROJECTS_LIMIT:
            return MAX_RECENT_PROJECTS_LIMIT
        return raw_limit

    def _build_initial_resource_registry(self) -> list[dict]:
        return build_builtin_resource_registry()

    def _get_resource_registry(self) -> list[dict]:
        return self._extract_resource_registry(self._state)

    def _get_resource_registry_revision(self) -> int:
        raw_project = self._state.get("project")
        if not isinstance(raw_project, dict):
            return 0
        revision = raw_project.get("resource_registry_revision", 0)
        return revision if isinstance(revision, int) else 0

    def _extract_resource_registry(self, state: dict | None) -> list[dict]:
        raw_items = state.get("resource_registry") if isinstance(state, dict) else None
        if not isinstance(raw_items, list):
            raw_items = self._build_initial_resource_registry()
        normalized_items: list[dict] = []
        for item in raw_items:
            normalized = self._normalize_resource_record(item)
            if normalized is not None:
                normalized_items.append(normalized)

        known_ids = {item["resource_id"] for item in normalized_items}
        for builtin in self._build_initial_resource_registry():
            if builtin["resource_id"] not in known_ids:
                normalized_items.append(builtin)
        normalized_items.sort(
            key=lambda item: (
                0 if item["resource_type"] == "builtin_component" else 1,
                item["display_name"],
            )
        )
        return normalized_items

    def _normalize_resource_record(self, item: dict | None) -> dict | None:
        if not isinstance(item, dict):
            return None
        resource_id = item.get("resource_id")
        resource_type = item.get("resource_type")
        display_name = item.get("display_name")
        resource_key = item.get("resource_key")
        if not isinstance(resource_id, str) or not resource_id.strip():
            return None
        if resource_type not in RESOURCE_TYPES:
            return None
        if not isinstance(display_name, str) or not display_name.strip():
            return None
        if not isinstance(resource_key, str) or not resource_key.strip():
            resource_key = resource_id
        compatibility_aliases = list(item.get("compatibility_aliases", []))
        if not isinstance(item.get("compatibility_aliases"), list):
            compatibility_aliases = []

        normalized_resource_id = resource_id.strip()
        normalized_resource_key = resource_key.strip()
        normalized_resource_type = resource_type
        if resource_type == "subgraph_resource":
            normalized_resource_type = "custom_node_graph"
            compatibility_aliases.extend(
                [
                    alias
                    for alias in {normalized_resource_id, normalized_resource_key}
                    if isinstance(alias, str) and alias
                ]
            )
            if normalized_resource_id.startswith(LEGACY_SUBGRAPH_RESOURCE_PREFIX):
                normalized_resource_id = (
                    CUSTOM_NODE_GRAPH_RESOURCE_PREFIX
                    + normalized_resource_id.removeprefix(LEGACY_SUBGRAPH_RESOURCE_PREFIX)
                )
            if normalized_resource_key.startswith(LEGACY_SUBGRAPH_RESOURCE_PREFIX):
                normalized_resource_key = (
                    CUSTOM_NODE_GRAPH_RESOURCE_PREFIX
                    + normalized_resource_key.removeprefix(LEGACY_SUBGRAPH_RESOURCE_PREFIX)
                )
        normalized = {
            "resource_id": normalized_resource_id,
            "resource_type": normalized_resource_type,
            "display_name": display_name.strip(),
            "display_name_i18n": self._normalize_i18n_field(item.get("display_name_i18n")),
            "resource_key": normalized_resource_key,
            "enabled": bool(item.get("enabled", True)),
            "origin": item.get(
                "origin",
                "builtin" if normalized_resource_type == "builtin_component" else "project",
            ),
            "description": item.get("description"),
            "description_i18n": self._normalize_i18n_field(item.get("description_i18n")),
            "implementation_kind": item.get(
                "implementation_kind",
                (
                    "core_atomic"
                    if normalized_resource_type == "builtin_component"
                    else "project_component"
                ),
            ),
            "compatibility_aliases": sorted(
                {
                    alias.strip()
                    for alias in compatibility_aliases
                    if isinstance(alias, str) and alias.strip()
                }
            ),
        }
        capability_domain = item.get("capability_domain")
        if isinstance(capability_domain, str) and capability_domain.strip():
            normalized["capability_domain"] = capability_domain.strip()
        if normalized["display_name_i18n"].get("en-US") is None:
            normalized["display_name_i18n"]["en-US"] = normalized["display_name"]
        if isinstance(normalized.get("description"), str) and normalized["description"].strip():
            normalized["description_i18n"].setdefault("en-US", normalized["description"].strip())
        normalized.update(self._infer_resource_visibility_metadata(normalized, item))
        normalized["category_path"] = self._build_resource_category_path(
            normalized=normalized,
            raw_item=item,
        )
        normalized["category_group_path"] = self._build_resource_category_group_path(
            normalized=normalized
        )
        normalized["category_group_label"] = self._build_resource_category_group_label(
            normalized=normalized
        )
        normalized["search_tokens"] = self._build_resource_search_tokens(
            normalized=normalized,
            raw_item=item,
        )
        if normalized_resource_type in {"user_component", "subgraph_resource", "custom_node_graph"}:
            normalized["source_graph_document_id"] = item.get("source_graph_document_id")
            normalized["source_graph_document_save_revision"] = item.get(
                "source_graph_document_save_revision"
            )
            source_graph_document = item.get("source_graph_document")
            if isinstance(source_graph_document, dict):
                normalized["source_graph_document"] = source_graph_document
            input_schema = item.get("input_schema")
            if isinstance(input_schema, dict):
                normalized["input_schema"] = self._extract_graph_resource_schema(
                    {"input_schema": input_schema},
                    schema_key="input_schema",
                )
            output_schema = item.get("output_schema")
            if isinstance(output_schema, dict):
                normalized["output_schema"] = self._extract_graph_resource_schema(
                    {"output_schema": output_schema},
                    schema_key="output_schema",
                )
        normalized["tags"] = self._build_resource_tags(normalized=normalized, raw_item=item)
        normalized["search_tokens"] = self._build_resource_search_tokens(
            normalized=normalized,
            raw_item=item,
        )
        return normalized

    def _normalize_i18n_field(self, raw_value: object) -> dict[str, str]:
        if not isinstance(raw_value, dict):
            return {}
        normalized: dict[str, str] = {}
        for locale, text in raw_value.items():
            if not isinstance(locale, str) or not locale.strip():
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            normalized[locale.strip()] = text.strip()
        return normalized

    def _extract_graph_resource_schema(self, root_metadata: object, *, schema_key: str) -> dict:
        if not isinstance(root_metadata, dict):
            return {}
        raw_schema = root_metadata.get(schema_key)
        if not isinstance(raw_schema, dict):
            return {}
        normalized_schema: dict[str, dict] = {}
        for field_name, field_meta in raw_schema.items():
            if not isinstance(field_name, str) or not field_name.strip():
                continue
            if not isinstance(field_meta, dict):
                continue
            normalized_schema[field_name.strip()] = dict(field_meta)
        return normalized_schema

    def _extract_custom_node_graph_boundary_schemas(
        self,
        graph_document: object,
    ) -> tuple[bool, dict, dict]:
        if not isinstance(graph_document, dict):
            return False, {}, {}
        raw_nodes = graph_document.get("nodes")
        if not isinstance(raw_nodes, list):
            return False, {}, {}
        input_schema: dict[str, dict] = {}
        output_schema: dict[str, dict] = {}
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue
            node_kind = raw_node.get("node_kind")
            if node_kind not in {"component.input", "component.output"}:
                continue
            node_config = raw_node.get("node_config")
            field_name, field_meta = self._extract_boundary_schema_field(node_config)
            if field_name is None or field_meta is None:
                continue
            if node_kind == "component.input":
                input_schema[field_name] = field_meta
            else:
                output_schema[field_name] = field_meta
        has_boundary_nodes = bool(input_schema or output_schema)
        return has_boundary_nodes, input_schema, output_schema

    def _extract_boundary_schema_field(self, node_config: object) -> tuple[str | None, dict | None]:
        if not isinstance(node_config, dict):
            return None, None
        raw_name = node_config.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return None, None
        field_name = raw_name.strip()
        raw_value_type = node_config.get("value_type")
        field_meta: dict[str, object] = {}
        if isinstance(raw_value_type, str) and raw_value_type.strip():
            field_meta["type"] = raw_value_type.strip()
        if "required" in node_config:
            field_meta["required"] = bool(node_config.get("required"))
        if "default_value" in node_config:
            field_meta["default_value"] = deepcopy(node_config.get("default_value"))
        raw_description = node_config.get("description")
        if isinstance(raw_description, str):
            field_meta["description"] = raw_description
        return field_name, field_meta

    def _schema_value_matches_type(self, value: object, schema_type: object) -> bool:
        if not isinstance(schema_type, str) or not schema_type.strip():
            return True
        normalized_type = schema_type.strip()
        if normalized_type == "string":
            return isinstance(value, str)
        if normalized_type == "number":
            return (
                (isinstance(value, int) and not isinstance(value, bool))
                or isinstance(value, float)
            )
        if normalized_type == "boolean":
            return isinstance(value, bool)
        if normalized_type == "array":
            return isinstance(value, list)
        if normalized_type == "object":
            return isinstance(value, dict)
        return True

    def _infer_resource_visibility_metadata(self, normalized: dict, raw_item: dict) -> dict:
        resource_type = normalized["resource_type"]
        resource_key = normalized["resource_key"]
        if resource_type in {"user_component", "subgraph_resource", "custom_node_graph"}:
            return {
                "node_taxonomy": "user_component",
                "component_library_visible": True,
                "resource_manager_visible": True,
                "user_creatable": True,
                "compatibility_only": False,
                "graph_semantic_kind": "component_instance",
            }

        explicit_taxonomy = raw_item.get("node_taxonomy")
        node_taxonomy = explicit_taxonomy if explicit_taxonomy in NODE_TAXONOMIES else None
        if node_taxonomy is None:
            node_taxonomy = self._infer_builtin_node_taxonomy(resource_key)

        compatibility_only = node_taxonomy in {"graph_edge_semantics", "compat_action"}
        component_library_visible = node_taxonomy in {
            "builtin_component",
            "control_structure",
            "logic_expression",
            "user_component",
        }
        resource_manager_visible = node_taxonomy in {"builtin_component", "user_component"}
        user_creatable = component_library_visible and not compatibility_only

        return {
            "node_taxonomy": node_taxonomy,
            "component_library_visible": bool(
                raw_item.get("component_library_visible", component_library_visible)
            ),
            "resource_manager_visible": bool(
                raw_item.get("resource_manager_visible", resource_manager_visible)
            ),
            "user_creatable": bool(raw_item.get("user_creatable", user_creatable)),
            "compatibility_only": bool(raw_item.get("compatibility_only", compatibility_only)),
            "graph_semantic_kind": raw_item.get(
                "graph_semantic_kind",
                self._infer_graph_semantic_kind(node_taxonomy=node_taxonomy, resource_key=resource_key),
            ),
        }

    def _infer_builtin_node_taxonomy(self, resource_key: str) -> str:
        if resource_key in {
            "control.foreach",
            "control.if",
            "control.switch",
            "control.parallel_fork",
            "control.join",
            "control.while",
            "control.retry",
            "control.failover",
        }:
            return "control_structure"
        if resource_key in {
            "control.jump_to_step",
            "control.end_foreach",
            "control.foreach_continue",
            "control.foreach_break",
        }:
            return "graph_edge_semantics"
        if resource_key in {"call_blueprint", "graph.call_subgraph"}:
            return "compat_action"
        if resource_key.startswith("data."):
            return "logic_expression"
        return "builtin_component"

    def _infer_graph_semantic_kind(self, *, node_taxonomy: str, resource_key: str) -> str:
        if node_taxonomy == "control_structure":
            return resource_key.removeprefix("control.")
        if node_taxonomy == "graph_edge_semantics":
            return resource_key.removeprefix("control.")
        if node_taxonomy == "logic_expression":
            return resource_key.removeprefix("data.")
        if node_taxonomy == "compat_action":
            return resource_key
        return "action"

    def _resolve_export_path(self, target_path: str | Path) -> Path:
        if isinstance(target_path, Path):
            candidate = target_path
        elif isinstance(target_path, str) and target_path.strip():
            candidate = Path(target_path.strip())
        else:
            raise ValueError("path must be a non-empty path")
        return candidate.resolve()

    def _require_resource(self, resource_id: str) -> dict:
        for item in self._get_resource_registry():
            if item["resource_id"] == resource_id:
                return dict(item)
        raise ValueError(f"resource not found: {resource_id}")

    def _get_editor_history(self) -> dict:
        return self._extract_editor_history(self._state)

    def _get_execution_history(self) -> dict:
        return self._extract_execution_history(self._state)

    def _extract_editor_history(self, state: dict | None) -> dict:
        raw_history = state.get("editor_history") if isinstance(state, dict) else None
        if not isinstance(raw_history, dict):
            raw_history = {}
        return {
            "undo_stack": self._normalize_editor_history_stack(raw_history.get("undo_stack")),
            "redo_stack": self._normalize_editor_history_stack(raw_history.get("redo_stack")),
        }

    def _extract_execution_history(self, state: dict | None) -> dict:
        raw_history = state.get("execution_history") if isinstance(state, dict) else None
        if not isinstance(raw_history, dict):
            raw_history = {}
        runtime_runs = raw_history.get("runtime_runs")
        debug_sessions = raw_history.get("debug_sessions")
        if not isinstance(runtime_runs, list):
            runtime_runs = []
        if not isinstance(debug_sessions, list):
            debug_sessions = []
        normalized_runtime_runs = [
            item
            for item in runtime_runs
            if isinstance(item, dict)
            and isinstance(item.get("session_id"), str)
            and isinstance(item.get("status"), str)
        ]
        normalized_debug_sessions = [
            item
            for item in debug_sessions
            if isinstance(item, dict)
            and isinstance(item.get("session_id"), str)
            and isinstance(item.get("status"), str)
        ]
        return {
            "runtime_runs": normalized_runtime_runs[:MAX_RUNTIME_SESSION_HISTORY],
            "debug_sessions": normalized_debug_sessions[:MAX_DEBUG_SESSION_HISTORY],
        }

    def _normalize_editor_history_stack(self, raw_stack) -> list[dict]:
        if not isinstance(raw_stack, list):
            return []
        normalized_stack: list[dict] = []
        for item in raw_stack:
            if not isinstance(item, dict):
                continue
            operation_id = item.get("operation_id")
            operation_kind = item.get("operation_kind")
            label = item.get("label")
            recorded_at = item.get("recorded_at")
            payload = item.get("payload")
            if not isinstance(operation_id, str) or not operation_id.strip():
                continue
            if not isinstance(operation_kind, str) or not operation_kind.strip():
                continue
            if not isinstance(label, str) or not label.strip():
                continue
            if not isinstance(recorded_at, str) or not recorded_at.strip():
                continue
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                continue
            normalized_stack.append(
                {
                    "operation_id": operation_id.strip(),
                    "operation_kind": operation_kind.strip(),
                    "label": label.strip(),
                    "recorded_at": recorded_at,
                    "payload": payload,
                }
            )
        return normalized_stack[:MAX_EDITOR_HISTORY_DEPTH]

    def _infer_resource_category(self, resource: dict) -> str:
        if resource["resource_type"] == "builtin_component":
            return "builtin"
        return "user"

    def _build_resource_facets(self, resources: list[dict]) -> dict:
        category_paths = sorted(
            {
                tuple(path)
                for item in resources
                for path in [item.get("category_path")]
                if isinstance(path, list) and path and all(isinstance(part, str) and part for part in path)
            }
        )
        category_groups = sorted(
            {
                tuple(path)
                for item in resources
                for path in [item.get("category_group_path")]
                if isinstance(path, list) and path and all(isinstance(part, str) and part for part in path)
            }
        )
        user_tags = sorted(
            {
                tag
                for item in resources
                for tag in item.get("tags", [])
                if isinstance(tag, str)
                and tag
                and not (
                    tag.startswith("type:")
                    or tag.startswith("origin:")
                    or tag.startswith("status:")
                    or tag.startswith("taxonomy:")
                    or tag.startswith("semantic:")
                    or tag.startswith("domain:")
                )
            }
        )
        return {
            "category_paths": [
                {
                    "path": list(path),
                    "label": " / ".join(path),
                }
                for path in category_paths
            ],
            "category_groups": [
                {
                    "path": list(path),
                    "label": self._format_category_group_label(list(path)),
                }
                for path in category_groups
            ],
            "user_tags": user_tags,
        }

    def _build_resource_category_group_path(self, *, normalized: dict) -> list[str]:
        category_path = normalized.get("category_path")
        if not isinstance(category_path, list):
            return []
        normalized_segments = [
            segment.strip()
            for segment in category_path
            if isinstance(segment, str) and segment.strip()
        ]
        if not normalized_segments:
            return []
        if len(normalized_segments) >= 2:
            return normalized_segments[:2]
        return normalized_segments[:1]

    def _build_resource_category_group_label(self, *, normalized: dict) -> str:
        return self._format_category_group_label(
            self._build_resource_category_group_path(normalized=normalized)
        )

    def _format_category_group_label(self, path: list[str]) -> str:
        if path == ["builtin", "browser"]:
            return "浏览器"
        if path == ["builtin", "excel"]:
            return "Excel"
        if path == ["builtin", "file"]:
            return "文件"
        if path == ["builtin", "http"]:
            return "HTTP"
        if path == ["builtin", "control_structure"]:
            return "流程控制"
        if path == ["builtin", "logic_expression"]:
            return "数据逻辑"
        if path == ["project", "custom_node_graph"]:
            return "用户组件"
        if path == ["project", "user_component"]:
            return "用户组件"
        if path == ["project", "subgraph_resource"]:
            return "用户组件"
        return " / ".join(path)

    def _filter_resources(
        self,
        resources: list[dict],
        *,
        query: str | None = None,
        tags: list[str] | None = None,
        enabled: bool | None = None,
        origin: str | None = None,
        resource_type: str | None = None,
    ) -> list[dict]:
        normalized_query = query.strip().lower() if isinstance(query, str) and query.strip() else None
        normalized_tags = [
            item.strip()
            for item in (tags or [])
            if isinstance(item, str) and item.strip()
        ]
        normalized_origin = origin.strip() if isinstance(origin, str) and origin.strip() else None
        normalized_resource_type = (
            resource_type.strip()
            if isinstance(resource_type, str) and resource_type.strip()
            else None
        )

        filtered: list[dict] = []
        for item in resources:
            if enabled is not None and item.get("enabled") is not enabled:
                continue
            if normalized_origin is not None and item.get("origin") != normalized_origin:
                continue
            if (
                normalized_resource_type is not None
                and item.get("resource_type") != normalized_resource_type
            ):
                continue
            if normalized_tags and not all(tag in item.get("tags", []) for tag in normalized_tags):
                continue
            if normalized_query is not None and not self._resource_matches_query(
                resource=item,
                query=normalized_query,
            ):
                continue
            filtered.append(item)
        return filtered

    def _resource_matches_query(self, *, resource: dict, query: str) -> bool:
        search_fields: list[str] = []
        for key in ("display_name", "resource_key", "description", "capability_domain"):
            value = resource.get(key)
            if isinstance(value, str) and value.strip():
                search_fields.append(value.strip().lower())
        category_path = resource.get("category_path")
        if isinstance(category_path, list):
            for segment in category_path:
                if isinstance(segment, str) and segment.strip():
                    search_fields.append(segment.strip().lower())
        for token in resource.get("search_tokens", []):
            if isinstance(token, str) and token.strip():
                search_fields.append(token.strip().lower())
        for alias in resource.get("compatibility_aliases", []):
            if isinstance(alias, str) and alias.strip():
                search_fields.append(alias.strip().lower())
        for tag in resource.get("tags", []):
            if isinstance(tag, str) and tag.strip():
                search_fields.append(tag.strip().lower())
        return any(query in field for field in search_fields)

    def _normalize_user_tags(self, raw_tags: object) -> list[str]:
        if not isinstance(raw_tags, list):
            return []
        return sorted(
            {
                item.strip()
                for item in raw_tags
                if isinstance(item, str) and item.strip()
            }
        )

    def _build_resource_category_path(self, *, normalized: dict, raw_item: dict) -> list[str]:
        resource_type = normalized["resource_type"]
        if resource_type == "builtin_component":
            node_taxonomy = normalized.get("node_taxonomy")
            capability_domain = normalized.get("capability_domain")
            semantic_kind = normalized.get("graph_semantic_kind")
            second_segment = (
                capability_domain
                if isinstance(capability_domain, str)
                and capability_domain.strip()
                and node_taxonomy not in {"control_structure", "logic_expression"}
                else node_taxonomy
            )
            if not isinstance(second_segment, str) or not second_segment.strip():
                second_segment = "builtin_component"
            third_segment = (
                semantic_kind
                if isinstance(semantic_kind, str) and semantic_kind.strip()
                else "action"
            )
            return ["builtin", second_segment.strip(), third_segment.strip()]

        folder_name = self._extract_resource_folder_name(raw_item)
        return [
            "project",
            resource_type,
            folder_name or "general",
        ]

    def _extract_resource_folder_name(self, raw_item: dict) -> str | None:
        for tag in self._normalize_user_tags(raw_item.get("tags")):
            if tag.startswith("folder:") and len(tag) > len("folder:"):
                return tag.removeprefix("folder:").strip().lower() or None
        source_graph_document = raw_item.get("source_graph_document")
        root_metadata = (
            source_graph_document.get("root_metadata")
            if isinstance(source_graph_document, dict)
            else None
        )
        resource_tags = root_metadata.get("resource_tags") if isinstance(root_metadata, dict) else None
        for tag in self._normalize_user_tags(resource_tags):
            if tag.startswith("folder:") and len(tag) > len("folder:"):
                return tag.removeprefix("folder:").strip().lower() or None
        return None

    def _build_resource_search_tokens(self, *, normalized: dict, raw_item: dict) -> list[str]:
        tokens: set[str] = set()
        display_name = normalized.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            tokens.add(f"display:{display_name.strip().lower()}")
        category_path = normalized.get("category_path")
        if isinstance(category_path, list):
            for segment in category_path:
                if isinstance(segment, str) and segment.strip():
                    tokens.add(f"path:{segment.strip().lower()}")
        for tag in self._build_resource_tags(normalized=normalized, raw_item=raw_item):
            if isinstance(tag, str) and tag.strip():
                tokens.add(f"tag:{tag.strip().lower()}")
        return sorted(tokens)

    def _build_resource_tags(self, *, normalized: dict, raw_item: dict) -> list[str]:
        tags = {
            f"type:{normalized['resource_type']}",
            f"origin:{normalized['origin']}",
            "status:enabled" if normalized.get("enabled") is True else "status:disabled",
            f"taxonomy:{normalized['node_taxonomy']}",
            f"semantic:{normalized['graph_semantic_kind']}",
        }
        capability_domain = normalized.get("capability_domain")
        if isinstance(capability_domain, str) and capability_domain.strip():
            tags.add(f"domain:{capability_domain.strip()}")
        tags.update(self._normalize_user_tags(raw_item.get("tags")))
        source_graph_document = raw_item.get("source_graph_document")
        root_metadata = (
            source_graph_document.get("root_metadata")
            if isinstance(source_graph_document, dict)
            else None
        )
        if isinstance(root_metadata, dict):
            tags.update(self._normalize_user_tags(root_metadata.get("resource_tags")))
        return sorted(tags)

    def _remember_runtime_session(self, session_document: dict) -> None:
        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            sessions = self._extract_runtime_sessions(current_state)
            sessions.insert(0, session_document)
            current_state["runtime_sessions"] = sessions[:MAX_RUNTIME_SESSION_HISTORY]
            return current_state

        self._state = self._state_store.mutate(mutation)

    def _remember_debug_session(self, session_document: dict) -> None:
        def mutation(state: dict | None) -> dict:
            current_state, _ = self._normalize_workspace_state(state)
            sessions = self._extract_debug_sessions(current_state)
            sessions.insert(0, session_document)
            current_state["debug_sessions"] = sessions[:MAX_DEBUG_SESSION_HISTORY]
            execution_history = self._extract_execution_history(current_state)
            execution_history["debug_sessions"].insert(
                0,
                {
                    "session_id": session_document["debug_session"]["session_id"],
                    "status": session_document["debug_session"]["status"],
                    "graph_model_id": session_document["object_index"]["graph_model_id"],
                    "started_at": session_document["debug_session"]["started_at"],
                    "prepared_at": session_document["debug_session"].get("prepared_at"),
                },
            )
            execution_history["debug_sessions"] = execution_history["debug_sessions"][
                :MAX_DEBUG_SESSION_HISTORY
            ]
            current_state["execution_history"] = execution_history
            return current_state

        self._state = self._state_store.mutate(mutation)

    def _get_runtime_sessions(self) -> list[dict]:
        return self._extract_runtime_sessions(self._state)

    def _find_runtime_session(self, session_id: str) -> dict:
        for item in self._get_runtime_sessions():
            if item["runtime_session"]["session_id"] == session_id:
                return item
        raise ValueError(f"runtime session not found: {session_id}")

    def get_runtime_stream_snapshot(self, *, session_id: str) -> dict:
        session_document = self.get_runtime_session(session_id=session_id)
        return self._build_runtime_stream_terminal_payload(
            session_id=session_id,
            session_document=session_document,
        )

    def iter_runtime_stream_events(self, *, session_id: str):
        subscriber_id, queue = self._runtime_stream_broker.subscribe(session_id)
        try:
            yield from self._runtime_stream_broker.iter_events(queue)
        finally:
            self._runtime_stream_broker.unsubscribe(session_id, subscriber_id)

    def _get_debug_sessions(self) -> list[dict]:
        return self._extract_debug_sessions(self._state)

    def _find_debug_session(self, session_id: str) -> dict:
        for item in self._get_debug_sessions():
            if item["debug_session"]["session_id"] == session_id:
                return item
        raise ValueError(f"debug session not found: {session_id}")

    def _extract_runtime_sessions(self, state: dict | None) -> list[dict]:
        raw_sessions = state.get("runtime_sessions") if isinstance(state, dict) else None
        if not isinstance(raw_sessions, list):
            return []
        normalized_sessions: list[dict] = []
        for item in raw_sessions:
            if not isinstance(item, dict):
                continue
            runtime_session = item.get("runtime_session")
            runtime_plan = item.get("runtime_plan")
            request = item.get("request")
            node_states = item.get("node_states")
            event_log = item.get("event_log")
            if not isinstance(runtime_session, dict):
                continue
            if not isinstance(runtime_plan, dict):
                continue
            if not isinstance(request, dict):
                continue
            if not isinstance(node_states, list):
                continue
            if not isinstance(event_log, list):
                continue
            session_id = runtime_session.get("session_id")
            status = runtime_session.get("status")
            started_at = runtime_session.get("started_at")
            if not isinstance(session_id, str) or not session_id.strip():
                continue
            if not isinstance(status, str) or not status.strip():
                continue
            if not isinstance(started_at, str) or not started_at.strip():
                continue
            normalized_sessions.append(item)
        return normalized_sessions[:MAX_RUNTIME_SESSION_HISTORY]

    def _extract_debug_sessions(self, state: dict | None) -> list[dict]:
        raw_sessions = state.get("debug_sessions") if isinstance(state, dict) else None
        if not isinstance(raw_sessions, list):
            return []
        normalized_sessions: list[dict] = []
        for item in raw_sessions:
            if not isinstance(item, dict):
                continue
            debug_session = item.get("debug_session")
            request = item.get("request")
            stage_timeline = item.get("stage_timeline")
            object_index = item.get("object_index")
            diagnostic_links = item.get("diagnostic_links")
            if not isinstance(debug_session, dict):
                continue
            if not isinstance(request, dict):
                continue
            if not isinstance(stage_timeline, list):
                continue
            if not isinstance(object_index, dict):
                continue
            if not isinstance(diagnostic_links, list):
                continue
            session_id = debug_session.get("session_id")
            status = debug_session.get("status")
            started_at = debug_session.get("started_at")
            if not isinstance(session_id, str) or not session_id.strip():
                continue
            if not isinstance(status, str) or not status.strip():
                continue
            if not isinstance(started_at, str) or not started_at.strip():
                continue
            normalized_sessions.append(item)
        return normalized_sessions[:MAX_DEBUG_SESSION_HISTORY]

    def _normalize_compile_records_in_state(self, state: dict) -> bool:
        changed = False
        last_compile = state.get("last_compile")
        if isinstance(last_compile, dict) and "duration_ms" not in last_compile:
            last_compile["duration_ms"] = None
            changed = True
        compile_history = state.get("compile_history")
        if isinstance(compile_history, list):
            for item in compile_history:
                if isinstance(item, dict) and "duration_ms" not in item:
                    item["duration_ms"] = None
                    changed = True
        return changed

    def _resolve_graph_document_request(
        self,
        graph_document_payload: dict | None,
    ) -> tuple[GraphModel, dict]:
        self._refresh_state_from_store()
        if graph_document_payload is None:
            graph_model = self._get_graph_document_model()
            graph_document_meta = self._get_graph_document_meta()
            return graph_model, {
                "request_origin": "saved_graph_document",
                "requested_graph_model_id": graph_model.graph_model_id,
                "requested_graph_save_revision": graph_document_meta["save_revision"],
                "requested_graph_saved_at": graph_document_meta["saved_at"],
            }

        try:
            graph_model = GraphModel.model_validate(graph_document_payload)
        except ValidationError as exc:
            raise ValueError(f"graph document payload is invalid: {exc.errors()[0]['loc']}") from exc
        return graph_model, {
            "request_origin": "graph_document_payload",
            "requested_graph_model_id": graph_model.graph_model_id,
            "requested_graph_save_revision": None,
            "requested_graph_saved_at": None,
        }

    def _compile_graph_document_transient(
        self,
        graph_model: GraphModel,
        *,
        compilation_id_prefix: str,
    ) -> dict:
        started_at = perf_counter()
        diagnostics = self._collect_graph_validation_diagnostics(graph_model)
        compilation_id = f"{compilation_id_prefix}-{uuid.uuid4().hex[:12]}"

        blocking_diagnostics = [
            item
            for item in diagnostics
            if self._resolve_graph_validation_diagnostic_severity(item) in {"error", "fatal"}
        ]

        if blocking_diagnostics:
            return self._build_invalid_graph_compile_result(
                graph_model,
                blocking_diagnostics,
                compilation_id=compilation_id,
                duration_ms=self._resolve_duration_ms(started_at),
            )

        source_text = json.dumps(
            graph_model.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request = CompilationRequest(
            compilation_id=compilation_id,
            source=CompilationSource(
                kind="graph_workspace",
                entry_document=graph_model.graph_model_id,
                source_text=source_text,
            ),
        )
        try:
            outcome = self._compiler.compile(request)
            status = "succeeded"
        except CompilationAbortedError as exc:
            outcome = exc.outcome
            status = exc.status

        if diagnostics:
            outcome.diagnostic_catalog.entries.extend(
                self._materialize_graph_validation_diagnostic_entries(
                    graph_model,
                    diagnostics,
                    diagnostic_id_prefix=f"{compilation_id}:graph-validate",
                )
            )

        duration_ms = self._resolve_duration_ms(started_at)
        outcome.compilation_summary.duration_ms = duration_ms
        view = self._build_compile_view(
            status=status,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        return {
            "status": status,
            "request": request.model_dump(),
            "outcome": outcome,
            "view": view,
        }

    def _build_runtime_plan(self, graph_model: GraphModel) -> dict:
        resources = self._get_resource_registry()
        static_order_by_node_id = self._build_runtime_static_node_order(graph_model)
        node_by_id = {node.node_id: node for node in graph_model.nodes}
        outgoing_edge_ids: dict[str, list[str]] = {node.node_id: [] for node in graph_model.nodes}
        incoming_edge_ids: dict[str, list[str]] = {node.node_id: [] for node in graph_model.nodes}
        port_map_by_node_id = {
            node.node_id: {port.port_id: port for port in node.ports}
            for node in graph_model.nodes
        }
        relation_edges = []
        for edge in graph_model.edges:
            source_node = node_by_id.get(edge.from_node_id)
            source_port = (
                self._resolve_graph_port_by_reference(
                    node=source_node,
                    port_id=edge.from_port_id,
                    direction="output",
                )
                if isinstance(edge.from_port_id, str) and source_node is not None
                else None
            )
            target_node = node_by_id.get(edge.to_node_id)
            target_port = (
                self._resolve_graph_port_by_reference(
                    node=target_node,
                    port_id=edge.to_port_id,
                    direction="input",
                )
                if isinstance(edge.to_port_id, str) and target_node is not None
                else None
            )
            relation_edges.append(
                {
                    "edge_id": edge.edge_id,
                    "relation_layer": edge.relation_layer,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "from_port_id": edge.from_port_id,
                    "to_port_id": edge.to_port_id,
                    "from_port_semantic_slot": (
                        source_port.semantic_slot
                        if source_port is not None
                        else None
                    ),
                    "to_port_semantic_slot": (
                        target_port.semantic_slot
                        if target_port is not None
                        else None
                    ),
                    "edge_state": edge.edge_state,
                }
            )
            outgoing_edge_ids.setdefault(edge.from_node_id, []).append(edge.edge_id)
            incoming_edge_ids.setdefault(edge.to_node_id, []).append(edge.edge_id)

        executable_nodes = [
            {
                "node_id": node.node_id,
                "display_name": node.display_name,
                "node_kind": node.node_kind,
                "node_config": dict(node.node_config),
                "lowered_kind": node.lowered_kind,
                "source_anchor_ref": node.source_anchor_ref,
                "port_ids": [port.port_id for port in node.ports],
                "ports": [
                    {
                        "port_id": port.port_id,
                        "direction": port.direction,
                        "relation_layer": port.relation_layer,
                        "semantic_slot": port.semantic_slot,
                        "display_name": port.display_name,
                        "max_connections": port.max_connections,
                    }
                    for port in node.ports
                ],
                "incoming_edge_ids": incoming_edge_ids.get(node.node_id, []),
                "outgoing_edge_ids": outgoing_edge_ids.get(node.node_id, []),
                "plan_index": index,
                "static_order": static_order_by_node_id.get(node.node_id, index),
                **self._resolve_runtime_node_resource(node_kind=node.node_kind, resources=resources),
            }
            for index, node in enumerate(graph_model.nodes)
        ]

        entry_node_ids = [
            node.node_id
            for node in graph_model.nodes
            if node.node_kind == "flow.start"
        ]
        scheduler_mode = "flow_graph" if entry_node_ids else "legacy_sequence"
        scheduler_hints = self._build_runtime_scheduler_hints(graph_model)

        return {
            "graph_model_id": graph_model.graph_model_id,
            "compilation_id": graph_model.compilation_id,
            "root_metadata": deepcopy(graph_model.root_metadata),
            "node_count": len(graph_model.nodes),
            "edge_count": len(graph_model.edges),
            "scheduler_mode": scheduler_mode,
            "scheduler_hints": scheduler_hints,
            "entry_node_ids": entry_node_ids,
            "start_node_ids": [
                node.node_id
                for node in graph_model.nodes
                if not incoming_edge_ids.get(node.node_id)
            ],
            "terminal_node_ids": [
                node.node_id
                for node in graph_model.nodes
                if not outgoing_edge_ids.get(node.node_id)
            ],
            "executable_nodes": executable_nodes,
            "relation_edges": relation_edges,
            "viewport": graph_model.viewport.model_dump() if graph_model.viewport is not None else None,
        }

    def _resolve_runtime_node_resource(self, *, node_kind: str | None, resources: list[dict]) -> dict:
        if not isinstance(node_kind, str) or not node_kind.strip():
            return {
                "resolved_resource_id": None,
                "resource_key": None,
                "resource_status": "missing",
                "resource_type": None,
                "resource_origin": None,
                "component_source_graph_document_id": None,
                "component_source_graph_document": None,
            }
        for item in resources:
            if item.get("resource_key") == node_kind or item.get("resource_id") == node_kind:
                return {
                    "resolved_resource_id": item["resource_id"],
                    "resource_key": item["resource_key"],
                    "resource_status": "enabled" if item.get("enabled") is True else "disabled",
                    "resource_type": item.get("resource_type"),
                    "resource_origin": item.get("origin"),
                    "component_source_graph_document_id": item.get("source_graph_document_id"),
                    "component_source_graph_document": item.get("source_graph_document"),
                }
        return {
            "resolved_resource_id": None,
            "resource_key": node_kind,
            "resource_status": "missing",
            "resource_type": None,
            "resource_origin": None,
            "component_source_graph_document_id": None,
            "component_source_graph_document": None,
        }

    def _build_runtime_scheduler_hints(self, graph_model: GraphModel) -> dict:
        reachable_node_ids = self._collect_flow_graph_reachable_node_ids(graph_model)
        data_dependency_edges = [
            {
                "edge_id": edge.edge_id,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "from_port_id": edge.from_port_id,
                "to_port_id": edge.to_port_id,
            }
            for edge in graph_model.edges
            if edge.relation_layer == "data"
        ]

        writers_by_variable: dict[str, list[str]] = {}
        for node in graph_model.nodes:
            variable_name = self._extract_runtime_written_variable_name(node)
            if variable_name is None:
                continue
            writers_by_variable.setdefault(variable_name, []).append(node.node_id)

        potential_write_conflicts = []
        for variable_name, writer_node_ids in writers_by_variable.items():
            if len(writer_node_ids) < 2:
                continue
            reachable_writer_node_ids = [
                node_id for node_id in writer_node_ids if node_id in reachable_node_ids
            ]
            if len(reachable_writer_node_ids) < 2:
                continue
            potential_write_conflicts.append(
                {
                    "variable_name": variable_name,
                    "writer_node_ids": writer_node_ids,
                    "reachable_writer_node_ids": reachable_writer_node_ids,
                }
            )

        return {
            "data_dependency_edges": data_dependency_edges,
            "potential_write_conflicts": potential_write_conflicts,
        }

    def _extract_runtime_written_variable_name(self, node) -> str | None:
        node_kind = getattr(node, "node_kind", None)
        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            return None

        if node_kind in {
            "data.set_variable",
            "data.get_text",
            "data.get_attribute",
            "data.get_value",
            "data.get_element_count",
            "data.list_length",
            "data.list_index",
            "data.evaluate_expression",
            "data.increment_variable",
            "data.decrement_variable",
        }:
            for key in ("name", "variable_name"):
                value = node_config.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        if node_kind in {"data.create_list", "data.create_map"}:
            value = node_config.get("variable_name")
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        if node_kind == "data.set_variables_batch":
            updates = node_config.get("updates")
            if isinstance(updates, list) and len(updates) == 1 and isinstance(updates[0], dict):
                name = updates[0].get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            return None

        return None

    def _build_compilation_diagnostics_summary(self, compile_result: dict) -> dict:
        view = compile_result["view"]
        entries = [
            {
                "diagnostic_id": entry.diagnostic_id,
                "stage": entry.stage,
                "severity": entry.severity,
                "category": entry.category,
                "message": entry.message,
                "object_ref": entry.object_ref,
                "trace_ref": entry.trace_ref,
                "stage_extension": entry.stage_extension,
            }
            for entry in compile_result["outcome"].diagnostic_catalog.entries
        ]
        return {
            "total_count": view["diagnostic_summary"]["total_count"],
            "highest_severity": view["diagnostic_summary"]["highest_severity"],
            "entries": entries,
        }

    def _build_runtime_debug_snapshot(
        self,
        *,
        scheduler_mode: str | None,
        pending_node_entries: list[dict[str, object]],
        queued_node_ids: set[str],
        executed_node_ids_in_order: list[str],
        join_state_by_node_id: dict[str, dict[str, object]],
        retry_state_by_node_id: dict[str, dict[str, object]],
        executable_nodes: list[dict],
        current_program_counter: int | None,
        current_repeat_mode: bool,
    ) -> dict:
        token_queue: list[dict[str, object]] = []
        for entry in pending_node_entries:
            if not isinstance(entry, dict):
                continue
            node_index = entry.get("node_index")
            if not isinstance(node_index, int) or not (0 <= node_index < len(executable_nodes)):
                continue
            executable_node = executable_nodes[node_index]
            token_queue.append(
                {
                    "node_id": executable_node.get("node_id"),
                    "node_kind": executable_node.get("node_kind"),
                    "repeat_mode": bool(entry.get("repeat_mode")),
                }
            )

        join_buffers: dict[str, dict[str, object]] = {}
        for node_id, join_state in join_state_by_node_id.items():
            if not isinstance(node_id, str) or not isinstance(join_state, dict):
                continue
            arrived_ports = join_state.get("arrived_input_ports")
            join_buffers[node_id] = {
                "arrived_input_ports": (
                    sorted(arrived_ports)
                    if isinstance(arrived_ports, set)
                    else []
                )
            }

        retry_states: dict[str, dict[str, object]] = {}
        for node_id, retry_state in retry_state_by_node_id.items():
            if not isinstance(node_id, str) or not isinstance(retry_state, dict):
                continue
            retry_states[node_id] = {
                "attempts": int(retry_state.get("attempts", 0))
                if isinstance(retry_state.get("attempts"), int)
                else 0
            }

        current_node = None
        if isinstance(current_program_counter, int) and 0 <= current_program_counter < len(executable_nodes):
            executable_node = executable_nodes[current_program_counter]
            current_node = {
                "node_id": executable_node.get("node_id"),
                "node_kind": executable_node.get("node_kind"),
                "repeat_mode": current_repeat_mode,
            }

        return {
            "scheduler_mode": scheduler_mode,
            "token_queue": token_queue,
            "queued_node_ids": sorted(item for item in queued_node_ids if isinstance(item, str)),
            "executed_node_ids": [item for item in executed_node_ids_in_order if isinstance(item, str)],
            "join_buffers": join_buffers,
            "retry_states": retry_states,
            "current_node": current_node,
        }

    def _build_runtime_preview_summary(self, snapshot: dict | None) -> dict:
        if not isinstance(snapshot, dict):
            return {
                "scheduler_mode": None,
                "queued_node_count": 0,
                "executed_node_count": 0,
                "join_buffer_count": 0,
                "retry_state_count": 0,
                "current_node_id": None,
            }
        current_node = snapshot.get("current_node")
        queued_node_ids = snapshot.get("queued_node_ids")
        executed_node_ids = snapshot.get("executed_node_ids")
        join_buffers = snapshot.get("join_buffers")
        retry_states = snapshot.get("retry_states")
        return {
            "scheduler_mode": snapshot.get("scheduler_mode"),
            "queued_node_count": len(queued_node_ids) if isinstance(queued_node_ids, list) else 0,
            "executed_node_count": len(executed_node_ids) if isinstance(executed_node_ids, list) else 0,
            "join_buffer_count": len(join_buffers) if isinstance(join_buffers, dict) else 0,
            "retry_state_count": len(retry_states) if isinstance(retry_states, dict) else 0,
            "current_node_id": current_node.get("node_id") if isinstance(current_node, dict) else None,
        }

    def _build_runtime_execution_summary(
        self,
        *,
        runtime_session: dict,
        node_states: list[dict],
        event_log: list[dict],
        diagnostic_events: list[dict],
        result: dict | None,
    ) -> dict:
        node_status_counts: dict[str, int] = {}
        for item in node_states if isinstance(node_states, list) else []:
            if not isinstance(item, dict):
                continue
            node_status = item.get("node_status")
            if isinstance(node_status, str) and node_status.strip():
                node_status_counts[node_status.strip()] = node_status_counts.get(node_status.strip(), 0) + 1
        return {
            "status": result.get("status") if isinstance(result, dict) else runtime_session.get("status"),
            "completed_node_count": runtime_session.get("completed_node_count", 0),
            "failed_node_count": runtime_session.get("failed_node_count", 0),
            "event_count": len(event_log),
            "diagnostic_event_count": len(diagnostic_events),
            "node_status_counts": node_status_counts,
            "latest_event_kind": (
                event_log[-1].get("event_kind")
                if event_log and isinstance(event_log[-1], dict)
                else None
            ),
        }

    def _build_runtime_stream_snapshot_payload(
        self,
        *,
        session_id: str,
        session: dict,
        runtime_session: dict,
        node_states: list[dict],
        event_log: list[dict],
        result: dict | None,
    ) -> dict:
        payload = {
            "session_id": session_id,
            "status": runtime_session.get("status"),
            "runtime_session": dict(runtime_session),
            "runtime_plan": dict(session.get("runtime_plan", {})),
            "node_states": self._decorate_runtime_node_states_for_display(node_states),
            "event_log": [dict(item) for item in event_log],
            "execution_summary": self._build_runtime_execution_summary(
                runtime_session=runtime_session,
                node_states=node_states,
                event_log=event_log,
                diagnostic_events=[
                    item
                    for item in event_log
                    if item.get("event_kind") == "diagnostic.raised"
                ],
                result=result,
            ),
            "result": dict(result) if isinstance(result, dict) else result,
        }
        return payload

    def _build_runtime_stream_summary_payload(
        self,
        *,
        session_id: str,
        runtime_session: dict,
        node_states: list[dict],
        event_log: list[dict],
    ) -> dict:
        completed_count = sum(1 for item in node_states if item.get("node_status") == "completed")
        failed_count = sum(1 for item in node_states if item.get("node_status") == "failed")
        running_count = sum(1 for item in node_states if item.get("node_status") == "running")
        pending_count = sum(1 for item in node_states if item.get("node_status") == "pending")
        total_count = len(node_states)
        percent = ((completed_count + failed_count) / total_count * 100.0) if total_count > 0 else 0.0
        return {
            "session_id": session_id,
            "status": runtime_session.get("status"),
            "total_node_count": total_count,
            "completed_node_count": completed_count,
            "failed_node_count": failed_count,
            "running_node_count": running_count,
            "pending_node_count": pending_count,
            "percent": round(percent, 1),
            "event_count": len(event_log),
        }

    def _build_runtime_stream_terminal_payload(
        self,
        *,
        session_id: str,
        session_document: dict,
    ) -> dict:
        runtime_session = session_document.get("runtime_session", {})
        node_states = session_document.get("node_states", [])
        event_log = session_document.get("event_log", [])
        result = session_document.get("result")
        return self._build_runtime_stream_snapshot_payload(
            session_id=session_id,
            session=session_document,
            runtime_session=runtime_session if isinstance(runtime_session, dict) else {},
            node_states=node_states if isinstance(node_states, list) else [],
            event_log=event_log if isinstance(event_log, list) else [],
            result=result if isinstance(result, dict) else None,
        )

    def _build_execution_status_counts(self, entries: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            if not isinstance(status, str) or not status.strip():
                continue
            normalized_status = status.strip()
            counts[normalized_status] = counts.get(normalized_status, 0) + 1
        return counts

    def _filter_execution_history_entries(
        self,
        entries: list[dict],
        *,
        status: str | None,
    ) -> list[dict]:
        if not isinstance(status, str) or not status.strip():
            return list(entries)
        normalized_status = status.strip()
        return [
            item
            for item in entries
            if isinstance(item, dict) and item.get("status") == normalized_status
        ]

    def _build_debug_object_index(self, graph_model: GraphModel) -> dict:
        return {
            "graph_model_id": graph_model.graph_model_id,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "source_anchor_ref": node.source_anchor_ref,
                    "display_name": node.display_name,
                    "node_kind": node.node_kind,
                    "lowered_kind": node.lowered_kind,
                    "port_ids": [port.port_id for port in node.ports],
                }
                for node in graph_model.nodes
            ],
            "ports": [
                {
                    "node_id": node.node_id,
                    "port_id": port.port_id,
                    "direction": port.direction,
                    "relation_layer": port.relation_layer,
                    "semantic_slot": port.semantic_slot,
                }
                for node in graph_model.nodes
                for port in node.ports
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "relation_layer": edge.relation_layer,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "from_port_id": edge.from_port_id,
                    "to_port_id": edge.to_port_id,
                }
                for edge in graph_model.edges
            ],
        }

    def _build_debug_diagnostic_links(self, compile_result: dict) -> list[dict]:
        links = []
        for entry in compile_result["outcome"].diagnostic_catalog.entries:
            stage_extension = entry.stage_extension if isinstance(entry.stage_extension, dict) else {}
            links.append(
                {
                    "diagnostic_id": entry.diagnostic_id,
                    "stage": entry.stage,
                    "severity": entry.severity,
                    "category": entry.category,
                    "message": entry.message,
                    "object_ref": entry.object_ref,
                    "trace_ref": entry.trace_ref,
                    "subject_ref": stage_extension.get("subject_ref"),
                    "source_ref": stage_extension.get("source_ref"),
                    "graph_ref": stage_extension.get("graph_ref"),
                }
            )
        return links

    def _graph_model_to_native_flow_source_text(self, graph_model: GraphModel) -> str:
        source_nodes = []
        source_id_by_node_id: dict[str, str] = {}
        diagnostics: list[dict] = []

        for node in graph_model.nodes:
            try:
                projection = self._project_graph_node_to_native_flow(node)
            except GraphCompileMappingError as exc:
                diagnostics.extend(exc.diagnostics)
                continue
            source_node_id = node.source_anchor_ref or node.node_id
            source_id_by_node_id[node.node_id] = source_node_id
            source_nodes.append(
                {
                    "id": source_node_id,
                    "role": projection["role"],
                    "capability_domain": projection["capability_domain"],
                    "action_kind": projection["action_kind"],
                }
            )

        if diagnostics:
            raise GraphCompileMappingError(diagnostics)

        source_edges = [
            {
                "id": edge.edge_id,
                "from": source_id_by_node_id.get(edge.from_node_id, edge.from_node_id),
                "to": source_id_by_node_id.get(edge.to_node_id, edge.to_node_id),
                "relation_layer": edge.relation_layer,
            }
            for edge in graph_model.edges
        ]

        return json.dumps(
            {
                "nodes": source_nodes,
                "edges": source_edges,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _project_graph_node_to_native_flow(self, node) -> dict:
        bridge_meta = self._extract_bridge_native_flow_meta(node)
        if bridge_meta is not None:
            return bridge_meta

        node_kind = getattr(node, "node_kind", None)
        expansion_role = getattr(node, "expansion_role", "")
        if isinstance(node_kind, str) and "." in node_kind:
            capability_domain, action_kind = node_kind.split(".", 1)
            return self._build_native_flow_projection(
                node,
                role=self._resolve_native_flow_role(node),
                capability_domain=capability_domain,
                action_kind=action_kind,
                source="node_kind",
            )

        raise GraphCompileMappingError(
            [
                self._build_graph_compile_mapping_diagnostic(
                    node,
                    message=(
                        "graph node cannot be mapped to native_flow; "
                        "provide node_kind=<domain>.<action> or node_config.bridge_native_flow"
                    ),
                    detail={
                        "node_kind": node_kind,
                        "expansion_role": expansion_role,
                    },
                )
            ]
        )

    def _extract_bridge_native_flow_meta(self, node) -> dict | None:
        node_config = getattr(node, "node_config", {})
        if not isinstance(node_config, dict):
            return None
        bridge_meta = node_config.get("bridge_native_flow")
        if not isinstance(bridge_meta, dict):
            return None
        return self._build_native_flow_projection(
            node,
            role=bridge_meta.get("role"),
            capability_domain=bridge_meta.get("capability_domain"),
            action_kind=bridge_meta.get("action_kind"),
            source="node_config.bridge_native_flow",
        )

    def _build_native_flow_projection(
        self,
        node,
        *,
        role,
        capability_domain,
        action_kind,
        source: str,
    ) -> dict:
        if not isinstance(role, str) or role not in NATIVE_FLOW_ROLES:
            raise GraphCompileMappingError(
                [
                    self._build_graph_compile_mapping_diagnostic(
                        node,
                        message=f"invalid native_flow role from {source}: {role!r}",
                        detail={"source": source, "role": role},
                    )
                ]
            )
        if (
            not isinstance(capability_domain, str)
            or capability_domain not in NATIVE_FLOW_CAPABILITY_DOMAINS
        ):
            raise GraphCompileMappingError(
                [
                    self._build_graph_compile_mapping_diagnostic(
                        node,
                        message=(
                            f"invalid native_flow capability_domain from {source}: "
                            f"{capability_domain!r}"
                        ),
                        detail={"source": source, "capability_domain": capability_domain},
                    )
                ]
            )
        if not isinstance(action_kind, str) or not action_kind.strip():
            raise GraphCompileMappingError(
                [
                    self._build_graph_compile_mapping_diagnostic(
                        node,
                        message=f"invalid native_flow action_kind from {source}: {action_kind!r}",
                        detail={"source": source, "action_kind": action_kind},
                    )
                ]
            )
        return {
            "role": role,
            "capability_domain": capability_domain,
            "action_kind": action_kind.strip(),
        }

    def _resolve_native_flow_role(self, node) -> str:
        expansion_role = getattr(node, "expansion_role", "")
        if isinstance(expansion_role, str) and ":" in expansion_role:
            role = expansion_role.split(":", 1)[0]
            if role in NATIVE_FLOW_ROLES:
                return role
        lowered_kind = getattr(node, "lowered_kind", "execution")
        return {
            "execution": "action",
            "control": "condition",
            "observe": "transform",
            "bridge": "transform",
        }.get(lowered_kind, "action")

    def _build_graph_compile_mapping_diagnostic(self, node, *, message: str, detail: dict) -> dict:
        return {
            "category": "graph.compile.mapping_error",
            "message": message,
            "object_ref": getattr(node, "node_id", None),
            "stage_extension": {
                "subject_ref": getattr(node, "node_id", None),
                "action": "mapped graph document to native_flow",
                "rule": "graph.compile.bridge_native_flow",
                "result": "failed",
                "detail": detail,
            },
        }
