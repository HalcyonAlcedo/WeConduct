from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Mapping

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload


class OperationRegistryError(ValueError):
    """Stable error raised before or during an operation adapter dispatch."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        operation_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.operation_id = operation_id
        self.details = dict(details or {})


@dataclass(frozen=True)
class OperationDescriptor:
    operation_id: str
    contract_version: str = "1"
    input_schema: Mapping[str, object] = field(default_factory=dict)
    output_schema: Mapping[str, object] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    side_effect_level: str = "read"
    audit_policy: str = "default"
    execution_mode: str = "sync"
    idempotency_capability: bool = False
    exposure: str = "stable_public"

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "contract_version": self.contract_version,
            "input_schema": deepcopy(dict(self.input_schema)),
            "output_schema": deepcopy(dict(self.output_schema)),
            "required_permissions": list(self.required_permissions),
            "side_effect_level": self.side_effect_level,
            "audit_policy": self.audit_policy,
            "execution_mode": self.execution_mode,
            "idempotency_capability": self.idempotency_capability,
            "exposure": self.exposure,
        }


class OperationRegistry:
    """Shared operation contract for CLI, external API and future plugins."""

    def __init__(self, *, service: object, host_metadata: Mapping[str, object] | None = None) -> None:
        self._service = service
        self._host_metadata = dict(host_metadata or {})
        self._descriptors = self._build_descriptors()

    def list_descriptors(self, *, exposure: str | None = None) -> list[OperationDescriptor]:
        descriptors = list(self._descriptors.values())
        if exposure is not None:
            descriptors = [item for item in descriptors if item.exposure == exposure]
        return descriptors

    def describe(self, operation_id: str) -> OperationDescriptor:
        descriptor = self._descriptors.get(operation_id)
        if descriptor is None:
            raise OperationRegistryError("operation.not_found", f"operation not found: {operation_id}")
        return descriptor

    def execute(self, operation_id: str, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        descriptor = self.describe(operation_id)
        request = dict(payload or {})
        self._validate_input(descriptor, request)
        try:
            result = self._dispatch(operation_id, request)
        except OperationRegistryError:
            raise
        except ValueError as exc:
            raise _normalize_dispatch_value_error(exc, operation_id=operation_id) from exc
        except Exception as exc:
            raise OperationRegistryError(
                "operation.execution_failed",
                str(exc),
                operation_id=operation_id,
            ) from exc
        normalized = _normalize_value(result)
        if not isinstance(normalized, dict):
            normalized = {"result": normalized}
        return redact_sensitive_payload(self._filter_output(operation_id, normalized))

    def _build_descriptors(self) -> dict[str, OperationDescriptor]:
        object_schema = {"type": "object"}
        return {
            "host.describe": OperationDescriptor(
                "host.describe",
                output_schema={"type": "object", "properties": {"api_version": {"type": "string"}}},
            ),
            "host.capabilities": OperationDescriptor(
                "host.capabilities",
                output_schema={"type": "object", "properties": {"capabilities": object_schema}},
            ),
            "project.current.get": OperationDescriptor("project.current.get", output_schema=object_schema),
            "project.create": OperationDescriptor(
                "project.create",
                input_schema={"required": ["project_name"]},
                side_effect_level="write",
                idempotency_capability=True,
            ),
            "project.open": OperationDescriptor(
                "project.open",
                input_schema={"required": ["project_path"]},
                side_effect_level="write",
            ),
            "project.save": OperationDescriptor(
                "project.save",
                side_effect_level="write",
                idempotency_capability=True,
            ),
            "project.close": OperationDescriptor("project.close", side_effect_level="write"),
            "graph.get": OperationDescriptor("graph.get", output_schema=object_schema),
            "graph.replace": OperationDescriptor(
                "graph.replace",
                input_schema={"required": ["graph_document"]},
                side_effect_level="write",
                idempotency_capability=True,
            ),
            "graph.validate": OperationDescriptor(
                "graph.validate",
                input_schema={"required": ["graph_document"]},
            ),
            "graph.compile": OperationDescriptor("graph.compile", side_effect_level="write"),
            "graph.node_draft.build": OperationDescriptor(
                "graph.node_draft.build",
                input_schema={"required": ["resource_key"]},
            ),
            "execution.start": OperationDescriptor(
                "execution.start",
                side_effect_level="execute",
                execution_mode="async",
                idempotency_capability=True,
            ),
            "execution.get": OperationDescriptor(
                "execution.get",
                input_schema={"required": ["execution_id"]},
            ),
            "execution.cancel": OperationDescriptor(
                "execution.cancel",
                input_schema={"required": ["execution_id"]},
                side_effect_level="execute",
                idempotency_capability=True,
            ),
            "execution.events.subscribe": OperationDescriptor(
                "execution.events.subscribe",
                input_schema={"required": ["execution_id"]},
                execution_mode="async",
            ),
            "pending_input.get": OperationDescriptor(
                "pending_input.get",
                input_schema={"required": ["execution_id"]},
            ),
            "pending_input.submit": OperationDescriptor(
                "pending_input.submit",
                input_schema={"required": ["execution_id", "request_id", "values"]},
                side_effect_level="execute",
            ),
        }

    def _validate_input(self, descriptor: OperationDescriptor, payload: Mapping[str, object]) -> None:
        required = descriptor.input_schema.get("required", [])
        for field_name in required if isinstance(required, list) else []:
            if field_name not in payload:
                raise OperationRegistryError(
                    "operation.input_invalid",
                    f"missing required field: {field_name}",
                    operation_id=descriptor.operation_id,
                )
        if descriptor.operation_id == "project.create" and not isinstance(payload.get("project_name"), str):
            raise OperationRegistryError(
                "operation.input_invalid",
                "field must be a string: project_name",
                operation_id=descriptor.operation_id,
            )
        if descriptor.operation_id == "pending_input.submit" and not isinstance(payload.get("values"), dict):
            raise OperationRegistryError(
                "operation.input_invalid",
                "field must be an object: values",
                operation_id=descriptor.operation_id,
            )

    def _dispatch(self, operation_id: str, payload: dict[str, object]) -> object:
        service = self._service
        if operation_id == "host.describe":
            health = service.get_runtime_health()
            return {
                "service": "weconduct",
                "api_version": health.get("api_version"),
                "host_mode": health.get("host_mode"),
                **self._host_metadata,
            }
        if operation_id == "host.capabilities":
            return {"capabilities": service.get_runtime_health().get("capabilities", {})}
        if operation_id == "project.current.get":
            return _public_project_document(service.get_project_document())
        if operation_id == "project.create":
            return service.create_project(
                project_name=payload["project_name"],
                project_directory=payload.get("project_directory"),
            )
        if operation_id == "project.open":
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
            return service.save_graph_document(
                payload["graph_document"],
                expected_graph_document_save_revision=payload.get("expected_revision"),
            )
        if operation_id == "graph.validate":
            return service.validate_graph_document(payload["graph_document"])
        if operation_id == "graph.compile":
            return service.compile_graph_document(payload.get("graph_document"))
        if operation_id == "graph.node_draft.build":
            return service.build_graph_node_draft(
                resource_key=payload["resource_key"],
                node_id=payload.get("node_id"),
                position=payload.get("position"),
            )
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
            return service.abort_runtime_session(
                session_id=payload["execution_id"],
                reason=payload.get("reason", "external api cancellation"),
            )
        if operation_id == "execution.events.subscribe":
            return {"execution_id": payload["execution_id"], "stream": "sse"}
        if operation_id == "pending_input.get":
            snapshot = service.get_pending_input_snapshot(execution_id=payload["execution_id"])
            return _public_pending_input_snapshot(snapshot)
        if operation_id == "pending_input.submit":
            snapshot = service.submit_pending_input(
                execution_id=payload["execution_id"],
                request_id=payload["request_id"],
                values=payload["values"],
            )
            return _public_pending_input_snapshot(snapshot)
        raise OperationRegistryError("operation.not_found", f"operation not found: {operation_id}")

    @staticmethod
    def _filter_output(operation_id: str, result: dict[str, object]) -> dict[str, object]:
        if operation_id == "host.capabilities":
            return {"capabilities": result.get("capabilities", {})}
        if operation_id == "host.describe":
            return {
                key: result.get(key)
                for key in ("service", "api_version", "host_mode", "instance_id")
                if result.get(key) is not None
            }
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


def _normalize_dispatch_value_error(
    error: ValueError,
    *,
    operation_id: str,
) -> OperationRegistryError:
    explicit_code = getattr(error, "error_code", None)
    if isinstance(explicit_code, str) and explicit_code.strip():
        error_code = explicit_code.strip()
    else:
        message = str(error)
        if message == "pending input request was not found":
            error_code = "operation.not_found"
        elif message == "pending input request is not waiting":
            error_code = "operation.state_conflict"
        elif message.startswith("pending input"):
            error_code = "operation.input_invalid"
        else:
            error_code = "operation.execution_failed"
    details: dict[str, object] = {}
    for name in ("expected_revision", "current_revision", "recovery_action"):
        value = getattr(error, name, None)
        if value is not None:
            details[name] = value
    return OperationRegistryError(
        error_code,
        str(error),
        operation_id=operation_id,
        details=details,
    )


def _public_project_document(document: object) -> dict[str, object]:
    if not isinstance(document, Mapping):
        return {}
    project = document.get("project")
    if not isinstance(project, Mapping):
        return {"project": {}}
    allowed = {
        key: project.get(key)
        for key in (
            "project_id",
            "project_name",
            "project_schema_version",
            "project_status",
            "main_graph_document_id",
            "resource_registry_revision",
            "is_dirty",
            "last_compile_status",
            "last_runtime_status",
            "last_runtime_session_id",
        )
        if key in project
    }
    return {"project": allowed}


def _public_pending_input_snapshot(snapshot: object) -> dict[str, object]:
    if snapshot is None:
        return {"status": "none"}
    normalized = _normalize_value(snapshot)
    if not isinstance(normalized, dict):
        return {"status": "unknown"}
    fields = normalized.get("fields")
    if isinstance(fields, list):
        safe_fields = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            field_type = field.get("type", field.get("value_type"))
            safe_fields.append(
                {
                    key: field.get(key)
                    for key in ("field_id", "label", "type", "required", "sensitive")
                    if key in field
                }
            )
            if field_type is not None:
                safe_fields[-1]["type"] = field_type
        normalized["fields"] = safe_fields
    normalized.pop("values", None)
    return normalized
