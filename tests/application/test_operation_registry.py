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
    OperationExposure,
    OperationGetInput,
    PublicOperationOutput,
    build_public_output_model,
)
from weconduct.application.pending_input.service import PendingInputValidationError


_TEST_CALLER = OperationCaller(
    caller_id="test:operation-registry",
    permissions=frozenset({"operation.invoke"}),
)


class _FakeService:
    def __init__(self) -> None:
        self.last_configuration_confirm_high_risk: bool | None = None

    def publish_resource_registry_changed(self, *, reason: str) -> None:
        pass

    def get_runtime_health(self) -> dict:
        return {"api_version": "0.9", "capabilities": {"network": {"available": True}}}

    def get_project_document(self) -> dict:
        return {"project": {"project_id": "p-1"}}

    def get_project_resource_audit_document(self) -> dict:
        return {"status": "ready", "summary": {"resource_count": 1}, "resources": [], "issues": []}

    def create_project(self, *, project_name: str, project_directory=None) -> dict:
        return {"status": "created", "project_name": project_name, "project_directory": project_directory}

    def get_graph_document(self, *, document_id=None) -> dict:
        return {"graph_model": {"document_id": document_id or "graph:workspace"}}

    def get_graph_context(self, **payload: object) -> dict:
        return {"revision": 4, "focus_node": {"node_id": payload["node_id"]}, "neighbors": []}

    def preview_graph_patch(self, *, expected_revision: int, operations: list[dict]) -> dict:
        return {"status": "preview", "base_revision": expected_revision, "affected_node_ids": ["node-1"], "operations": operations}

    def apply_graph_patch(self, *, expected_revision: int, operations: list[dict]) -> dict:
        return {"status": "applied", "base_revision": expected_revision, "new_revision": expected_revision + 1, "affected_node_ids": ["node-1"], "operations": operations}

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

    def normalize_graph_document(self, graph_document_payload: dict) -> dict:
        return {"status": "normalized", "changed": False, "graph_model": graph_document_payload, "view": {}}

    def compile_graph_document(
        self,
        graph_document_payload: dict | None,
        *,
        expected_graph_document_save_revision: int | None = None,
        require_expected_revision: bool = False,
    ) -> dict:
        return {
            "status": "compiled",
            "graph_document": graph_document_payload,
            "expected_revision": expected_graph_document_save_revision,
            "require_expected_revision": require_expected_revision,
        }

    def build_graph_node_draft(self, *, resource_key: str, node_id=None, position=None) -> dict:
        return {"resource_key": resource_key, "node_id": node_id, "position": position}

    def get_resource_registry_document(self) -> dict:
        return {"registry_revision": 3, "resources": [{"resource_id": "resource-1"}]}

    def get_component_library_document(self) -> dict:
        return {"summary": {"available_resource_count": 1}, "items": [{"resource_key": "builtin.demo"}]}

    def save_user_component_resource(self, *, resource_name: str, replace_existing_resource_id=None) -> dict:
        return {"status": "saved", "registry_revision": 4, "resource": {"resource_id": "user-1", "display_name": resource_name}}

    def save_subgraph_resource(self, *, resource_name: str, replace_existing_resource_id=None) -> dict:
        return {"status": "saved", "registry_revision": 4, "resource": {"resource_id": "subgraph-1", "display_name": resource_name}}

    def save_custom_node_graph_resource(self, *, resource_name: str, replace_existing_resource_id=None) -> dict:
        return {"status": "saved", "registry_revision": 4, "resource": {"resource_id": "custom-1", "display_name": resource_name}}

    def create_empty_custom_node_graph_resource(self, *, resource_name: str) -> dict:
        return {"status": "created", "registry_revision": 4, "resource": {"resource_id": "custom-empty-1", "display_name": resource_name}}

    def set_resource_enabled(self, *, resource_id: str, enabled: bool) -> dict:
        return {"status": "updated", "registry_revision": 4, "resource": {"resource_id": resource_id, "enabled": enabled}}

    def update_resource_tags(self, *, resource_id: str, tags: list[str]) -> dict:
        return {"status": "updated", "registry_revision": 4, "resource": {"resource_id": resource_id, "tags": tags}}

    def update_resource_metadata(self, **payload: object) -> dict:
        return {"status": "updated", "registry_revision": 4, "resource": dict(payload)}

    def rename_resource(self, *, resource_id: str, display_name: str) -> dict:
        return {"status": "renamed", "registry_revision": 4, "resource": {"resource_id": resource_id, "display_name": display_name}}

    def delete_resource(self, *, resource_id: str) -> dict:
        return {"status": "deleted", "registry_revision": 4, "resource": {"resource_id": resource_id}}

    def prepare_debug_session(self, graph_document_payload: dict | None) -> dict:
        return {"status": "ready", "request": {"graph_document": graph_document_payload}}

    def start_debug_session_async(self, graph_document_payload: dict | None, *, settle_timeout_ms: int = 75) -> dict:
        return {"status": "started", "debug_session": {"session_id": "debug-1"}}

    def list_debug_sessions(self) -> dict:
        return {"sessions": [{"session_id": "debug-1", "status": "paused"}]}

    def get_debug_session(self, *, session_id: str) -> dict:
        return {"debug_session": {"session_id": session_id, "status": "paused"}}

    def get_configuration_schema(self, *, scope: str) -> dict:
        return {"scope": scope, "domains": []}

    def get_configuration_values(self, *, scope: str) -> dict:
        return {"scope": scope, "values": {"editor_preferences": {"snap": True}}}

    def preview_configuration(self, *, scope: str, operations: list[dict]) -> dict:
        return {"scope": scope, "values": {}, "changes": operations, "validation": []}

    def apply_configuration(
        self,
        *,
        scope: str,
        operations: list[dict],
        confirm_high_risk: bool = False,
    ) -> dict:
        self.last_configuration_confirm_high_risk = confirm_high_risk
        return {
            "scope": scope,
            "values": {},
            "changes": operations,
            "validation": [],
            "confirm_high_risk": confirm_high_risk,
        }

    def reset_configuration(self, *, scope: str) -> dict:
        return {"scope": scope, "values": {}, "changes": []}

    def list_runtime_sessions(self) -> dict:
        return {"sessions": [{"session_id": "runtime-1", "status": "running"}]}

    def get_execution_history_document(self) -> dict:
        return {"summary": {"runtime_run_count": 1}, "runtime_runs": [], "debug_sessions": []}

    def list_debug_history_sessions(self) -> dict:
        return {"summary": {"count": 1}, "sessions": [{"session_id": "debug-1"}]}

    def open_debug_history_session(self, *, session_id: str) -> dict:
        return {"debug_session": {"session_id": session_id}}

    def list_debug_session_events(self, *, session_id: str) -> dict:
        return {"session_id": session_id, "events": []}

    def get_debug_history_projection(self, *, session_id: str) -> dict:
        return {"session_id": session_id, "projection": {}}

    def get_debug_live_projection(self, *, session_id: str) -> dict:
        return {"session_id": session_id, "source": "active_session", "projection": {}}

    def get_graph_source_projection_document(self, *, target_source_kind: str, graph_document_payload=None) -> dict:
        return {"status": "ready", "source_kind": target_source_kind, "source_text": "{}", "diagnostics": []}

    def start_runtime_session(self, graph_document_payload: dict | None) -> dict:
        return {"status": "started", "runtime_session": {"session_id": "e-1"}}

    def prepare_runtime_session(self, graph_document_payload: dict | None) -> dict:
        return {"status": "ready", "request": {"graph_document": graph_document_payload}, "runtime_plan": {}}

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


