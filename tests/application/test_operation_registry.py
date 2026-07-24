from __future__ import annotations

import pytest

from weconduct.application.operation_registry import (
    OperationRegistry,
    OperationRegistryError,
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

    def save_graph_document(self, graph_document_payload: dict, *, expected_graph_document_save_revision=None) -> dict:
        return {
            "status": "saved",
            "graph_document": graph_document_payload,
            "expected_revision": expected_graph_document_save_revision,
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


class _PendingInputErrorService(_FakeService):
    def submit_pending_input(self, *, execution_id: str, request_id: str, values: dict) -> dict:
        raise ValueError("pending input request is not waiting")


def test_operation_registry_exposes_stable_descriptors_and_dispatches_contracts() -> None:
    registry = OperationRegistry(service=_FakeService())

    descriptor = registry.describe("graph.replace")
    assert descriptor.operation_id == "graph.replace"
    assert descriptor.exposure == "stable_public"
    assert descriptor.execution_mode == "sync"

    result = registry.execute(
        "graph.replace",
        {"graph_document": {"document_id": "graph:workspace"}, "expected_revision": 4},
    )
    assert result["status"] == "saved"
    assert result["expected_revision"] == 4

    started = registry.execute("execution.start", {"graph_document": None})
    assert started["runtime_session"]["session_id"] == "e-1"


def test_operation_registry_rejects_unknown_operation_and_missing_fields() -> None:
    registry = OperationRegistry(service=_FakeService())

    with pytest.raises(OperationRegistryError) as not_found:
        registry.execute("internal.missing", {})
    assert not_found.value.error_code == "operation.not_found"
    with pytest.raises(OperationRegistryError) as invalid_input:
        registry.execute("project.create", {})
    assert invalid_input.value.error_code == "operation.input_invalid"


def test_operation_registry_redacts_descriptor_output_to_contract_fields() -> None:
    registry = OperationRegistry(service=_FakeService())

    capabilities = registry.execute("host.capabilities", {})

    assert capabilities == {"capabilities": {"network": {"available": True}}}


def test_operation_registry_normalizes_pending_input_state_conflicts() -> None:
    registry = OperationRegistry(service=_PendingInputErrorService())

    with pytest.raises(OperationRegistryError) as error:
        registry.execute(
            "pending_input.submit",
            {"execution_id": "e-1", "request_id": "r-1", "values": {}},
        )

    assert error.value.error_code == "operation.state_conflict"
