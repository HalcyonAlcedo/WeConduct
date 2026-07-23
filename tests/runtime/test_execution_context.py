from __future__ import annotations

from weconduct.runtime.execution_context import ExecutionTokenContext
from weconduct.runtime.engine import RuntimeContext


def test_execution_token_context_round_trips_only_network_reference_identity() -> None:
    context = ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=3,
    )

    snapshot = context.to_snapshot()

    assert snapshot == {
        "network_context_id": "network-context-1",
        "network_context_epoch": 3,
    }
    assert ExecutionTokenContext.from_snapshot(snapshot) == context


def test_execution_token_context_omits_invalid_reference_values() -> None:
    assert ExecutionTokenContext.from_snapshot(
        {"network_context_id": 7, "network_context_epoch": -1}
    ) == ExecutionTokenContext()


def test_execution_token_context_keeps_valid_id_when_epoch_is_absent() -> None:
    assert ExecutionTokenContext.from_snapshot(
        {"network_context_id": "network-context-1"}
    ) == ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=None,
    )


def test_runtime_context_exposes_current_token_context() -> None:
    token_context = ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=3,
    )

    runtime_context = RuntimeContext(execution_token_context=token_context)

    assert runtime_context.execution_token_context == token_context
