from __future__ import annotations

from weconduct.application.compilation_workbench_service import (
    CompilationWorkbenchService,
)
from weconduct.runtime.execution_context import ExecutionTokenContext


def test_control_schedulers_preserve_network_context_reference() -> None:
    service = CompilationWorkbenchService()
    token_context = ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=3,
    )
    executable_nodes = [
        {"node_id": "fork", "node_kind": "control.parallel_fork", "ports": []},
        {"node_id": "fork-target", "node_kind": "data.set_variable", "ports": []},
        {"node_id": "join", "node_kind": "control.join", "ports": []},
        {"node_id": "join-target", "node_kind": "data.set_variable", "ports": []},
    ]
    control_edges_by_source = {
        "fork": [
            {
                "edge_id": "fork-edge",
                "from_node_id": "fork",
                "from_port_id": "branch:one",
                "to_node_id": "fork-target",
                "to_port_id": "in",
                "relation_layer": "control",
            }
        ],
        "join": [
            {
                "edge_id": "join-edge",
                "from_node_id": "join",
                "from_port_id": "out",
                "to_node_id": "join-target",
                "to_port_id": "in",
                "relation_layer": "control",
            }
        ],
    }
    node_index_by_id = {
        node["node_id"]: index for index, node in enumerate(executable_nodes)
    }
    node_kind_by_id = {
        node["node_id"]: node["node_kind"] for node in executable_nodes
    }
    pending_node_entries: list[dict[str, object]] = []

    service._queue_runtime_parallel_fork_successors(
        executable_node=executable_nodes[0],
        control_edges_by_source=control_edges_by_source,
        node_index_by_id=node_index_by_id,
        node_kind_by_id=node_kind_by_id,
        control_edges_by_target={},
        join_state_by_node_id={},
        pending_node_entries=pending_node_entries,
        queued_node_ids=set(),
        executed_node_ids=set(),
        executable_nodes=executable_nodes,
        token_context=token_context,
    )
    service._queue_runtime_join_successors(
        executable_node=executable_nodes[2],
        control_edges_by_source=control_edges_by_source,
        node_index_by_id=node_index_by_id,
        node_kind_by_id=node_kind_by_id,
        control_edges_by_target={},
        join_state_by_node_id={},
        pending_node_entries=pending_node_entries,
        queued_node_ids=set(),
        executed_node_ids=set(),
        executable_nodes=executable_nodes,
        token_context=token_context,
    )

    assert [entry["token_context"] for entry in pending_node_entries] == [
        token_context.to_snapshot(),
        token_context.to_snapshot(),
    ]


def test_debug_scheduler_snapshot_preserves_current_network_context_reference() -> None:
    service = CompilationWorkbenchService()
    token_context = ExecutionTokenContext(
        network_context_id="network-context-debug",
        network_context_epoch=5,
    )

    snapshot = service._build_runtime_debug_snapshot(
        scheduler_mode="flow_graph",
        pending_node_entries=[],
        queued_node_ids=set(),
        executed_node_ids_in_order=[],
        join_state_by_node_id={},
        retry_state_by_node_id={},
        executable_nodes=[{"node_id": "node-a", "node_kind": "network.http_request"}],
        current_program_counter=0,
        current_repeat_mode=False,
        current_token_context=token_context,
    )

    assert snapshot["current_node"]["token_context"] == token_context.to_snapshot()