def test_graph_context_and_patch_operations_delegate_through_stable_contracts() -> None:
    service = HostOperationService(service=_FakeService())

    context = service.invoke(
        "graph.context",
        {"node_id": "node-1", "depth": 1, "include_config": True},
        caller=_TEST_CALLER,
    )
    preview = service.invoke(
        "graph.patch.preview",
        {
            "expected_revision": 4,
            "operations": [{"op": "node.update", "node_id": "node-1", "changes": {"display_name": "优化后"}}],
        },
        caller=_TEST_CALLER,
    )
    applied = service.invoke(
        "graph.patch.apply",
        {
            "expected_revision": 4,
            "operations": [{"op": "node.update", "node_id": "node-1", "changes": {"display_name": "优化后"}}],
        },
        caller=_TEST_CALLER,
    )

    assert context["focus_node"]["node_id"] == "node-1"
    assert preview["status"] == "preview"
    assert preview["base_revision"] == 4
    assert applied["status"] == "applied"
    assert applied["new_revision"] == 5


def test_catalogue_operations_accept_and_forward_search_filters() -> None:
    class _FilteredService(_FakeService):
        resource_payload: dict[str, object] | None = None
        component_payload: dict[str, object] | None = None

        def get_resource_registry_document(self, **payload: object) -> dict:
            self.resource_payload = payload
            return {"registry_revision": 3, "resources": []}

        def get_component_library_document(self, **payload: object) -> dict:
            self.component_payload = payload
            return {"summary": {}, "items": []}

    host = _FilteredService()
    service = HostOperationService(service=host)
    service.invoke(
        "resource.list",
        {"query": "captcha", "tags": ["builtin"], "limit": 5},
        caller=_TEST_CALLER,
    )
    service.invoke(
        "component.list",
        {"query": "while", "limit": 3},
        caller=_TEST_CALLER,
    )

    assert host.resource_payload == {"query": "captcha", "tags": ["builtin"], "limit": 5}
    assert host.component_payload == {"query": "while", "limit": 3}


