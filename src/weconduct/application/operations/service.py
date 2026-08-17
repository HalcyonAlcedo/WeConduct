from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Mapping
import platform

from weconduct.application.sensitive_values.redaction import redact_sensitive_payload
from weconduct._version import APP_VERSION

from .models import (
    InMemoryOperationAuditTrail,
    InMemoryOperationIdempotencyStore,
    IdempotencyCapability,
    OperationAuditRecord,
    OperationCaller,
    OperationDescriptor,
    OperationExposure,
    OperationInvocationResult,
    OperationRegistryError,
)
from .registry import OperationRegistry


_NOT_FOUND_DISPATCH_VALUE_ERROR_PREFIXES = (
    "debug session not found:",
    "debug history session not found:",
    "debug history event not found:",
    "debug history keyframe not found:",
    "runtime session not found:",
    "resource not found:",
    "resource not found for graph node draft:",
    "custom node graph resource not found:",
    "graph document not found:",
    "project file not found:",
)


class HostOperationService:
    """在契约校验、敏感遮罩后，将稳定 operation_id 委托给宿主服务。"""

    def __init__(
        self,
        *,
        service: object,
        registry: OperationRegistry | None = None,
        host_metadata: Mapping[str, object] | None = None,
        project_path_allowed_roots: tuple[str | Path, ...] | None = None,
        audit_trail: InMemoryOperationAuditTrail | None = None,
        idempotency_store: InMemoryOperationIdempotencyStore | None = None,
    ) -> None:
        self._service = service
        self._registry = registry or OperationRegistry.build_stable_public()
        self._host_metadata = dict(host_metadata or {})
        self._project_path_allowed_roots = (
            None
            if project_path_allowed_roots is None
            else tuple(Path(root).expanduser().resolve() for root in project_path_allowed_roots)
        )
        self._audit_trail = audit_trail or InMemoryOperationAuditTrail()
        self._idempotency_store = idempotency_store or InMemoryOperationIdempotencyStore()

    def list_descriptors(self, *, exposure: str | None = None):
        return self._registry.list_descriptors(exposure=exposure)

    def describe(self, operation_id: str):
        return self._registry.describe(operation_id)

    def invoke(
        self,
        operation_id: str,
        payload: Mapping[str, object] | None,
        *,
        caller: OperationCaller,
        idempotency_key: str | None = None,
    ) -> OperationInvocationResult:
        descriptor = self._registry.describe(operation_id)
        request = dict(payload or {})
        reserved_idempotency_key: str | None = None
        try:
            self._assert_permissions(descriptor.required_permissions, caller=caller, operation_id=operation_id)
            request = self._registry.validate_input(descriptor, request)
            if idempotency_key is not None and descriptor.idempotency_capability is IdempotencyCapability.SUPPORTED:
                normalized_key = idempotency_key.strip()
                if not normalized_key:
                    raise OperationRegistryError(
                        "operation.input_invalid",
                        "idempotency key must not be empty",
                        operation_id=operation_id,
                    )
                replay = self._idempotency_store.reserve_or_replay(
                    caller_id=caller.caller_id,
                    operation_id=operation_id,
                    idempotency_key=normalized_key,
                )
                if replay is not None:
                    return OperationInvocationResult(replay, replayed=True)
                reserved_idempotency_key = normalized_key
            result = self._dispatch(operation_id, request)
            normalized = _normalize_value(result)
            if not isinstance(normalized, dict):
                normalized = {"result": normalized}
            public_result = redact_sensitive_payload(self._filter_output(descriptor, normalized))
            validated_result = self._registry.validate_output(descriptor, public_result)
            if reserved_idempotency_key is not None:
                self._idempotency_store.complete(
                    caller_id=caller.caller_id,
                    operation_id=operation_id,
                    idempotency_key=reserved_idempotency_key,
                    result=validated_result,
                )
        except OperationRegistryError as exc:
            self._release_idempotency_reservation(
                caller=caller,
                operation_id=operation_id,
                idempotency_key=reserved_idempotency_key,
            )
            self._record_audit(
                operation_id=operation_id,
                caller=caller,
                outcome="failed" if exc.error_code == "operation.output_invalid" else "rejected",
                payload=request,
            )
            raise
        except ValueError as exc:
            self._release_idempotency_reservation(
                caller=caller,
                operation_id=operation_id,
                idempotency_key=reserved_idempotency_key,
            )
            error = _normalize_dispatch_value_error(exc, operation_id=operation_id)
            self._record_audit(
                operation_id=operation_id,
                caller=caller,
                outcome="failed",
                payload=request,
            )
            raise error from exc
        except Exception as exc:
            self._release_idempotency_reservation(
                caller=caller,
                operation_id=operation_id,
                idempotency_key=reserved_idempotency_key,
            )
            self._record_audit(
                operation_id=operation_id,
                caller=caller,
                outcome="failed",
                payload=request,
            )
            raise OperationRegistryError("operation.execution_failed", str(exc), operation_id=operation_id) from exc
        self._record_audit(
            operation_id=operation_id,
            caller=caller,
            outcome="succeeded",
            payload=request,
        )
        return OperationInvocationResult(validated_result, replayed=False)

    def _release_idempotency_reservation(
        self,
        *,
        caller: OperationCaller,
        operation_id: str,
        idempotency_key: str | None,
    ) -> None:
        if idempotency_key is None:
            return
        self._idempotency_store.release(
            caller_id=caller.caller_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
        )

    @property
    def audit_trail(self) -> InMemoryOperationAuditTrail:
        return self._audit_trail

    def _assert_permissions(
        self,
        required_permissions: frozenset[str],
        *,
        caller: OperationCaller,
        operation_id: str,
    ) -> None:
        if required_permissions.issubset(caller.permissions):
            return
        raise OperationRegistryError(
            "operation.permission_denied",
            "caller does not have the required operation permission",
            operation_id=operation_id,
            details={"required_permissions": sorted(required_permissions)},
        )

    def _record_audit(
        self,
        *,
        operation_id: str,
        caller: OperationCaller,
        outcome: str,
        payload: Mapping[str, object],
    ) -> None:
        audit_payload = dict(payload)
        if operation_id == "pending_input.submit" and "values" in audit_payload:
            values = audit_payload["values"]
            if isinstance(values, Mapping):
                # 待输入字段的敏感性由请求定义决定；审计层不持有该定义，
                # 因此只保留字段名，统一丢弃所有提交值。
                audit_payload["values"] = {
                    str(field_id): "<redacted>"
                    for field_id in values
                }
            else:
                audit_payload["values"] = "<redacted>"
        self._audit_trail.append(
            OperationAuditRecord(
                operation_id=operation_id,
                caller_id=caller.caller_id,
                outcome=outcome,  # type: ignore[arg-type]
                input_summary=redact_sensitive_payload(audit_payload),
            )
        )

    def _dispatch(self, operation_id: str, payload: dict[str, object]) -> object:
        service = self._service
        if operation_id == "operation.list":
            descriptors = self._registry.list_descriptors(
                exposure=OperationExposure.STABLE_PUBLIC.value,
            )
            return {
                "operations": [
                    descriptor.to_dict()
                    for descriptor in sorted(descriptors, key=lambda item: item.operation_id)
                ]
            }
        if operation_id == "operation.get":
            descriptor = self._registry.describe(payload["operation_id"])
            if descriptor.exposure is not OperationExposure.STABLE_PUBLIC:
                raise OperationRegistryError(
                    "operation.not_found",
                    f"operation not found: {payload['operation_id']}",
                    operation_id=payload["operation_id"],
                )
            return {"operation": descriptor.to_dict()}
        if operation_id == "host.describe":
            health = service.get_runtime_health()
            return {
                "service": "weconduct",
                "application_version": APP_VERSION,
                "platform": platform.system().strip().lower(),
                "api_version": health.get("api_version"),
                "host_mode": health.get("host_mode"),
                "instance_id": self._host_metadata.get(
                    "instance_id",
                    health.get("workspace_session_id"),
                ),
            }
        if operation_id == "host.capabilities":
            return {"capabilities": service.get_runtime_health().get("capabilities", {})}
        if operation_id == "configuration.schema.get":
            return service.get_configuration_schema(scope=payload["scope"])
        if operation_id == "configuration.values.get":
            return service.get_configuration_values(scope=payload["scope"])
        if operation_id == "configuration.preview":
            return service.preview_configuration(scope=payload["scope"], operations=payload["operations"])
        if operation_id == "configuration.apply":
            if payload["scope"] == "program":
                raise OperationRegistryError(
                    "operation.not_available",
                    "program configuration cannot be applied through external API",
                    operation_id=operation_id,
                )
            return service.apply_configuration(
                scope=payload["scope"],
                operations=payload["operations"],
                confirm_high_risk=payload["confirm_high_risk"],
            )
        if operation_id == "configuration.reset":
            if payload["scope"] == "program":
                raise OperationRegistryError(
                    "operation.not_available",
                    "program configuration cannot be reset through external API",
                    operation_id=operation_id,
                )
            return service.reset_configuration(scope=payload["scope"])
        if operation_id == "debug.prepare":
            return service.prepare_debug_session(payload.get("graph_document"))
        if operation_id == "debug.start":
            return service.start_debug_session_async(payload.get("graph_document"))
        if operation_id == "debug.list":
            return service.list_debug_sessions()
        if operation_id == "debug.history.list":
            return service.list_debug_history_sessions()
        if operation_id == "debug.history.get":
            return service.open_debug_history_session(session_id=payload["session_id"])
        if operation_id == "debug.history.events":
            return service.list_debug_session_events(session_id=payload["session_id"])
        if operation_id == "debug.history.projection":
            return service.get_debug_history_projection(
                session_id=payload["session_id"],
                event_index=payload.get("event_index"),
                keyframe_id=payload.get("keyframe_id"),
            )
        if operation_id == "debug.live_projection":
            return service.get_debug_live_projection(session_id=payload["session_id"])
        if operation_id == "debug.get":
            return service.get_debug_session(session_id=payload["session_id"])
        if operation_id == "debug.continue":
            return service.continue_debug_session_async(session_id=payload["session_id"])
        if operation_id == "debug.pause":
            return service.request_debug_pause(session_id=payload["session_id"], node_id=payload.get("node_id"), reason=payload["reason"])
        if operation_id == "debug.step_over":
            return service.step_over_debug_session_async(session_id=payload["session_id"])
        if operation_id == "debug.step_into":
            return service.step_into_debug_session_async(session_id=payload["session_id"])
        if operation_id == "debug.step_out":
            return service.step_out_debug_session_async(session_id=payload["session_id"])
        if operation_id == "debug.abort":
            return service.abort_debug_session(session_id=payload["session_id"], reason=payload["reason"])
        if operation_id == "debug.variables.apply":
            return service.apply_debug_session_variables(session_id=payload["session_id"], updates=payload["updates"], apply_mode=payload["apply_mode"])
        if operation_id == "debug.node_debugger.apply":
            return service.update_debug_session_node_debugger(session_id=payload["session_id"], node_id=payload["node_id"], debugger_config=payload["debugger"])
        if operation_id == "debug.parameters.unlock":
            return service.unlock_debug_session_parameters(session_id=payload["session_id"], password=payload["password"])
        if operation_id == "resource.list":
            return service.get_resource_registry_document(**_catalogue_filter_payload(payload))
        if operation_id == "component.list":
            return service.get_component_library_document(**_catalogue_filter_payload(payload))
        if operation_id in {
            "resource.user_component.save",
            "resource.subgraph.save",
            "resource.custom_node_graph.save",
        }:
            save_resource = {
                "resource.user_component.save": service.save_user_component_resource,
                "resource.subgraph.save": service.save_subgraph_resource,
                "resource.custom_node_graph.save": service.save_custom_node_graph_resource,
            }[operation_id]
            saved = save_resource(
                resource_name=payload["resource_name"],
                replace_existing_resource_id=payload.get("replace_existing_resource_id"),
            )
            tags = payload.get("tags")
            result = saved if tags is None else service.update_resource_tags(
                resource_id=saved["resource"]["resource_id"],
                tags=tags,
            )
            service.publish_resource_registry_changed(reason="external_resource_saved")
            return result
        if operation_id == "resource.custom_node_graph.create":
            result = service.create_empty_custom_node_graph_resource(
                resource_name=payload["resource_name"],
            )
            service.publish_resource_registry_changed(reason="resource_created")
            return result
        if operation_id == "resource.enabled.set":
            result = service.set_resource_enabled(
                resource_id=payload["resource_id"],
                enabled=payload["enabled"],
            )
            service.publish_resource_registry_changed(reason="external_resource_enabled")
            return result
        if operation_id == "resource.tags.set":
            result = service.update_resource_tags(
                resource_id=payload["resource_id"],
                tags=payload["tags"],
            )
            service.publish_resource_registry_changed(reason="external_resource_tags")
            return result
        if operation_id == "resource.metadata.update":
            result = service.update_resource_metadata(
                resource_id=payload["resource_id"],
                display_name=payload["display_name"],
                description=payload.get("description"),
                display_name_i18n=payload.get("display_name_i18n"),
                description_i18n=payload.get("description_i18n"),
            )
            service.publish_resource_registry_changed(reason="external_resource_metadata")
            return result
        if operation_id == "resource.rename":
            result = service.rename_resource(
                resource_id=payload["resource_id"],
                display_name=payload["display_name"],
            )
            service.publish_resource_registry_changed(reason="external_resource_renamed")
            return result
        if operation_id == "resource.delete":
            result = service.delete_resource(resource_id=payload["resource_id"])
            service.publish_resource_registry_changed(reason="external_resource_deleted")
            return result
        if operation_id == "project.current.get":
            return _public_project_document(service.get_project_document())
        if operation_id == "project.resource_audit.get":
            return service.get_project_resource_audit_document()
        if operation_id == "project.create":
            project_directory = payload.get("project_directory")
            if project_directory is not None:
                self._assert_project_path_allowed(
                    project_directory,
                    operation_id=operation_id,
                )
            created = service.create_project(
                project_name=payload["project_name"],
                project_directory=project_directory,
            )
            return _with_current_graph_revision(service, created)
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
        if operation_id == "project.documents.list":
            return service.get_project_documents_document()
        if operation_id == "graph.get":
            return service.get_graph_document(document_id=payload.get("document_id"))
        if operation_id == "graph.context":
            return service.get_graph_context(**payload)
        if operation_id == "graph.document.get":
            return service.get_graph_document(document_id=payload["document_id"])
        if operation_id == "graph.document.replace":
            return service.save_graph_document(
                payload["graph_document"],
                expected_graph_document_save_revision=payload["expected_revision"],
                require_expected_revision=True,
            )
        if operation_id == "graph.replace":
            return service.save_graph_document(
                payload["graph_document"],
                expected_graph_document_save_revision=payload["expected_revision"],
                require_expected_revision=True,
            )
        if operation_id == "graph.patch.preview":
            return service.preview_graph_patch(
                expected_revision=payload["expected_revision"],
                operations=payload["operations"],
            )
        if operation_id == "graph.patch.apply":
            return service.apply_graph_patch(
                expected_revision=payload["expected_revision"],
                operations=payload["operations"],
            )
        if operation_id == "graph.validate":
            return service.validate_graph_document(payload["graph_document"])
        if operation_id == "graph.normalize":
            return service.normalize_graph_document(payload["graph_document"])
        if operation_id == "graph.compile":
            return service.compile_graph_document(payload.get("graph_document"))
        if operation_id == "graph.node_draft.build":
            return service.build_graph_node_draft(resource_key=payload["resource_key"], node_id=payload.get("node_id"), position=payload.get("position"))
        if operation_id == "graph.source_projection":
            return service.get_graph_source_projection_document(
                target_source_kind=payload["target_source_kind"],
            )
        if operation_id == "runtime.list":
            return service.list_runtime_sessions()
        if operation_id == "execution.history.get":
            return service.get_execution_history_document()
        if operation_id == "execution.prepare":
            return service.prepare_runtime_session(payload.get("graph_document"))
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
        if operation_id == "execution.parameters.unlock":
            unlocked = service.unlock_runtime_session_parameters(
                session_id=payload["execution_id"],
                password=payload["password"],
            )
            resumed = service.start_runtime_session_execution(
                session_id=payload["execution_id"]
            )
            return {
                "status": resumed.get("status", unlocked.get("status")),
                "parameter_ids": unlocked.get("parameter_ids", []),
            }
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
    def _filter_output(
        descriptor: OperationDescriptor,
        result: dict[str, object],
    ) -> dict[str, object]:
        return {
            key: value
            for key, value in result.items()
            if key in descriptor.output_fields
        }


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


