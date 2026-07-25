from __future__ import annotations

from typing import Mapping

from .models import OperationDescriptor, OperationRegistryError


class OperationRegistry:
    """只保存已显式注册的操作契约，不持有应用服务。"""

    def __init__(self, descriptors: Mapping[str, OperationDescriptor]) -> None:
        self._descriptors = dict(descriptors)

    @classmethod
    def build_stable_public(cls) -> "OperationRegistry":
        object_schema = {"type": "object"}
        descriptors = {
            "host.describe": OperationDescriptor(
                "host.describe",
                output_schema={"type": "object", "properties": {"api_version": {"type": "string"}}},
            ),
            "host.capabilities": OperationDescriptor(
                "host.capabilities",
                output_schema={"type": "object", "properties": {"capabilities": object_schema}},
            ),
            "project.current.get": OperationDescriptor("project.current.get", output_schema=object_schema),
            "project.create": OperationDescriptor("project.create", input_schema={"required": ["project_name"]}, side_effect_level="write", idempotency_capability=True),
            "project.open": OperationDescriptor("project.open", input_schema={"required": ["project_path"]}, side_effect_level="write"),
            "project.save": OperationDescriptor("project.save", side_effect_level="write", idempotency_capability=True),
            "project.close": OperationDescriptor("project.close", side_effect_level="write"),
            "graph.get": OperationDescriptor("graph.get", output_schema=object_schema),
            "graph.replace": OperationDescriptor("graph.replace", input_schema={"required": ["graph_document", "expected_revision"]}, side_effect_level="write", idempotency_capability=True),
            "graph.validate": OperationDescriptor("graph.validate", input_schema={"required": ["graph_document"]}),
            "graph.compile": OperationDescriptor("graph.compile", side_effect_level="write"),
            "graph.node_draft.build": OperationDescriptor("graph.node_draft.build", input_schema={"required": ["resource_key"]}),
            "execution.start": OperationDescriptor("execution.start", side_effect_level="execute", execution_mode="async", idempotency_capability=True),
            "execution.get": OperationDescriptor("execution.get", input_schema={"required": ["execution_id"]}),
            "execution.cancel": OperationDescriptor("execution.cancel", input_schema={"required": ["execution_id"]}, side_effect_level="execute", idempotency_capability=True),
            "execution.events.subscribe": OperationDescriptor("execution.events.subscribe", input_schema={"required": ["execution_id"]}, execution_mode="async"),
            "pending_input.get": OperationDescriptor("pending_input.get", input_schema={"required": ["execution_id"]}),
            "pending_input.submit": OperationDescriptor("pending_input.submit", input_schema={"required": ["execution_id", "request_id", "values"]}, side_effect_level="execute"),
        }
        return cls(descriptors)

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

    def validate_input(self, descriptor: OperationDescriptor, payload: Mapping[str, object]) -> None:
        required = descriptor.input_schema.get("required", [])
        for field_name in required if isinstance(required, list) else []:
            if field_name not in payload:
                raise OperationRegistryError("operation.input_invalid", f"missing required field: {field_name}", operation_id=descriptor.operation_id)
        if descriptor.operation_id == "project.create" and not isinstance(payload.get("project_name"), str):
            raise OperationRegistryError("operation.input_invalid", "field must be a string: project_name", operation_id=descriptor.operation_id)
        if descriptor.operation_id == "pending_input.submit" and not isinstance(payload.get("values"), dict):
            raise OperationRegistryError("operation.input_invalid", "field must be an object: values", operation_id=descriptor.operation_id)
        if descriptor.operation_id == "graph.replace":
            expected_revision = payload.get("expected_revision")
            if (
                not isinstance(expected_revision, int)
                or isinstance(expected_revision, bool)
                or expected_revision < 0
            ):
                raise OperationRegistryError(
                    "operation.input_invalid",
                    "field must be a non-negative integer: expected_revision",
                    operation_id=descriptor.operation_id,
                )
            graph_document = payload.get("graph_document")
            if not isinstance(graph_document, Mapping):
                raise OperationRegistryError(
                    "operation.input_invalid",
                    "field must be an object: graph_document",
                    operation_id=descriptor.operation_id,
                )
            document_id = graph_document.get("document_id")
            if document_id is not None and document_id != "graph:workspace":
                raise OperationRegistryError(
                    "operation.input_invalid",
                    "graph.replace only supports the workspace graph",
                    operation_id=descriptor.operation_id,
                )
