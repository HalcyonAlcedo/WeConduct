from __future__ import annotations

from pydantic import BaseModel
import pytest

import weconduct.application.operations as operations
from weconduct.application.operations import OperationRegistry


def test_stable_public_descriptors_use_pydantic_input_and_output_models() -> None:
    registry = OperationRegistry.build_stable_public()
    descriptors = registry.list_descriptors(exposure="stable_public")

    assert len(descriptors) == 18
    for descriptor in descriptors:
        assert issubclass(descriptor.input_model, BaseModel)
        assert issubclass(descriptor.output_model, BaseModel)
        output_schema = descriptor.output_model.model_json_schema()
        assert output_schema["additionalProperties"] is False
        assert set(output_schema["properties"]) == set(descriptor.output_fields)


class _HostService:
    def __init__(self) -> None:
        self.created_project_count = 0

    def get_runtime_health(self) -> dict[str, object]:
        return {"api_version": "0.9", "capabilities": {"network": {"available": True}}}

    def create_project(
        self,
        *,
        project_name: str,
        project_directory: str | None,
    ) -> dict[str, object]:
        self.created_project_count += 1
        return {
            "project_name": project_name,
            "project_directory": project_directory,
            "created_project_count": self.created_project_count,
        }


def test_invoke_enforces_permissions_and_records_audited_result() -> None:
    audit_trail = operations.InMemoryOperationAuditTrail()
    operation_service = operations.HostOperationService(
        service=_HostService(),
        audit_trail=audit_trail,
    )

    with pytest.raises(operations.OperationRegistryError, match="permission") as denied:
        operation_service.invoke(
            "host.capabilities",
            {},
            caller=operations.OperationCaller(
                caller_id="external:denied",
                permissions=frozenset(),
            ),
        )
    assert denied.value.error_code == "operation.permission_denied"

    result = operation_service.invoke(
        "host.capabilities",
        {},
        caller=operations.OperationCaller(
            caller_id="external:allowed",
            permissions=frozenset({"operation.invoke"}),
        ),
    )

    assert result == {"capabilities": {"network": {"available": True}}}
    record = audit_trail.records[-1]
    assert record.operation_id == "host.capabilities"
    assert record.caller_id == "external:allowed"
    assert record.outcome == "succeeded"


def test_invoke_replays_idempotent_result_for_same_caller_and_key() -> None:
    host_service = _HostService()
    operation_service = operations.HostOperationService(service=host_service)
    caller = operations.OperationCaller(
        caller_id="external:caller-a",
        permissions=frozenset({"operation.invoke"}),
    )

    first = operation_service.invoke(
        "project.create",
        {"project_name": "demo"},
        caller=caller,
        idempotency_key="create-demo",
    )
    replay = operation_service.invoke(
        "project.create",
        {"project_name": "demo"},
        caller=caller,
        idempotency_key="create-demo",
    )

    assert host_service.created_project_count == 1
    assert replay == first
    assert first.replayed is False
    assert replay.replayed is True


def test_stable_operation_filters_undeclared_output_fields() -> None:
    result = operations.HostOperationService(service=_HostService()).invoke(
        "project.create",
        {"project_name": "demo"},
        caller=operations.OperationCaller(
            caller_id="external:output-contract",
            permissions=frozenset({"operation.invoke"}),
        ),
    )

    assert result == {"project_name": "demo", "project_directory": None}
