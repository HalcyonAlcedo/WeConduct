from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .models import (
    EmptyOperationInput,
    ExecutionCancelInput,
    ExecutionReferenceInput,
    ExecutionStartInput,
    GraphDocumentInput,
    GraphGetInput,
    GraphNodeDraftBuildInput,
    GraphReplaceInput,
    IdempotencyCapability,
    OperationDescriptor,
    OperationRegistryError,
    PendingInputSubmitInput,
    ProjectCreateInput,
    ProjectOpenInput,
    ProjectSaveInput,
    PublicOperationOutput,
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
            "project.current.get": descriptor("project.current.get", "project", "revision"),
            "project.create": descriptor("project.create", "status", "project", "graph_document", "project_name", "project_directory", "revision", input_model=ProjectCreateInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.open": descriptor("project.open", "status", "project", "graph_document", input_model=ProjectOpenInput, side_effect_level=SideEffectLevel.WRITE),
            "project.save": descriptor("project.save", "status", "project", "graph_document", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.close": descriptor("project.close", "status", "project", side_effect_level=SideEffectLevel.WRITE),
            "graph.get": descriptor("graph.get", "graph_model", "view", "revision", input_model=GraphGetInput),
            "graph.replace": descriptor("graph.replace", "status", "graph_model", "view", "graph_document", "expected_revision", "require_expected_revision", input_model=GraphReplaceInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "graph.validate": descriptor("graph.validate", "status", "graph_model", "summary", "diagnostics", input_model=GraphDocumentInput),
            "graph.compile": descriptor("graph.compile", "status", "request", "outcome", "view", "diagnostics", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE),
            "graph.node_draft.build": descriptor("graph.node_draft.build", "resource", "node", "parameter_schema", "resource_key", "node_id", "position", input_model=GraphNodeDraftBuildInput),
            "execution.start": descriptor("execution.start", "status", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", "diagnostics", "diagnostic_links", "object_index", "message", "details", "runtime_preview", "runtime_preview_summary", input_model=ExecutionStartInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async", idempotency_capability=IdempotencyCapability.SUPPORTED),
            "execution.get": descriptor("execution.get", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", input_model=ExecutionReferenceInput),
            "execution.cancel": descriptor("execution.cancel", "status", "request", "runtime_session", "runtime_plan", "node_states", "debug_snapshot", "diagnostic_events", "execution_summary", "result", input_model=ExecutionCancelInput, side_effect_level=SideEffectLevel.EXECUTE, idempotency_capability=IdempotencyCapability.SUPPORTED),
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
                details={"validation_errors": exc.errors(include_url=False)},
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
                details={"validation_errors": exc.errors(include_url=False)},
            ) from exc
