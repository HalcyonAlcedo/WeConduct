from __future__ import annotations

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.runtime.engine import RuntimeContext
from weconduct.runtime.execution_context import ExecutionSessionContext


def _build_sensitive_runtime_context() -> tuple[RuntimeContext, SensitiveValueService, list[dict]]:
    context = RuntimeContext(
        execution_session_context=ExecutionSessionContext(session_id="sensitive-write-session")
    )
    sensitive_values = SensitiveValueService()
    audit_events: list[dict] = []
    context.flow_runtime["sensitive_value_service"] = sensitive_values
    context.flow_runtime["sensitive_variable_modification_sink"] = audit_events.append
    context.flow_runtime["active_runtime_node"] = {
        "node_id": "node-write",
        "node_kind": "data.set_variable",
    }
    return context, sensitive_values, audit_events


def test_sensitive_variable_rewrites_remain_references_and_audit_without_values() -> None:
    context, sensitive_values, audit_events = _build_sensitive_runtime_context()
    context.variables["token"] = sensitive_values.create(
        "initial-secret",
        scope_id="sensitive-write-session",
        source="encrypted_parameter",
    )

    context.variables["token"] = "rotated-secret"
    context.variables.update({"token": "second-secret"})
    context.variables = {"token": "third-secret", "other": "plain-value"}

    token = context.variables["token"]
    assert isinstance(token, SensitiveRef)
    assert sensitive_values.resolve(token, consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "third-secret"
    assert context.variables["other"] == "plain-value"
    assert len(audit_events) == 3
    assert all(event["category"] == "runtime.sensitive_variable_modified" for event in audit_events)
    assert all(event["severity"] == "warn" for event in audit_events)
    assert all(event["variable_name"] == "token" for event in audit_events)
    assert all(event["node_id"] == "node-write" for event in audit_events)
    assert "initial-secret" not in repr(audit_events)
    assert "rotated-secret" not in repr(audit_events)
    assert "second-secret" not in repr(audit_events)
    assert "third-secret" not in repr(audit_events)
