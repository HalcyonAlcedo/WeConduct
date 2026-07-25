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
)


class OperationRegistry:
    """只保存已显式注册的操作契约，不持有应用服务。"""

    def __init__(self, descriptors: Mapping[str, OperationDescriptor]) -> None:
        self._descriptors = dict(descriptors)

    @classmethod
    def build_stable_public(cls) -> "OperationRegistry":
        descriptors = {
            "host.describe": OperationDescriptor(
                "host.describe",
            ),
            "host.capabilities": OperationDescriptor(
                "host.capabilities",
            ),
            "project.current.get": OperationDescriptor("project.current.get"),
            "project.create": OperationDescriptor("project.create", input_model=ProjectCreateInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.open": OperationDescriptor("project.open", input_model=ProjectOpenInput, side_effect_level=SideEffectLevel.WRITE),
            "project.save": OperationDescriptor("project.save", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "project.close": OperationDescriptor("project.close", side_effect_level=SideEffectLevel.WRITE),
            "graph.get": OperationDescriptor("graph.get", input_model=GraphGetInput),
            "graph.replace": OperationDescriptor("graph.replace", input_model=GraphReplaceInput, side_effect_level=SideEffectLevel.WRITE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "graph.validate": OperationDescriptor("graph.validate", input_model=GraphDocumentInput),
            "graph.compile": OperationDescriptor("graph.compile", input_model=ProjectSaveInput, side_effect_level=SideEffectLevel.WRITE),
            "graph.node_draft.build": OperationDescriptor("graph.node_draft.build", input_model=GraphNodeDraftBuildInput),
            "execution.start": OperationDescriptor("execution.start", input_model=ExecutionStartInput, side_effect_level=SideEffectLevel.EXECUTE, execution_mode="async", idempotency_capability=IdempotencyCapability.SUPPORTED),
            "execution.get": OperationDescriptor("execution.get", input_model=ExecutionReferenceInput),
            "execution.cancel": OperationDescriptor("execution.cancel", input_model=ExecutionCancelInput, side_effect_level=SideEffectLevel.EXECUTE, idempotency_capability=IdempotencyCapability.SUPPORTED),
            "execution.events.subscribe": OperationDescriptor("execution.events.subscribe", input_model=ExecutionReferenceInput, execution_mode="async"),
            "pending_input.get": OperationDescriptor("pending_input.get", input_model=ExecutionReferenceInput),
            "pending_input.submit": OperationDescriptor("pending_input.submit", input_model=PendingInputSubmitInput, side_effect_level=SideEffectLevel.EXECUTE),
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
            )
        except ValidationError as exc:
            raise OperationRegistryError(
                "operation.output_invalid",
                "operation output does not match its schema",
                operation_id=descriptor.operation_id,
                details={"validation_errors": exc.errors(include_url=False)},
            ) from exc
