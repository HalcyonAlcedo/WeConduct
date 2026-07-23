from __future__ import annotations

from weconduct.runtime.execution_context import ExecutionSessionContext, ExecutionTokenContext
from weconduct.runtime.engine import CancellationContext, RuntimeContext


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


def test_runtime_context_delegates_token_and_cancellation_to_session_context() -> None:
    cancellation_context = CancellationContext()
    token_context = ExecutionTokenContext(
        network_context_id="network-context-1",
        network_context_epoch=3,
    )
    session_context = ExecutionSessionContext(
        session_id="runtime-session-1",
        token_context=token_context,
        cancellation_context=cancellation_context,
    )

    runtime_context = RuntimeContext(execution_session_context=session_context)
    next_token_context = ExecutionTokenContext(
        network_context_id="network-context-2",
        network_context_epoch=4,
    )
    next_cancellation_context = CancellationContext()

    assert runtime_context.execution_token_context == token_context
    assert runtime_context.cancellation_context is cancellation_context
    runtime_context.execution_token_context = next_token_context
    runtime_context.cancellation_context = next_cancellation_context

    assert session_context.token_context == next_token_context
    assert session_context.cancellation_context is next_cancellation_context