def test_operation_discovery_exposes_only_stable_public_descriptors_with_json_schemas() -> None:
    registry = OperationRegistry(
        {
            "operation.list": OperationDescriptor(
                operation_id="operation.list",
                output_model=build_public_output_model(
                    "OperationListOutput",
                    frozenset({"operations"}),
                ),
                output_fields=frozenset({"operations"}),
            ),
            "operation.get": OperationDescriptor(
                operation_id="operation.get",
                input_model=OperationGetInput,
                output_model=build_public_output_model(
                    "OperationGetOutput",
                    frozenset({"operation"}),
                ),
                output_fields=frozenset({"operation"}),
            ),
            "test.visible": OperationDescriptor(operation_id="test.visible"),
            "test.managed": OperationDescriptor(
                operation_id="test.managed",
                exposure=OperationExposure.MANAGED_PLUGIN,
            ),
        }
    )
    service = HostOperationService(service=_FakeService(), registry=registry)

    listed = service.invoke("operation.list", {}, caller=_TEST_CALLER)
    assert [item["operation_id"] for item in listed["operations"]] == [
        "operation.get",
        "operation.list",
        "test.visible",
    ]

    described = service.invoke(
        "operation.get",
        {"operation_id": "test.visible"},
        caller=_TEST_CALLER,
    )
    assert described["operation"]["operation_id"] == "test.visible"
    assert described["operation"]["input_schema"]["type"] == "object"
    assert described["operation"]["output_schema"]["type"] == "object"


def test_resource_and_component_catalogues_delegate_to_workbench_service() -> None:
    service = HostOperationService(service=_FakeService())

    resources = service.invoke("resource.list", {}, caller=_TEST_CALLER)
    components = service.invoke("component.list", {}, caller=_TEST_CALLER)

    assert resources == {
        "registry_revision": 3,
        "resources": [{"resource_id": "resource-1"}],
    }
    assert components == {
        "summary": {"available_resource_count": 1},
        "items": [{"resource_key": "builtin.demo"}],
    }


