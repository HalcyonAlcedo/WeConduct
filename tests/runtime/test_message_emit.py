from __future__ import annotations

from weconduct.runtime.engine import RuntimeContext, RuntimeExecutorRegistry


def test_message_emit_publishes_resolved_message_with_normalized_severity() -> None:
    emitted_events: list[dict] = []
    context = RuntimeContext(
        variables={"operator": "Ada"},
        flow_runtime={"runtime_diagnostic_sink": emitted_events.append},
    )

    result = RuntimeExecutorRegistry().execute(
        "message.emit",
        {
            "node_id": "message-1",
            "node_kind": "message.emit",
            "node_config": {
                "message": "running for ${operator}",
                "severity": "warn",
            },
        },
        context,
    )

    assert result == {
        "status": "succeeded",
        "node_id": "message-1",
        "message": "running for Ada",
        "severity": "warning",
    }
    assert emitted_events == [
        {
            "category": "runtime.message",
            "severity": "warning",
            "message": "running for Ada",
            "node_id": "message-1",
            "node_kind": "message.emit",
        }
    ]


def test_message_emit_succeeds_without_runtime_diagnostic_sink() -> None:
    result = RuntimeExecutorRegistry().execute(
        "message.emit",
        {
            "node_id": "message-1",
            "node_kind": "message.emit",
            "node_config": {"message": "progress", "severity": "fatal"},
        },
        RuntimeContext(),
    )

    assert result == {
        "status": "succeeded",
        "node_id": "message-1",
        "message": "progress",
        "severity": "fatal",
    }
