from __future__ import annotations

import pytest
from pydantic import Field

from weconduct.application.operations import (
    HostOperationService,
    OperationCaller,
    OperationRegistry,
    OperationRegistryError,
)
from weconduct.application.operations.models import (
    EmptyOperationInput,
    IdempotencyCapability,
    OperationDescriptor,
    PublicOperationOutput,
)
from weconduct.application.pending_input.service import PendingInputValidationError


_TEST_CALLER = OperationCaller(
    caller_id="test:operation-registry",
    permissions=frozenset({"operation.invoke"}),
)


class _FakeService:
    def get_runtime_health(self) -> dict:
        return {"api_version": "0.9", "capabilities": {"network": {"available": True}}}

    def get_project_document(self) -> dict:
        return {"project": {"project_id": "p-1"}}

    def create_project(self, *, project_name: str, project_directory=None) -> dict:
        return {"status": "created", "project_name": project_name, "project_directory": project_directory}

    def get_graph_document(self, *, document_id=None) -> dict:
        return {"graph_model": {"document_id": document_id or "graph:workspace"}}

    def save_graph_document(
        self,
        graph_document_payload: dict,
        *,
        expected_graph_document_save_revision=None,
        require_expected_revision: bool = False,
    ) -> dict:
        return {
            "status": "saved",
            "graph_document": graph_document_payload,
            "expected_revision": expected_graph_document_save_revision,
            "require_expected_revision": require_expected_revision,
        }

    def validate_graph_document(self, graph_document_payload: dict) -> dict:
        return {"status": "valid", "graph_model": graph_document_payload}

    def compile_graph_document(self, graph_document_payload: dict | None) -> dict:
        return {"status": "compiled", "graph_document": graph_document_payload}

    def build_graph_node_draft(self, *, resource_key: str, node_id=None, position=None) -> dict:
        return {"resource_key": resource_key, "node_id": node_id, "position": position}

    def start_runtime_session(self, graph_document_payload: dict | None) -> dict:
        return {"status": "started", "runtime_session": {"session_id": "e-1"}}

    def get_runtime_session(self, *, session_id: str) -> dict:
        return {"runtime_session": {"session_id": session_id, "status": "running"}}

    def abort_runtime_session(self, *, session_id: str, reason: str) -> dict:
        return {"status": "aborting", "session_id": session_id, "reason": reason}

    def get_pending_input_snapshot(self, *, execution_id: str):
        return {"execution_id": execution_id, "status": "waiting"}

    def submit_pending_input(self, *, execution_id: str, request_id: str, values: dict) -> dict:
        return {"execution_id": execution_id, "request_id": request_id, "values": values}

    def unlock_runtime_session_parameters(self, *, session_id: str, password: str) -> dict:
        return {"status": "unlocked", "parameter_ids": ["api_key"]}

    def start_runtime_session_execution(self, *, session_id: str) -> dict:
        return {"status": "accepted", "runtime_session": {"session_id": session_id}}


class _PendingInputErrorService(_FakeService):
    def submit_pending_input(self, *, execution_id: str, request_id: str, values: dict) -> dict:
        raise ValueError("pending input request is not waiting")


class _PendingInputValidationErrorService(_FakeService):
    def submit_pending_input(self, *, execution_id: str, request_id: str, values: dict) -> dict:
        raise PendingInputValidationError(
            "field attempt_count must be an integer",
            details={
                "validation_kind": "type_mismatch",
                "field_id": "attempt_count",
                "expected_type": "integer",
                "actual_type": "string",
            },
        )


class _StrictOutput(PublicOperationOutput):
    value: int = Field(strict=True)


class _OutputInvalidHostOperationService(HostOperationService):
    def __init__(self) -> None:
        registry = OperationRegistry(
            {
                "test.output_invalid": OperationDescriptor(
                    operation_id="test.output_invalid",
                    input_model=EmptyOperationInput,
                    output_model=_StrictOutput,
                    output_fields=frozenset({"value"}),
                    idempotency_capability=IdempotencyCapability.SUPPORTED,
                )
            }
        )
        super().__init__(service=_FakeService(), registry=registry)
        self.dispatch_count = 0

    def _dispatch(self, operation_id: str, payload: dict[str, object]) -> object:
        self.dispatch_count += 1
        return {"value": "not-an-integer"}


def test_operation_service_executes_through_explicit_registry() -> None:
    from weconduct.application.operations import HostOperationService, OperationRegistry

    registry = OperationRegistry.build_stable_public()
    service = HostOperationService(service=_FakeService(), registry=registry)

    result = service.invoke(
        "graph.replace",
        {"graph_document": {"document_id": "graph:workspace"}, "expected_revision": 4},
        caller=_TEST_CALLER,
    )

    assert result["status"] == "saved"
    assert result["expected_revision"] == 4


def test_operation_service_exposes_stable_descriptors_and_dispatches_contracts() -> None:
    service = HostOperationService(service=_FakeService())

    descriptor = service.describe("graph.replace")
    assert descriptor.operation_id == "graph.replace"
    assert descriptor.exposure.value == "stable_public"
    assert descriptor.execution_mode == "sync"

    result = service.invoke(
        "graph.replace",
        {"graph_document": {"document_id": "graph:workspace"}, "expected_revision": 4},
        caller=_TEST_CALLER,
    )
    assert result["status"] == "saved"
    assert result["expected_revision"] == 4

    started = service.invoke(
        "execution.start",
        {"graph_document": None},
        caller=_TEST_CALLER,
    )
    assert started["runtime_session"]["session_id"] == "e-1"


