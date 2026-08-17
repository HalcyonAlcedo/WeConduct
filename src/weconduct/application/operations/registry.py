from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .models import (
    ConfigurationOperationsInput,
    ConfigurationScopeInput,
    EmptyOperationInput,
    ExecutionCancelInput,
    ExecutionParameterUnlockInput,
    ExecutionReferenceInput,
    ExecutionStartInput,
    DebugAbortInput,
    DebugHistoryProjectionInput,
    DebugNodeDebuggerApplyInput,
    DebugParameterUnlockInput,
    DebugPauseInput,
    DebugSessionInput,
    DebugVariablesApplyInput,
    GraphDocumentInput,
    GraphDocumentGetInput,
    GraphDocumentReplaceInput,
    GraphContextInput,
    GraphGetInput,
    GraphNodeDraftBuildInput,
    GraphPatchInput,
    GraphReplaceInput,
    GraphSourceProjectionInput,
    IdempotencyCapability,
    OperationGetInput,
    OperationDescriptor,
    OperationRegistryError,
    PendingInputSubmitInput,
    ProjectCreateInput,
    ProjectOpenInput,
    ProjectSaveInput,
    PublicOperationOutput,
    ResourceEnabledSetInput,
    ResourceCatalogueListInput,
    ResourceMetadataUpdateInput,
    ResourceReferenceInput,
    ResourceRenameInput,
    ResourceSaveInput,
    ResourceTagsSetInput,
    SideEffectLevel,
    build_public_output_model,
)