def test_graph_document_operations_support_custom_documents_with_optimistic_revision() -> None:
    service = HostOperationService(service=_FakeService())

    document = service.invoke(
        "graph.document.get",
        {"document_id": "resource:custom-node-graph"},
        caller=_TEST_CALLER,
    )
    assert document == {"graph_model": {"document_id": "resource:custom-node-graph"}}

    saved = service.invoke(
        "graph.document.replace",
        {
            "document_id": "resource:custom-node-graph",
            "graph_document": {"document_id": "resource:custom-node-graph", "nodes": []},
            "expected_revision": 5,
        },
        caller=_TEST_CALLER,
    )
    assert saved["expected_revision"] == 5
    assert saved["require_expected_revision"] is True

    with pytest.raises(OperationRegistryError) as mismatch:
        service.invoke(
            "graph.document.replace",
            {
                "document_id": "resource:custom-node-graph",
                "graph_document": {"document_id": "graph:workspace", "nodes": []},
                "expected_revision": 5,
            },
            caller=_TEST_CALLER,
        )
    assert mismatch.value.error_code == "operation.input_invalid"


def test_resource_mutation_operations_delegate_to_workbench_service() -> None:
    service = HostOperationService(service=_FakeService())

    saved = service.invoke(
        "resource.user_component.save",
        {"resource_name": "共享组件", "tags": ["team:ops"]},
        caller=_TEST_CALLER,
    )
    enabled = service.invoke(
        "resource.enabled.set",
        {"resource_id": "user-1", "enabled": False},
        caller=_TEST_CALLER,
    )
    renamed = service.invoke(
        "resource.rename",
        {"resource_id": "user-1", "display_name": "重命名组件"},
        caller=_TEST_CALLER,
    )
    deleted = service.invoke(
        "resource.delete",
        {"resource_id": "user-1"},
        caller=_TEST_CALLER,
    )

    assert saved["resource"]["tags"] == ["team:ops"]
    assert enabled["resource"]["enabled"] is False
    assert renamed["status"] == "renamed"
    assert deleted["status"] == "deleted"


def test_debug_discovery_and_start_operations_delegate_to_workbench_service() -> None:
    service = HostOperationService(service=_FakeService())

    prepared = service.invoke("debug.prepare", {"graph_document": None}, caller=_TEST_CALLER)
    started = service.invoke("debug.start", {"graph_document": None}, caller=_TEST_CALLER)
    listed = service.invoke("debug.list", {}, caller=_TEST_CALLER)
    loaded = service.invoke("debug.get", {"session_id": "debug-1"}, caller=_TEST_CALLER)

    assert prepared["status"] == "ready"
    assert started["debug_session"]["session_id"] == "debug-1"
    assert listed["sessions"][0]["status"] == "paused"
    assert loaded["debug_session"]["session_id"] == "debug-1"


def test_configuration_operations_keep_program_scope_read_only() -> None:
    fake_service = _FakeService()
    service = HostOperationService(service=fake_service)

    schema = service.invoke("configuration.schema.get", {"scope": "program"}, caller=_TEST_CALLER)
    preview = service.invoke(
        "configuration.preview",
        {"scope": "graph", "operations": []},
        caller=_TEST_CALLER,
    )
    applied = service.invoke(
        "configuration.apply",
        {"scope": "project", "operations": [], "confirm_high_risk": True},
        caller=_TEST_CALLER,
    )
    assert schema["scope"] == "program"
    assert preview["scope"] == "graph"
    assert applied["scope"] == "project"
    assert fake_service.last_configuration_confirm_high_risk is True

    with pytest.raises(OperationRegistryError) as denied:
        service.invoke(
            "configuration.apply",
            {"scope": "program", "operations": []},
            caller=_TEST_CALLER,
        )
    assert denied.value.error_code == "operation.not_available"