def _catalogue_filter_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        field: payload[field]
        for field in ("query", "tags", "enabled", "origin", "resource_type", "limit")
        if payload.get(field) is not None
    }


def _normalize_dispatch_value_error(error: ValueError, *, operation_id: str) -> OperationRegistryError:
    message = str(error)
    explicit_code = getattr(error, "error_code", None)
    if isinstance(explicit_code, str) and explicit_code.strip():
        error_code = explicit_code.strip()
    elif message == "pending input request was not found":
        error_code = "operation.not_found"
    elif message.startswith(_NOT_FOUND_DISPATCH_VALUE_ERROR_PREFIXES):
        error_code = "operation.not_found"
    elif message == "pending input request is not waiting":
        error_code = "operation.state_conflict"
    elif message.startswith("pending input"):
        error_code = "operation.input_invalid"
    elif message in {"project.close_active_execution", "project.close_unsaved_changes"}:
        error_code = "operation.state_conflict"
    elif (
        isinstance(getattr(error, "expected_revision", None), int)
        and isinstance(getattr(error, "current_revision", None), int)
    ):
        error_code = "graph.revision_conflict"
    else:
        error_code = "operation.execution_failed"
    details = {
        name: value
        for name in ("expected_revision", "current_revision", "recovery_action", "state")
        if (value := getattr(error, name, None)) is not None
    }
    raw_details = getattr(error, "details", None)
    if isinstance(raw_details, Mapping):
        for name in (
            "validation_kind",
            "field_id",
            "field_ids",
            "expected_type",
            "actual_type",
        ):
            value = raw_details.get(name)
            if name == "field_ids":
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    details[name] = list(value)
            elif isinstance(value, str):
                details[name] = value
    if message.startswith("project.close_"):
        details["state"] = message.removeprefix("project.close_")
    return OperationRegistryError(error_code, message, operation_id=operation_id, details=details)


def _public_project_document(document: object) -> dict[str, object]:
    if not isinstance(document, Mapping):
        return {}
    project = document.get("project")
    if not isinstance(project, Mapping):
        return {"project": {}}
    allowed = {key: project.get(key) for key in ("project_id", "project_name", "project_schema_version", "project_status", "main_graph_document_id", "resource_registry_revision", "is_dirty", "last_compile_status", "last_runtime_status", "last_runtime_session_id") if key in project}
    public_document: dict[str, object] = {"project": allowed}
    graph_workspace = document.get("graph_workspace")
    if isinstance(graph_workspace, Mapping):
        revision = graph_workspace.get("graph_document_save_revision")
        if isinstance(revision, int) and revision >= 0:
            public_document["revision"] = revision
    return public_document


def _with_current_graph_revision(service: object, result: object) -> object:
    if not isinstance(result, Mapping):
        return result
    get_graph_document = getattr(service, "get_graph_document", None)
    if not callable(get_graph_document):
        return result
    graph_document = get_graph_document()
    if not isinstance(graph_document, Mapping):
        return result
    revision = graph_document.get("revision")
    if not isinstance(revision, int) or revision < 0:
        return result
    return {**result, "revision": revision}


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