def test_operation_service_rejects_unknown_operation_and_missing_fields() -> None:
    service = HostOperationService(service=_FakeService())

    with pytest.raises(OperationRegistryError) as not_found:
        service.invoke("internal.missing", {}, caller=_TEST_CALLER)
    assert not_found.value.error_code == "operation.not_found"
    with pytest.raises(OperationRegistryError) as invalid_input:
        service.invoke("project.create", {}, caller=_TEST_CALLER)
    assert invalid_input.value.error_code == "operation.input_invalid"

    with pytest.raises(OperationRegistryError) as missing_graph_revision:
        service.invoke(
            "graph.replace",
            {"graph_document": {"document_id": "graph:workspace"}},
            caller=_TEST_CALLER,
        )
    assert missing_graph_revision.value.error_code == "operation.input_invalid"

    with pytest.raises(OperationRegistryError) as invalid_graph_revision:
        service.invoke(
            "graph.replace",
            {
                "graph_document": {"document_id": "graph:workspace"},
                "expected_revision": "latest",
            },
            caller=_TEST_CALLER,
        )
    assert invalid_graph_revision.value.error_code == "operation.input_invalid"

    with pytest.raises(OperationRegistryError) as invalid_graph_document:
        service.invoke(
            "graph.replace",
            {"graph_document": "not-a-document", "expected_revision": 0},
            caller=_TEST_CALLER,
        )
    assert invalid_graph_document.value.error_code == "operation.input_invalid"

    with pytest.raises(OperationRegistryError) as unsupported_graph_document:
        service.invoke(
            "graph.replace",
            {
                "graph_document": {"document_id": "resource:custom-node-graph"},
                "expected_revision": 0,
            },
            caller=_TEST_CALLER,
        )
    assert unsupported_graph_document.value.error_code == "operation.input_invalid"


def test_operation_validation_errors_do_not_echo_input_payloads() -> None:
    service = HostOperationService(service=_FakeService())
    secret = "graph-input-secret-should-not-echo"

    with pytest.raises(OperationRegistryError) as error:
        service.invoke(
            "graph.replace",
            {
                "graph_document": {
                    "nodes": [{"node_config": {"authorization": secret}}],
                },
            },
            caller=_TEST_CALLER,
        )

    assert error.value.error_code == "operation.input_invalid"
    assert secret not in repr(error.value.details)
    assert all("input" not in item for item in error.value.details["validation_errors"])


def test_output_validation_failure_releases_idempotency_reservation() -> None:
    service = _OutputInvalidHostOperationService()

    for _ in range(2):
        with pytest.raises(OperationRegistryError) as error:
            service.invoke(
                "test.output_invalid",
                {},
                caller=_TEST_CALLER,
                idempotency_key="retry-after-output-validation-failure",
            )
        assert error.value.error_code == "operation.output_invalid"

    assert service.dispatch_count == 2


def test_operation_service_redacts_descriptor_output_to_contract_fields() -> None:
    service = HostOperationService(service=_FakeService())

    capabilities = service.invoke("host.capabilities", {}, caller=_TEST_CALLER)

    assert capabilities == {"capabilities": {"network": {"available": True}}}


def test_host_capabilities_expose_runtime_network_and_security_features() -> None:
    from weconduct.application import CompilationWorkbenchService

    result = HostOperationService(service=CompilationWorkbenchService()).invoke(
        "host.capabilities",
        {},
        caller=_TEST_CALLER,
    )

    capabilities = result["capabilities"]
    assert capabilities["network"]["available"] is True
    assert capabilities["network"]["protocols"]["http2"] is True
    assert capabilities["sensitive_input"]["available"] is True
    assert capabilities["external_api_v1"]["available"] is True
    assert capabilities["python_run"]["dynamic_schema"] is True


def test_operation_service_normalizes_pending_input_state_conflicts() -> None:
    service = HostOperationService(service=_PendingInputErrorService())

    with pytest.raises(OperationRegistryError) as error:
        service.invoke(
            "pending_input.submit",
            {"execution_id": "e-1", "request_id": "r-1", "values": {}},
            caller=_TEST_CALLER,
        )

    assert error.value.error_code == "operation.state_conflict"


def test_operation_service_normalizes_pending_input_validation_details() -> None:
    service = HostOperationService(service=_PendingInputValidationErrorService())

    with pytest.raises(OperationRegistryError) as error:
        service.invoke(
            "pending_input.submit",
            {"execution_id": "e-1", "request_id": "r-1", "values": {"attempt_count": "bad"}},
            caller=_TEST_CALLER,
        )

    assert error.value.error_code == "operation.input_invalid"
    assert error.value.details == {
        "validation_kind": "type_mismatch",
        "field_id": "attempt_count",
        "expected_type": "integer",
        "actual_type": "string",
    }


def test_execution_parameter_unlock_uses_stable_operation_and_redacts_password_audit() -> None:
    service = HostOperationService(service=_FakeService())

    result = service.invoke(
        "execution.parameters.unlock",
        {"execution_id": "e-1", "password": "unlock-secret"},
        caller=_TEST_CALLER,
    )

    assert result == {"status": "accepted", "parameter_ids": ["api_key"]}
    assert service.audit_trail.records[-1].input_summary == {
        "execution_id": "e-1",
        "password": "<redacted>",
    }
