from __future__ import annotations

import sys

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
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


def test_python_run_denies_sensitive_reference_without_explicit_consumer_permission(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-denied",
            "node_kind": "python.run",
            "node_config": {
                "code": "ctx.outputs.set('value', ctx.inputs.get('api_key'))",
                "input_schema": {"api_key": {"type": "string", "required": True}},
                "output_schema": {"value": {"type": "string"}},
            },
        },
        context,
    )

    assert output["error_code"] == "python.sensitive_access_denied"
    assert "python-secret" not in repr(output)


def test_python_run_resolves_sensitive_reference_for_explicit_runtime_executor(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-allowed",
            "node_kind": "python.run",
            "node_config": {
                "allow_sensitive_values": True,
                "code": "ctx.outputs.set('value', ctx.inputs.get('api_key'))",
                "input_schema": {"api_key": {"type": "string", "required": True}},
                "output_schema": {"value": {"type": "string", "required": True}},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert isinstance(output["outputs"]["value"], SensitiveRef)
    assert sensitive.resolve(output["outputs"]["value"], consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "python-secret"


def test_python_run_marks_output_derived_from_sensitive_input_as_sensitive(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-derived",
            "node_kind": "python.run",
            "node_config": {
                "allow_sensitive_values": True,
                "code": (
                    "secret = ctx.inputs.get('api_key')\n"
                    "ctx.outputs.set('value', secret)"
                ),
                "input_schema": {"api_key": {"type": "string", "required": True}},
                "output_schema": {"value": {"type": "string", "required": True}},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert isinstance(output["outputs"]["value"], SensitiveRef)
    assert sensitive.resolve(output["outputs"]["value"], consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "python-secret"


def test_python_run_marks_output_derived_from_sensitive_data_as_sensitive(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-data-derived",
            "node_kind": "python.run",
            "node_config": {
                "allow_sensitive_values": True,
                "data_fields": ["api_key"],
                "code": "ctx.outputs.set('value', ctx.data.get('api_key'))",
                "output_schema": {"value": {"type": "string", "required": True}},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert isinstance(output["outputs"]["value"], SensitiveRef)
    assert sensitive.resolve(output["outputs"]["value"], consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "python-secret"


def test_python_run_marks_result_derived_from_sensitive_input_as_sensitive(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-result",
            "node_kind": "python.run",
            "node_config": {
                "allow_sensitive_values": True,
                "code": "result = ctx.inputs.get('api_key')",
                "input_schema": {"api_key": {"type": "string", "required": True}},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert isinstance(output["result"], SensitiveRef)
    assert sensitive.resolve(output["result"], consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "python-secret"


def test_python_run_redacts_sensitive_value_from_captured_stdout(tmp_path) -> None:
    sensitive = SensitiveValueService()
    secret_ref = sensitive.create(
        "python-secret",
        scope_id="session-sensitive-python",
        source="runtime_input",
    )
    context = RuntimeContext(
        variables={"api_key": secret_ref},
        flow_runtime={"sensitive_value_service": sensitive},
    )
    registry = _registry(tmp_path)

    output = registry.execute(
        "python.run",
        {
            "node_id": "python-sensitive-stdout",
            "node_kind": "python.run",
            "node_config": {
                "allow_sensitive_values": True,
                "code": "print(ctx.inputs.get('api_key'))",
                "input_schema": {"api_key": {"type": "string", "required": True}},
            },
        },
        context,
    )

    assert output["status"] == "succeeded"
    assert "python-secret" not in output["stdout"]
    assert "<redacted>" in output["stdout"]
