from __future__ import annotations

import pytest

from weconduct.runtime.execution_envelope import (
    ExecutionEnvelope,
    ExecutionEnvelopeError,
    FieldSchema,
)


def test_execution_envelope_exposes_stable_facade_and_commits_outputs_atomically() -> None:
    envelope = ExecutionEnvelope(
        inputs={"name": "alice"},
        metadata={},
        output_schema={"greeting": FieldSchema("greeting", "string", required=True)},
        metadata_schema={"trace": FieldSchema("trace", "string")},
        data_values={"counter": 1},
        allowed_data_fields=frozenset({"counter"}),
        session_info={"session_id": "session-1"},
        network_snapshot={"context_id": "network-1", "epoch": 2},
    )

    assert envelope.context.inputs.get("name") == "alice"
    assert envelope.context.session.info()["session_id"] == "session-1"
    assert envelope.context.network.current() == {"context_id": "network-1", "epoch": 2}
    assert envelope.context.data.get("counter") == 1
    envelope.context.outputs.set("greeting", "hello alice")
    envelope.context.metadata.set("trace", "trace-1")

    committed = envelope.commit()

    assert committed == {
        "outputs": {"greeting": "hello alice"},
        "metadata": {"trace": "trace-1"},
    }


def test_execution_envelope_rejects_undeclared_outputs_and_domain_escape() -> None:
    envelope = ExecutionEnvelope(
        inputs={},
        metadata={},
        output_schema={"value": FieldSchema("value", "integer")},
        metadata_schema={"trace": FieldSchema("trace", "string")},
        allowed_data_fields=frozenset({"allowed"}),
    )

    with pytest.raises(ExecutionEnvelopeError, match="output field is not declared"):
        envelope.context.outputs.set("unknown", 1)
    with pytest.raises(ExecutionEnvelopeError, match="data field is not available"):
        envelope.context.data.get("secret")


def test_execution_envelope_discards_staged_values_on_failure_or_cancel() -> None:
    envelope = ExecutionEnvelope(
        inputs={},
        metadata={},
        output_schema={"value": FieldSchema("value", "integer")},
        metadata_schema={"trace": FieldSchema("trace", "string")},
    )
    envelope.context.outputs.set("value", 7)
    envelope.context.metadata.set("trace", "temporary")

    envelope.discard()

    assert envelope.commit() == {"outputs": {}, "metadata": {}}