def test_configuration_preview_preserves_real_service_preview_contract() -> None:
    from weconduct.application import CompilationWorkbenchService

    result = HostOperationService(service=CompilationWorkbenchService()).invoke(
        "configuration.preview",
        {"scope": "graph", "operations": []},
        caller=_TEST_CALLER,
    )

    assert result["scope"] == "graph"
    assert "current_values" in result
    assert "proposed_values" in result
    assert result["confirmation_required"] is False
    assert result["high_risk_changes"] == []


def test_observability_operations_delegate_to_workbench_service() -> None:
    service = HostOperationService(service=_FakeService())

    runtime = service.invoke("runtime.list", {}, caller=_TEST_CALLER)
    history = service.invoke("execution.history.get", {}, caller=_TEST_CALLER)
    debug_history = service.invoke("debug.history.list", {}, caller=_TEST_CALLER)
    live_projection = service.invoke("debug.live_projection", {"session_id": "debug-1"}, caller=_TEST_CALLER)
    projection = service.invoke("graph.source_projection", {}, caller=_TEST_CALLER)

    assert runtime["sessions"][0]["session_id"] == "runtime-1"
    assert history["summary"]["runtime_run_count"] == 1
    assert debug_history["sessions"][0]["session_id"] == "debug-1"
    assert live_projection["source"] == "active_session"
    assert projection["source_kind"] == "native_flow"


def test_debug_history_projection_accepts_one_explicit_replay_selector() -> None:
    class _DebugHistoryProjectionService:
        def get_debug_history_projection(
            self,
            *,
            session_id: str,
            event_index: int | None = None,
            keyframe_id: str | None = None,
        ) -> dict:
            return {
                "source": "history_store",
                "session_id": session_id,
                "projection": {"event_index": event_index, "keyframe_id": keyframe_id},
                "runtime_preview": {},
                "variable_snapshot": {},
            }

    operation_service = HostOperationService(service=_DebugHistoryProjectionService())
    selected = operation_service.invoke(
        "debug.history.projection",
        {"session_id": "debug-history-1", "event_index": 3},
        caller=_TEST_CALLER,
    )

    assert selected["projection"] == {"event_index": 3, "keyframe_id": None}
    with pytest.raises(OperationRegistryError) as conflict:
        operation_service.invoke(
            "debug.history.projection",
            {
                "session_id": "debug-history-1",
                "event_index": 3,
                "keyframe_id": "keyframe-3",
            },
            caller=_TEST_CALLER,
        )
    assert conflict.value.error_code == "operation.input_invalid"


def test_execution_prepare_delegates_to_workbench_service_without_starting_a_session() -> None:
    service = HostOperationService(service=_FakeService())

    result = service.invoke("execution.prepare", {}, caller=_TEST_CALLER)

    assert result["status"] == "ready"
    assert result["request"] == {"graph_document": None}


def test_read_only_project_audit_and_graph_normalize_operations_delegate_to_workbench_service() -> None:
    service = HostOperationService(service=_FakeService())

    audit = service.invoke("project.resource_audit.get", {}, caller=_TEST_CALLER)
    normalized = service.invoke(
        "graph.normalize",
        {"graph_document": {"document_id": "graph:workspace"}},
        caller=_TEST_CALLER,
    )

    assert audit["summary"]["resource_count"] == 1
    assert normalized["status"] == "normalized"
    assert normalized["changed"] is False


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


def test_debug_session_not_found_is_reported_as_a_stable_not_found_error() -> None:
    class _MissingDebugSessionService:
        def get_debug_session(self, *, session_id: str) -> dict:
            raise ValueError(f"debug session not found: {session_id}")

    with pytest.raises(OperationRegistryError) as error:
        HostOperationService(service=_MissingDebugSessionService()).invoke(
            "debug.get",
            {"session_id": "missing-debug-session"},
            caller=_TEST_CALLER,
        )

    assert error.value.error_code == "operation.not_found"

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
