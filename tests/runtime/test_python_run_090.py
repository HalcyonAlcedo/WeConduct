from __future__ import annotations

import sys

from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def _registry(tmp_path):
    return RuntimeExecutorRegistry(
        runtime_settings={
            "allow_python_execution": True,
            "python_project_runtime_enabled": True,
            "python_executable_path": sys.executable,
            "python_project_runtime_root": str(tmp_path),
            "python_timeout_seconds": 10,
        }
    )


def test_python_run_supports_dynamic_inputs_outputs_and_metadata(tmp_path) -> None:
    registry = _registry(tmp_path)
    output = registry.execute(
        "python.run",
        {
            "node_id": "python-envelope-1",
            "node_kind": "python.run",
            "node_config": {
                "code": (
                    "ctx.outputs.set('greeting', 'hello ' + ctx.inputs.get('name'))\n"
                    "ctx.metadata.set('trace', 'trace-1')"
                ),
                "inputs": {"name": "alice"},
                "input_schema": {"name": {"type": "string", "required": True}},
                "output_schema": {"greeting": {"type": "string", "required": True}},
                "metadata_schema": {"trace": {"type": "string"}},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "succeeded"
    assert output["outputs"] == {"greeting": "hello alice"}
    assert output["metadata"]["trace"] == "trace-1"


def test_python_run_rejects_undeclared_output_without_partial_commit(tmp_path) -> None:
    registry = _registry(tmp_path)
    output = registry.execute(
        "python.run",
        {
            "node_id": "python-envelope-2",
            "node_kind": "python.run",
            "node_config": {
                "code": "ctx.outputs.set('unknown', 1)",
                "output_schema": {"declared": {"type": "integer"}},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert output["error_code"] == "python.execution_failed"
    assert "outputs" not in output


def test_python_run_discards_staged_output_when_code_fails(tmp_path) -> None:
    registry = _registry(tmp_path)
    output = registry.execute(
        "python.run",
        {
            "node_id": "python-envelope-3",
            "node_kind": "python.run",
            "node_config": {
                "code": "ctx.outputs.set('value', 7)\nraise ValueError('boom')",
                "output_schema": {"value": {"type": "integer"}},
            },
        },
        RuntimeContext(),
    )

    assert output["status"] == "failed"
    assert "outputs" not in output


def test_python_run_rejects_missing_required_input_and_data_escape(tmp_path) -> None:
    registry = _registry(tmp_path)
    missing = registry.execute(
        "python.run",
        {
            "node_id": "python-envelope-4",
            "node_kind": "python.run",
            "node_config": {
                "code": "ctx.outputs.set('value', 1)",
                "input_schema": {"name": {"type": "string", "required": True}},
                "output_schema": {"value": {"type": "integer"}},
            },
        },
        RuntimeContext(),
    )
    escaped = registry.execute(
        "python.run",
        {
            "node_id": "python-envelope-5",
            "node_kind": "python.run",
            "node_config": {
                "code": "ctx.data.get('secret')",
                "data_fields": ["allowed"],
            },
        },
        RuntimeContext(),
    )

    assert missing["error_code"] == "python.input_required"
    assert escaped["status"] == "failed"
