from __future__ import annotations

from weconduct.application import CompilationWorkbenchService
from weconduct.contracts import GraphModel


def _python_graph(*, ports: list[dict] | None = None, schemas: dict | None = None) -> dict:
    schema_values = schemas or {
        "input_schema": {
            "username": {"type": "string", "required": True},
            "retry_count": {"type": "integer"},
        },
        "output_schema": {
            "logged_in": {"type": "boolean"},
        },
        "metadata_schema": {
            "request_id": {"type": "string"},
        },
    }
    return {
        "graph_model_id": "graph:workspace",
        "compilation_id": None,
        "graph_schema_version": "graph-v1",
        "nodes": [
            {
                "node_id": "python-node",
                "lowered_kind": "execution",
                "source_anchor_ref": "n-python-node",
                "expansion_role": "action:python_run",
                "node_kind": "python.run",
                "ports": ports or [
                    {
                        "port_id": "legacy-username",
                        "direction": "input",
                        "relation_layer": "data",
                        "semantic_slot": "in.username",
                    },
                    {
                        "port_id": "in",
                        "direction": "input",
                        "relation_layer": "control",
                        "semantic_slot": "in.control",
                    },
                    {
                        "port_id": "out",
                        "direction": "output",
                        "relation_layer": "control",
                        "semantic_slot": "out.control",
                    },
                ],
                "node_config": {
                    "code": "ctx.outputs.set('logged_in', True)",
                    "inputs": {},
                    "outputs": {},
                    "metadata": {},
                    **schema_values,
                },
            }
        ],
        "edges": [],
        "root_metadata": {},
    }


def test_python_run_schema_generates_stable_data_and_metadata_ports() -> None:
    service = CompilationWorkbenchService()

    normalized = service.normalize_graph_document(_python_graph())

    assert normalized["changed"] is True
    node = normalized["graph_model"].nodes[0]
    ports = {(port.semantic_slot, port.direction): port for port in node.ports}

    assert ports[("in.control", "input")].port_id == "in"
    assert ports[("out.control", "output")].port_id == "out"
    assert ports[("in.username", "input")].port_id == "legacy-username"
    assert ports[("in.retry_count", "input")].port_id == "python-node::python::in-retry_count"
    assert ports[("out.logged_in", "output")].port_id == "python-node::python::out-logged_in"
    assert ports[("out.metadata.request_id", "output")].port_id == (
        "python-node::python::out-metadata-request_id"
    )
    assert all(port.relation_layer == "data" for slot, port in ports.items() if slot[0].startswith("in.") and slot[0] != "in.control")


def test_python_run_schema_normalization_is_idempotent_and_removes_deleted_fields() -> None:
    service = CompilationWorkbenchService()
    first = service.normalize_graph_document(_python_graph())
    second = service.normalize_graph_document(first["graph_model"].model_dump(mode="python"))

    assert second["changed"] is False
    assert second["graph_model"] == first["graph_model"]

    changed_schema = {
        "input_schema": {"username": {"type": "string"}},
        "output_schema": {},
        "metadata_schema": {},
    }
    reduced = service.normalize_graph_document(
        _python_graph(ports=first["graph_model"].nodes[0].model_dump(mode="python")["ports"], schemas=changed_schema)
    )
    reduced_slots = {port.semantic_slot for port in reduced["graph_model"].nodes[0].ports}
    assert "in.username" in reduced_slots
    assert "in.retry_count" not in reduced_slots
    assert "out.logged_in" not in reduced_slots
    assert "out.metadata.request_id" not in reduced_slots
