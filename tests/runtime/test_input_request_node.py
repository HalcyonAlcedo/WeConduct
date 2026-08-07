from __future__ import annotations

from queue import Empty
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


def test_input_request_node_uses_a_distinct_request_id_for_each_execution_instance() -> None:
    service = CompilationWorkbenchService()
    session_id = "runtime-session-input-retry"
    runtime_context = RuntimeContext(
        execution_session_context=ExecutionSessionContext(session_id=session_id),
    )
    node = {
        "node_id": "input-node-retry",
        "node_kind": "input.request",
        "node_config": {
            "fields": [{"field_id": "answer", "label": "Answer"}],
            "timeout_seconds": 0,
        },
    }

    request_ids: list[str] = []
    for answer in ("first", "second"):
        output_holder: list[dict] = []
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
        request_ids.append(pending.request_id)
        service.submit_pending_input(
            execution_id=session_id,
            request_id=pending.request_id,
            values={"answer": answer},
        )
        worker.join(timeout=1)

        assert worker.is_alive() is False
        assert output_holder[0]["status"] == "succeeded"
        assert output_holder[0]["answer"] == answer

    assert request_ids == [
        "runtime-session-input-retry:input-node-retry:1",
        "runtime-session-input-retry:input-node-retry:2",
    ]


def test_input_request_is_registered_as_a_builtin_component() -> None:
    registry = build_builtin_resource_registry()

    input_request = next(item for item in registry if item["resource_key"] == "input.request")

    assert input_request["resource_id"] == "builtin:input.request"
    assert input_request["implementation_kind"] == "core_atomic"


def test_input_request_draft_defines_field_schema_and_dynamic_output_ports() -> None:
    service = CompilationWorkbenchService()

    draft = service.build_graph_node_draft(resource_key="input.request", node_id="input-node")
    node = draft["node"]
    node["node_config"]["fields"] = [
        {"field_id": "username", "label": "Username", "type": "string"},
        {"field_id": "password", "label": "Password", "type": "string", "sensitive": True},
    ]
    normalized = service.normalize_graph_document(
        {
            "graph_model_id": "graph:workspace",
            "compilation_id": None,
            "graph_schema_version": "graph-v1",
            "nodes": [node],
            "edges": [],
            "graph_effective_diagnostic_anchor_refs": [],
        }
    )

    assert draft["parameter_schema"]["fields"]["editor_kind"] == "input_request_fields"
    assert {port.port_id for port in normalized["graph_model"].nodes[0].ports} == {"in", "out", "timed_out", "out:username", "out:password"}


def _build_input_timeout_graph(
    *,
    default_value: object = None,
    include_default: bool = False,
    include_timeout_edge: bool = True,
) -> dict:
    input_fields = [{"field_id": "region", "label": "Region"}]
    if include_default:
        input_fields[0]["default_value"] = default_value

    nodes = [
        {
            "node_id": "start",
            "lowered_kind": "control",
            "source_anchor_ref": "start",
            "expansion_role": "flow.start",
            "display_name": "Start",
            "node_kind": "flow.start",
            "position": {"x": 0, "y": 0},
            "ports": [
                {
                    "port_id": "next",
                    "direction": "output",
                    "relation_layer": "control",
                    "semantic_slot": "control.next",
                }
            ],
            "node_config": {"initial_variables": {}},
        },
        {
            "node_id": "input",
            "lowered_kind": "execution",
            "source_anchor_ref": "input",
            "expansion_role": "input.request",
            "display_name": "Request input",
            "node_kind": "input.request",
            "position": {"x": 160, "y": 0},
            "ports": [
                {
                    "port_id": "in",
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "control.previous",
                },
                {
                    "port_id": "next",
                    "direction": "output",
                    "relation_layer": "control",
                    "semantic_slot": "control.next",
                },
                {
                    "port_id": "timeout",
                    "direction": "output",
                    "relation_layer": "control",
                    "semantic_slot": "control.timeout",
                },
            ],
            "node_config": {"fields": input_fields, "timeout_seconds": 0.01},
        },
        {
            "node_id": "default-target",
            "lowered_kind": "execution",
            "source_anchor_ref": "default-target",
            "expansion_role": "data.set_variable",
            "display_name": "Default path",
            "node_kind": "data.set_variable",
            "position": {"x": 320, "y": -80},
            "ports": [
                {
                    "port_id": "in",
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "control.previous",
                }
            ],
            "node_config": {"name": "path", "value": "default"},
        },
        {
            "node_id": "timeout-target",
            "lowered_kind": "execution",
            "source_anchor_ref": "timeout-target",
            "expansion_role": "data.set_variable",
            "display_name": "Timeout path",
            "node_kind": "data.set_variable",
            "position": {"x": 320, "y": 80},
            "ports": [
                {
                    "port_id": "in",
                    "direction": "input",
                    "relation_layer": "control",
                    "semantic_slot": "control.previous",
                }
            ],
            "node_config": {"name": "path", "value": "timeout"},
        },
    ]
    edges = [
        {
            "edge_id": "start-input",
            "from_node_id": "start",
            "from_port_id": "next",
            "to_node_id": "input",
            "to_port_id": "in",
            "relation_layer": "control",
        },
        {
            "edge_id": "input-default",
            "from_node_id": "input",
            "from_port_id": "next",
            "to_node_id": "default-target",
            "to_port_id": "in",
            "relation_layer": "control",
        },
    ]
    if include_timeout_edge:
        edges.append(
            {
                "edge_id": "input-timeout",
                "from_node_id": "input",
                "from_port_id": "timeout",
                "to_node_id": "timeout-target",
                "to_port_id": "in",
                "relation_layer": "control",
            }
        )
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": nodes,
        "edges": edges,
        "graph_effective_diagnostic_anchor_refs": [],
    }


