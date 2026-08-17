from __future__ import annotations

import platform

from pydantic import BaseModel
import pytest

import weconduct.application.operations as operations
from weconduct.application.operations import OperationRegistry
from weconduct._version import APP_VERSION


def test_stable_public_descriptors_use_pydantic_input_and_output_models() -> None:
    registry = OperationRegistry.build_stable_public()
    descriptors = registry.list_descriptors(exposure="stable_public")

    assert len(descriptors) == 67
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


def test_host_describe_exposes_version_platform_and_instance_identity() -> None:
    result = operations.HostOperationService(
        service=_HostService(),
        host_metadata={"instance_id": "instance-contract-test"},
    ).invoke(
        "host.describe",
        {},
        caller=operations.OperationCaller(
            caller_id="external:host-describe-contract",
            permissions=frozenset({"operation.invoke"}),
        ),
    )

    assert result["application_version"] == APP_VERSION
    assert result["platform"] == platform.system().strip().lower()
    assert result["api_version"] == "0.9"
    assert result["instance_id"] == "instance-contract-test"


def test_project_current_exposes_project_summary_with_graph_revision() -> None:
    class _ProjectService(_HostService):
        def get_project_document(self) -> dict[str, object]:
            return {
                "project": {
                    "project_id": "project-contract-test",
                    "project_status": "ready",
                },
                "graph_workspace": {"graph_document_save_revision": 7},
            }

    result = operations.HostOperationService(service=_ProjectService()).invoke(
        "project.current.get",
        {},
        caller=operations.OperationCaller(
            caller_id="external:project-current-contract",
            permissions=frozenset({"operation.invoke"}),
        ),
    )

    assert result == {
        "project": {
            "project_id": "project-contract-test",
            "project_status": "ready",
        },
        "revision": 7,
    }


def test_project_create_exposes_new_graph_revision() -> None:
    class _ProjectCreateService(_HostService):
        def get_graph_document(self, *, document_id: str | None = None) -> dict[str, object]:
            assert document_id is None
            return {"revision": 8}

    result = operations.HostOperationService(service=_ProjectCreateService()).invoke(
        "project.create",
        {"project_name": "contract-project"},
        caller=operations.OperationCaller(
            caller_id="external:project-create-contract",
            permissions=frozenset({"operation.invoke"}),
        ),
    )

    assert result == {
        "project_name": "contract-project",
        "project_directory": None,
        "revision": 8,
    }


@pytest.mark.parametrize(
    ("failure", "state"),
    [
        ("project.close_active_execution", "active_execution"),
        ("project.close_unsaved_changes", "unsaved_changes"),
    ],
)
def test_project_close_returns_a_state_conflict_when_close_is_rejected(
    failure: str,
    state: str,
) -> None:
    class _ProjectCloseService(_HostService):
        def close_project(self) -> dict[str, object]:
            raise ValueError(failure)

    with pytest.raises(operations.OperationRegistryError) as error:
        operations.HostOperationService(service=_ProjectCloseService()).invoke(
            "project.close",
            {},
            caller=operations.OperationCaller(
                caller_id="external:project-close-contract",
                permissions=frozenset({"operation.invoke"}),
            ),
        )

    assert error.value.error_code == "operation.state_conflict"
    assert error.value.details["state"] == state
