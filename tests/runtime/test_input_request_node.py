from __future__ import annotations

from threading import Thread
from time import monotonic, sleep

from weconduct.application import CompilationWorkbenchService
from weconduct.application.sensitive_values.models import SensitiveRef
from weconduct.builtin_components import build_builtin_resource_registry
from weconduct.runtime import RuntimeContext, RuntimeExecutorRegistry
from weconduct.runtime.engine import CancellationContext
from weconduct.runtime.execution_context import ExecutionSessionContext


def test_input_request_node_publishes_atomic_runtime_outputs_with_sensitive_refs() -> None:
    service = CompilationWorkbenchService()
    session_id = "runtime-session-input-1"
    runtime_context = RuntimeContext(
        execution_session_context=ExecutionSessionContext(session_id=session_id),
    )
    output_holder: list[dict] = []
    node = {
        "node_id": "input-node-1",
        "node_kind": "input.request",
        "node_config": {
            "fields": [
                {"field_id": "username", "label": "Username"},
                {"field_id": "password", "label": "Password", "sensitive": True},
            ],
            "timeout_seconds": 0,
        },
    }
    worker = Thread(
        target=lambda: output_holder.append(
            service._execute_runtime_plan_node(
                executable_node=node,
                runtime_context=runtime_context,
                executor_registry=RuntimeExecutorRegistry(),
            )
        ),
        daemon=True,
    )
    worker.start()
    deadline = monotonic() + 1
    while service.get_pending_input_snapshot(execution_id=session_id) is None and monotonic() < deadline:
        sleep(0.01)

    pending = service.get_pending_input_snapshot(execution_id=session_id)
    assert pending is not None
    assert pending.status == "waiting"
    assert [field.field_id for field in pending.fields] == ["username", "password"]
    submitted = service.submit_pending_input(
        execution_id=session_id,
        request_id=pending.request_id,
        values={"username": "alice", "password": "test-secret"},
    )
    worker.join(timeout=1)

    assert submitted.status == "submitted"
    assert worker.is_alive() is False
    assert output_holder[0]["username"] == "alice"
    assert isinstance(output_holder[0]["password"], SensitiveRef)
    assert runtime_context.node_outputs["input-node-1"]["password"] == output_holder[0]["password"]
    assert "test-secret" not in repr(output_holder[0])


def test_input_request_is_registered_as_a_builtin_component() -> None:
    registry = build_builtin_resource_registry()

    input_request = next(item for item in registry if item["resource_key"] == "input.request")

    assert input_request["resource_id"] == "builtin:input.request"
    assert input_request["implementation_kind"] == "core_atomic"
