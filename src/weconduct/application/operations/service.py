from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Mapping

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload

from .models import OperationRegistryError
from .registry import OperationRegistry


class HostOperationService:
    """在契约校验、敏感遮罩后，将稳定 operation_id 委托给宿主服务。"""

    def __init__(
        self,
        *,
        service: object,
        registry: OperationRegistry | None = None,
        host_metadata: Mapping[str, object] | None = None,
        project_path_allowed_roots: tuple[str | Path, ...] | None = None,
    ) -> None:
        self._service = service
        self._registry = registry or OperationRegistry.build_stable_public()
        self._host_metadata = dict(host_metadata or {})
        self._project_path_allowed_roots = (
            None
            if project_path_allowed_roots is None
            else tuple(Path(root).expanduser().resolve() for root in project_path_allowed_roots)
        )

    def list_descriptors(self, *, exposure: str | None = None):
        return self._registry.list_descriptors(exposure=exposure)

    def describe(self, operation_id: str):
        return self._registry.describe(operation_id)

    def execute(self, operation_id: str, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        descriptor = self._registry.describe(operation_id)
        request = dict(payload or {})
        self._registry.validate_input(descriptor, request)
        try:
            result = self._dispatch(operation_id, request)
        except OperationRegistryError:
            raise
        except ValueError as exc:
            raise _normalize_dispatch_value_error(exc, operation_id=operation_id) from exc
        except Exception as exc:
            raise OperationRegistryError("operation.execution_failed", str(exc), operation_id=operation_id) from exc
        normalized = _normalize_value(result)
        if not isinstance(normalized, dict):
            normalized = {"result": normalized}
        return redact_sensitive_payload(self._filter_output(operation_id, normalized))

    def _dispatch(self, operation_id: str, payload: dict[str, object]) -> object:
        service = self._service
        if operation_id == "host.describe":
            health = service.get_runtime_health()
            return {"service": "weconduct", "api_version": health.get("api_version"), "host_mode": health.get("host_mode"), **self._host_metadata}
        if operation_id == "host.capabilities":
            return {"capabilities": service.get_runtime_health().get("capabilities", {})}
        if operation_id == "project.current.get":
            return _public_project_document(service.get_project_document())
        if operation_id == "project.create":
            project_directory = payload.get("project_directory")
            if project_directory is not None:
                self._assert_project_path_allowed(
                    project_directory,
                    operation_id=operation_id,
                )
            return service.create_project(
                project_name=payload["project_name"],
                project_directory=project_directory,
            )
        if operation_id == "project.open":
            self._assert_project_path_allowed(payload["project_path"], operation_id=operation_id)
            return service.open_project(project_path=payload["project_path"])
        if operation_id == "project.save":
            return service.save_project(graph_document_payload=payload.get("graph_document"))
        if operation_id == "project.close":
            close_method = getattr(service, "close_project", None)
            if not callable(close_method):
                raise OperationRegistryError("operation.not_available", "project.close is not available")
            return close_method()
        if operation_id == "graph.get":
            return service.get_graph_document(document_id=payload.get("document_id"))
        if operation_id == "graph.replace":
            return service.save_graph_document(payload["graph_document"], expected_graph_document_save_revision=payload.get("expected_revision"))
        if operation_id == "graph.validate":
            return service.validate_graph_document(payload["graph_document"])
        if operation_id == "graph.compile":
            return service.compile_graph_document(payload.get("graph_document"))
        if operation_id == "graph.node_draft.build":
            return service.build_graph_node_draft(resource_key=payload["resource_key"], node_id=payload.get("node_id"), position=payload.get("position"))
        if operation_id == "execution.start":
            started = service.start_runtime_session(payload.get("graph_document"))
            if started.get("status") == "started":
                session_id = started.get("runtime_session", {}).get("session_id")
                if isinstance(session_id, str) and hasattr(service, "start_runtime_session_execution"):
                    return service.start_runtime_session_execution(session_id=session_id)
            return started
        if operation_id == "execution.get":
            return service.get_runtime_session(session_id=payload["execution_id"])
        if operation_id == "execution.cancel":
            return service.abort_runtime_session(session_id=payload["execution_id"], reason=payload.get("reason", "external api cancellation"))
        if operation_id == "execution.events.subscribe":
            return {"execution_id": payload["execution_id"], "stream": "sse"}
        if operation_id == "pending_input.get":
            return _public_pending_input_snapshot(service.get_pending_input_snapshot(execution_id=payload["execution_id"]))
        if operation_id == "pending_input.submit":
            return _public_pending_input_snapshot(service.submit_pending_input(execution_id=payload["execution_id"], request_id=payload["request_id"], values=payload["values"]))
        raise OperationRegistryError("operation.not_found", f"operation not found: {operation_id}")

    def _assert_project_path_allowed(self, raw_path: object, *, operation_id: str) -> None:
        allowed_roots = self._project_path_allowed_roots
        if allowed_roots is None:
            return
        if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
            raise OperationRegistryError(
                "operation.input_invalid",
                "project path must be a non-empty path",
                operation_id=operation_id,
            )
        candidate = Path(raw_path).expanduser().resolve()
        for root in allowed_roots:
            try:
                candidate.relative_to(root)
                return
            except ValueError:
                continue
        raise OperationRegistryError(
            "operation.path_denied",
            "project path is outside the configured external API allowed roots",
            operation_id=operation_id,
        )

    @staticmethod
    def _filter_output(operation_id: str, result: dict[str, object]) -> dict[str, object]:
        if operation_id == "host.capabilities":
            return {"capabilities": result.get("capabilities", {})}
        if operation_id == "host.describe":
            return {key: result.get(key) for key in ("service", "api_version", "host_mode", "instance_id") if result.get(key) is not None}
        return result


def _normalize_value(value: object) -> object:
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _normalize_value(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_dispatch_value_error(error: ValueError, *, operation_id: str) -> OperationRegistryError:
    explicit_code = getattr(error, "error_code", None)
    if isinstance(explicit_code, str) and explicit_code.strip():
        error_code = explicit_code.strip()
    elif str(error) == "pending input request was not found":
        error_code = "operation.not_found"
    elif str(error) == "pending input request is not waiting":
        error_code = "operation.state_conflict"
    elif str(error).startswith("pending input"):
        error_code = "operation.input_invalid"
    else:
        error_code = "operation.execution_failed"
    details = {name: value for name in ("expected_revision", "current_revision", "recovery_action", "state") if (value := getattr(error, name, None)) is not None}
    return OperationRegistryError(error_code, str(error), operation_id=operation_id, details=details)


def _public_project_document(document: object) -> dict[str, object]:
    if not isinstance(document, Mapping):
        return {}
    project = document.get("project")
    if not isinstance(project, Mapping):
        return {"project": {}}
    allowed = {key: project.get(key) for key in ("project_id", "project_name", "project_schema_version", "project_status", "main_graph_document_id", "resource_registry_revision", "is_dirty", "last_compile_status", "last_runtime_status", "last_runtime_session_id") if key in project}
    return {"project": allowed}


def _public_pending_input_snapshot(snapshot: object) -> dict[str, object]:
    if snapshot is None:
        return {"status": "none"}
    normalized = _normalize_value(snapshot)
    if not isinstance(normalized, dict):
        return {"status": "unknown"}
    fields = normalized.get("fields")
    if isinstance(fields, list):
        safe_fields: list[dict[str, object]] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            field_type = field.get("type", field.get("value_type"))
            safe_field = {key: field.get(key) for key in ("field_id", "label", "type", "required", "sensitive") if key in field}
            if field_type is not None:
                safe_field["type"] = field_type
            safe_fields.append(safe_field)
        normalized["fields"] = safe_fields
    normalized.pop("values", None)
    return normalized