def test_input_request_timeout_routes_only_to_connected_timeout_port() -> None:
    service = CompilationWorkbenchService()
    started = service.start_runtime_session(
        graph_document_payload=_build_input_timeout_graph(),
    )

    result = service.run_runtime_session(session_id=started["runtime_session"]["session_id"])

    node_states = {item["node_id"]: item for item in result["node_states"]}
    assert result["status"] == "completed"
    assert node_states["input"]["output"]["status"] == "timed_out"
    assert node_states["timeout-target"]["node_status"] == "completed"
    assert "default-target" in result["result"]["skipped_node_ids"]


def test_input_request_timeout_routes_using_canonical_out_timed_out_port() -> None:
    service = CompilationWorkbenchService()
    graph = _build_input_timeout_graph()
    input_node = next(node for node in graph["nodes"] if node["node_id"] == "input")
    timeout_port = next(port for port in input_node["ports"] if port["port_id"] == "timeout")
    timeout_port["port_id"] = "timed_out"
    timeout_port["semantic_slot"] = "out.timed_out"
    timeout_edge = next(edge for edge in graph["edges"] if edge["edge_id"] == "input-timeout")
    timeout_edge["from_port_id"] = "timed_out"

    started = service.start_runtime_session(graph_document_payload=graph)
    result = service.run_runtime_session(session_id=started["runtime_session"]["session_id"])

    node_states = {item["node_id"]: item for item in result["node_states"]}
    assert result["status"] == "completed"
    assert node_states["input"]["output"]["status"] == "timed_out"
    assert node_states["timeout-target"]["node_status"] == "completed"


def test_input_request_timeout_uses_complete_defaults_without_timeout_branch() -> None:
    service = CompilationWorkbenchService()
    started = service.start_runtime_session(
        graph_document_payload=_build_input_timeout_graph(
            default_value="fallback-region",
            include_default=True,
        ),
    )

    result = service.run_runtime_session(session_id=started["runtime_session"]["session_id"])

    node_states = {item["node_id"]: item for item in result["node_states"]}
    assert result["status"] == "completed"
    assert node_states["input"]["output"]["region"] == "fallback-region"
    assert node_states["default-target"]["node_status"] == "completed"
    assert "timeout-target" in result["result"]["skipped_node_ids"]


def test_input_request_timeout_without_default_or_timeout_edge_fails() -> None:
    service = CompilationWorkbenchService()
    started = service.start_runtime_session(
        graph_document_payload=_build_input_timeout_graph(include_timeout_edge=False),
    )

    result = service.run_runtime_session(session_id=started["runtime_session"]["session_id"])

    node_states = {item["node_id"]: item for item in result["node_states"]}
    assert result["status"] == "failed"
    assert node_states["input"]["error"]["error_code"] == "runtime.input_timeout"


def test_abort_runtime_session_cancels_waiting_input_request_without_leaking_worker() -> None:
    service = CompilationWorkbenchService()
    graph = _build_input_timeout_graph(include_timeout_edge=False)
    input_node = next(node for node in graph["nodes"] if node["node_id"] == "input")
    input_node["node_config"]["timeout_seconds"] = 0
    started = service.start_runtime_session(graph_document_payload=graph)
    session_id = started["runtime_session"]["session_id"]

    service.start_runtime_session_execution(session_id=session_id)
    deadline = monotonic() + 1
    while (
        service.get_pending_input_snapshot(execution_id=session_id) is None
        and monotonic() < deadline
    ):
        sleep(0.01)
    pending = service.get_pending_input_snapshot(execution_id=session_id)
    assert pending is not None
    assert pending.status == "waiting"
    assert service.get_runtime_session(session_id=session_id)["runtime_session"]["status"] == "waiting"

    aborted = service.abort_runtime_session(session_id=session_id, reason="test_abort")

    assert aborted["status"] == "aborted"
    assert aborted["runtime_session"]["status"] == "aborted"
    assert service._runtime_execution_threads.get(session_id) is None  # type: ignore[attr-defined]


def test_input_request_waiting_state_is_published_to_workbench_events() -> None:
    service = CompilationWorkbenchService()
    session_id = "runtime-session-workbench-waiting"
    runtime_context = RuntimeContext(
        execution_session_context=ExecutionSessionContext(session_id=session_id),
    )
    node = {
        "node_id": "input-node-workbench-waiting",
        "node_kind": "input.request",
        "node_config": {
            "fields": [{"field_id": "answer", "label": "Answer"}],
            "timeout_seconds": 0,
        },
    }
    broker = service.get_workbench_event_broker()
    subscriber_id, queue = broker.subscribe()
    worker = Thread(
        target=service._execute_runtime_plan_node,
        kwargs={
            "executable_node": node,
            "runtime_context": runtime_context,
            "executor_registry": RuntimeExecutorRegistry(),
        },
        daemon=True,
    )
    try:
        worker.start()
        deadline = monotonic() + 1
        while service.get_pending_input_snapshot(execution_id=session_id) is None and monotonic() < deadline:
            sleep(0.01)

        pending = service.get_pending_input_snapshot(execution_id=session_id)
        assert pending is not None
        events: list[dict] = []
        while True:
            try:
                events.append(queue.get(timeout=0.05))
            except Empty:
                break

        assert any(
            event["event_name"] == "runtime.session_changed"
            and event["payload"]["session_id"] == session_id
            and event["payload"]["status"] == "waiting"
            for event in events
        )
    finally:
        runtime_context.cancellation_context.request_cancel("test_cleanup")
        worker.join(timeout=1)
        broker.unsubscribe(subscriber_id)