class OperationRegistry:
    """只保存已显式注册的操作契约，不持有应用服务。"""

    def __init__(self, descriptors: Mapping[str, OperationDescriptor]) -> None:
        self._descriptors = dict(descriptors)

    @classmethod
    def build_stable_public(cls) -> "OperationRegistry":
        def descriptor(
            operation_id: str,
            *output_fields: str,
            **kwargs: object,
        ) -> OperationDescriptor:
            fields = frozenset(output_fields)
            return OperationDescriptor(
                operation_id,
                output_model=build_public_output_model(
                    f"{operation_id.replace('.', '_').title().replace('_', '')}Output",
                    fields,
                ),
                output_fields=fields,
                **kwargs,
            )

        descriptors = {
            "configuration.schema.get": descriptor("configuration.schema.get", "scope", "domains", input_model=ConfigurationScopeInput),
            "configuration.values.get": descriptor("configuration.values.get", "scope", "values", input_model=ConfigurationScopeInput),
            "configuration.preview": descriptor("configuration.preview", "scope", "current_values", "proposed_values", "confirmation_required", "high_risk_changes", input_model=ConfigurationOperationsInput),
            "configuration.apply": descriptor("configuration.apply", "scope", "values", input_model=ConfigurationOperationsInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "configuration.reset": descriptor("configuration.reset", "scope", "values", input_model=ConfigurationScopeInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "operation.list": descriptor("operation.list", "operations"),
            "operation.get": descriptor("operation.get", "operation", input_model=OperationGetInput),
            "host.describe": descriptor(
                "host.describe",
                "service",
                "application_version",
                "platform",
                "api_version",
                "host_mode",
                "instance_id",
            ),
            "host.capabilities": descriptor("host.capabilities", "capabilities"),
            "debug.prepare": descriptor("debug.prepare", "status", "request", "stage_timeline", "object_index", "diagnostic_links", "runtime_preview", "runtime_preview_summary", "message", "details", input_model=ExecutionStartInput),
            "debug.start": descriptor("debug.start", "status", "debug_session", "request", "runtime_plan", "runtime_preview", "runtime_preview_summary", "diagnostic_links", "diagnostics", "message", "details", input_model=ExecutionStartInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async", idempotency_capability=IdempotencyCapability.SUPPORTED),
            "debug.list": descriptor("debug.list", "sessions"),
            "debug.history.list": descriptor("debug.history.list", "summary", "sessions"),
            "debug.history.get": descriptor("debug.history.get", "source", "session_id", "session", input_model=DebugSessionInput),
            "debug.history.events": descriptor("debug.history.events", "source", "session_id", "total_count", "events", input_model=DebugSessionInput),
            "debug.history.projection": descriptor("debug.history.projection", "source", "session_id", "projection", "runtime_preview", "variable_snapshot", input_model=DebugHistoryProjectionInput),
            "debug.live_projection": descriptor("debug.live_projection", "source", "session_id", "projection", input_model=DebugSessionInput),
            "debug.get": descriptor("debug.get", "status", "debug_session", "request", "runtime_plan", "runtime_preview", "runtime_preview_summary", "debug_events", "variable_snapshot", "variable_descriptors", "variable_changes", input_model=DebugSessionInput),
            "debug.continue": descriptor("debug.continue", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugSessionInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.pause": descriptor("debug.pause", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugPauseInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.step_over": descriptor("debug.step_over", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugSessionInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.step_into": descriptor("debug.step_into", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugSessionInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.step_out": descriptor("debug.step_out", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugSessionInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.abort": descriptor("debug.abort", "status", "debug_session", "runtime_preview", "runtime_preview_summary", "debug_events", input_model=DebugAbortInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "debug.variables.apply": descriptor("debug.variables.apply", "status", "debug_session", "variable_snapshot", "variable_changes", input_model=DebugVariablesApplyInput, side_effect_level=SideEffectLevel.WRITE),
            "debug.node_debugger.apply": descriptor("debug.node_debugger.apply", "status", "debug_session", "runtime_preview", input_model=DebugNodeDebuggerApplyInput, side_effect_level=SideEffectLevel.WRITE),
            "debug.parameters.unlock": descriptor("debug.parameters.unlock", "status", "debug_session", "runtime_preview", "runtime_preview_summary", input_model=DebugParameterUnlockInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async"),
            "resource.list": descriptor(
                "resource.list",
                "registry_revision",
                "resource_types",
                "summary",
                "facets",
                "resources",
                "total_matched_count",
                "truncated",
                input_model=ResourceCatalogueListInput,
            ),
            "component.list": descriptor(
                "component.list",
                "summary",
                "facets",
                "items",
                "total_matched_count",
                "truncated",
                input_model=ResourceCatalogueListInput,
            ),
            "resource.user_component.save": descriptor("resource.user_component.save", "status", "registry_revision", "resource", input_model=ResourceSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.subgraph.save": descriptor("resource.subgraph.save", "status", "registry_revision", "resource", input_model=ResourceSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.custom_node_graph.save": descriptor("resource.custom_node_graph.save", "status", "registry_revision", "resource", input_model=ResourceSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.custom_node_graph.create": descriptor("resource.custom_node_graph.create", "status", "registry_revision", "resource", input_model=ResourceSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.enabled.set": descriptor("resource.enabled.set", "status", "registry_revision", "resource", input_model=ResourceEnabledSetInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.tags.set": descriptor("resource.tags.set", "status", "registry_revision", "resource", input_model=ResourceTagsSetInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.metadata.update": descriptor("resource.metadata.update", "status", "registry_revision", "resource", input_model=ResourceMetadataUpdateInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.rename": descriptor("resource.rename", "status", "registry_revision", "resource", input_model=ResourceRenameInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "resource.delete": descriptor("resource.delete", "status", "registry_revision", "resource", input_model=ResourceReferenceInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.current.get": descriptor("project.current.get", "project", "revision"),
            "project.resource_audit.get": descriptor("project.resource_audit.get", "status", "project_file_path", "storage_root", "summary", "resources", "issues"),
            "project.create": descriptor("project.create", "status", "project", "graph_document", "project_name", "project_directory", "revision", input_model=ProjectCreateInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.open": descriptor("project.open", "status", "project", "graph_document", input_model=ProjectOpenInput, side_effect_level=SideEffectLevel.WRITE),
            "project.save": descriptor("project.save", "status", "project", "graph_document", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.close": descriptor("project.close", "status", "project", side_effect_level=SideEffectLevel.WRITE),
            "graph.get": descriptor("graph.get", "graph_model", "view", "revision", input_model=GraphGetInput),
            "graph.context": descriptor(
                "graph.context",
                "revision",
                "focus_node",
                "neighbors",
                "incoming_edges",
                "outgoing_edges",
                "context_nodes",
                "truncated",
                "limits",
                input_model=GraphContextInput,
            ),
            "project.documents.list": descriptor(
                "project.documents.list",
                "main_graph_document_id",
                "documents",
                "project_file",
                "graph_document",
                "project_owned_resources_index",
                "resource_overrides",
            ),
            "graph.document.get": descriptor(
                "graph.document.get",
                "graph_model",
                "view",
                "revision",
                input_model=GraphDocumentGetInput,
            ),
            "graph.document.replace": descriptor(
                "graph.document.replace",
                "status",
                "graph_model",
                "view",
                "graph_document",
                "expected_revision",
                "require_expected_revision",
                input_model=GraphDocumentReplaceInput,
                side_effect_level=SideEffectLevel.WRITE,
                idempotency_capability=IdempotencyCapability.SUPPORTED,
            ),
            "graph.replace": descriptor("graph.replace", "status", "graph_model", "view", "graph_document", "expected_revision", "require_expected_revision", input_model=GraphReplaceInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "graph.patch.preview": descriptor(
                "graph.patch.preview",
                "status",
                "base_revision",
                "affected_node_ids",
                "affected_edge_ids",
                "diagnostics",
                "patch_summary",
                "graph_summary",
                "operations",
                input_model=GraphPatchInput,
            ),
            "graph.patch.apply": descriptor(
                "graph.patch.apply",
                "status",
                "base_revision",
                "new_revision",
                "affected_node_ids",
                "affected_edge_ids",
                "diagnostics",
                "patch_summary",
                "graph_summary",
                "operations",
                input_model=GraphPatchInput,
                side_effect_level=SideEffectLevel.WRITE,
                idempotency_capability=IdempotencyCapability.SUPPORTED,
            ),
            "graph.validate": descriptor("graph.validate", "status", "graph_model", "summary", "diagnostics", input_model=GraphDocumentInput),
            "graph.normalize": descriptor("graph.normalize", "status", "changed", "graph_model", "view", input_model=GraphDocumentInput),
            "graph.compile": descriptor("graph.compile", "status", "request", "outcome", "view", "diagnostics", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE),
            "graph.node_draft.build": descriptor("graph.node_draft.build", "resource", "node", "parameter_schema", "resource_key", "node_id", "position", input_model=GraphNodeDraftBuildInput),
            "graph.source_projection": descriptor("graph.source_projection", "status", "source_kind", "request_origin", "graph_model_id", "graph_document_save_revision", "entry_document", "source_text", "diagnostics", input_model=GraphSourceProjectionInput),
            "runtime.list": descriptor("runtime.list", "sessions"),
            "execution.history.get": descriptor("execution.history.get", "summary", "runtime_runs", "debug_sessions"),
            "execution.prepare": descriptor("execution.prepare", "status", "request", "runtime_plan", "diagnostics", input_model=ExecutionStartInput),
            "execution.start": descriptor("execution.start", "status", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", "diagnostics", "diagnostic_links", "object_index", "message", "details", "runtime_preview", "runtime_preview_summary", input_model=ExecutionStartInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async", idempotency_capability=IdempotencyCapability.SUPPORTED),
            "execution.get": descriptor("execution.get", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", input_model=ExecutionReferenceInput),
            "execution.cancel": descriptor("execution.cancel", "status", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", input_model=ExecutionCancelInput, side_effect_level=SideEffectLevel.EXECUTE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "execution.parameters.unlock": descriptor("execution.parameters.unlock", "status", "parameter_ids", input_model=ExecutionParameterUnlockInput, side_effect_level=SideEffectLevel.EXECUTE),
            "execution.events.subscribe": descriptor("execution.events.subscribe", "execution_id", "stream", input_model=ExecutionReferenceInput, execution_mode="async"),
            "pending_input.get": descriptor("pending_input.get", "execution_id", "request_id", "status", "fields", "timeout_seconds", "created_at", "deadline", input_model=ExecutionReferenceInput),
            "pending_input.submit": descriptor("pending_input.submit", "execution_id", "request_id", "status", "fields", "timeout_seconds", "created_at", "deadline", input_model=PendingInputSubmitInput, side_effect_level=SideEffectLevel.EXECUTE),
        }
        return cls(descriptors)

    def list_descriptors(self, *, exposure: str | None = None) -> list[OperationDescriptor]:
        descriptors = list(self._descriptors.values())
        if exposure is not None:
            descriptors = [item for item in descriptors if item.exposure.value == exposure]
        return descriptors

    def describe(self, operation_id: str) -> OperationDescriptor:
        descriptor = self._descriptors.get(operation_id)
        if descriptor is None:
            raise OperationRegistryError("operation.not_found", f"operation not found: {operation_id}")
        return descriptor

    def validate_input(
        self,
        descriptor: OperationDescriptor,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        try:
            return descriptor.input_model.model_validate(dict(payload)).model_dump(
                mode="python",
                exclude_none=False,
            )
        except ValidationError as exc:
            raise OperationRegistryError(
                "operation.input_invalid",
                "operation input does not match its schema",
                operation_id=descriptor.operation_id,
                details={"validation_errors": _public_validation_errors(exc)},
            ) from exc

    def validate_output(
        self,
        descriptor: OperationDescriptor,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        try:
            return descriptor.output_model.model_validate(dict(payload)).model_dump(
                mode="json",
                exclude_unset=True,
            )
        except ValidationError as exc:
            raise OperationRegistryError(
                "operation.output_invalid",
                "operation output does not match its schema",
                operation_id=descriptor.operation_id,
                details={"validation_errors": _public_validation_errors(exc)},
            ) from exc


def _public_validation_errors(exc: ValidationError) -> list[dict[str, object]]:
    """只保留可诊断字段，避免 Pydantic 的 input/ctx 回显敏感载荷。"""
    public_errors: list[dict[str, object]] = []
    for error in exc.errors(include_url=False):
        public_error = {
            key: error[key]
            for key in ("type", "loc", "msg")
            if key in error
        }
        public_errors.append(public_error)
    return public_errors
