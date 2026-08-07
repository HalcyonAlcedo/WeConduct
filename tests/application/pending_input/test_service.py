from __future__ import annotations

from threading import Thread
from time import monotonic, sleep

import pytest

from weconduct.application.pending_input.models import (
    PendingInputField,
    PendingInputRequest,
)
from weconduct.application.pending_input.service import PendingInputService
from weconduct.application.pending_input.service import PendingInputStateError
from weconduct.runtime.engine import CancellationContext


def test_pending_input_rejects_default_value_for_sensitive_field() -> None:
    with pytest.raises(ValueError, match="sensitive fields cannot define defaults"):
        PendingInputRequest(
            request_id="request-1",
            execution_id="execution-1",
            node_id="node-1",
            fields=(
                PendingInputField(
                    field_id="password",
                    label="Password",
                    sensitive=True,
                    default_value="not-allowed",
                ),
            ),
        )


def test_pending_input_rejects_second_active_request_for_same_execution() -> None:
    service = PendingInputService()
    service.create(
        PendingInputRequest(
            request_id="request-first",
            execution_id="execution-1",
            node_id="node-first",
            fields=(PendingInputField(field_id="value", label="Value"),),
        )
    )

    with pytest.raises(ValueError, match="execution already has a pending input request"):
        service.create(
            PendingInputRequest(
                request_id="request-second",
                execution_id="execution-1",
                node_id="node-second",
                fields=(PendingInputField(field_id="value", label="Value"),),
            )
        )


def test_pending_input_returns_active_request_after_a_prior_request_is_terminal() -> None:
    service = PendingInputService()
    service.create(
        PendingInputRequest(
            request_id="request-first",
            execution_id="execution-1",
            node_id="node-first",
            fields=(PendingInputField(field_id="value", label="Value"),),
        )
    )
    service.cancel_session("execution-1")
    service.create(
        PendingInputRequest(
            request_id="request-second",
            execution_id="execution-1",
            node_id="node-second",
            fields=(PendingInputField(field_id="value", label="Value"),),
        )
    )

    snapshot = service.get_snapshot_for_execution("execution-1")

    assert snapshot is not None
    assert snapshot.request_id == "request-second"
    assert snapshot.status == "created"


def test_pending_input_submits_multiple_fields_atomically() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-1",
        execution_id="execution-1",
        node_id="node-1",
        fields=(
            PendingInputField(field_id="username", label="Username"),
            PendingInputField(field_id="password", label="Password", sensitive=True),
        ),
    )
    service.create(request)
    result_holder: list[object] = []
    worker = Thread(
        target=lambda: result_holder.append(
            service.wait(request_id=request.request_id, cancellation=CancellationContext())
        ),
        daemon=True,
    )
    worker.start()
    deadline = monotonic() + 1
    while service.get_snapshot(request.request_id).status != "waiting" and monotonic() < deadline:
        sleep(0.01)

    with pytest.raises(ValueError, match="missing required fields"):
        service.submit(request.request_id, {"username": "alice"})

    assert service.get_snapshot(request.request_id).status == "waiting"
    submitted = service.submit(
        request.request_id,
        {"username": "alice", "password": "secret"},
    )
    worker.join(timeout=1)

    assert submitted.status == "submitted"
    assert worker.is_alive() is False
    assert result_holder[0].values == {"username": "alice", "password": "secret"}
    with pytest.raises(PendingInputStateError) as exc_info:
        service.submit(request.request_id, {"username": "other", "password": "other"})
    assert exc_info.value.state == "submitted"


def test_pending_input_accepts_submission_immediately_after_activation() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-immediate",
        execution_id="execution-1",
        node_id="node-1",
        fields=(PendingInputField(field_id="answer", label="Answer"),),
    )
    service.create(request)

    activated = service.activate(request.request_id)
    submitted = service.submit(request.request_id, {"answer": "ready"})
    result = service.wait(request.request_id, CancellationContext())

    assert activated.status == "waiting"
    assert submitted.status == "submitted"
    assert result.values == {"answer": "ready"}


def test_pending_input_rejects_values_that_do_not_match_declared_types() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-typed",
        execution_id="execution-typed",
        node_id="node-typed",
        fields=(
            PendingInputField(field_id="count", label="Count", value_type="integer"),
            PendingInputField(field_id="enabled", label="Enabled", value_type="boolean"),
            PendingInputField(field_id="items", label="Items", value_type="array"),
        ),
    )
    service.create(request)
    service.activate(request.request_id)

    with pytest.raises(ValueError, match="field count must be an integer"):
        service.submit(
            request.request_id,
            {"count": "1", "enabled": True, "items": []},
        )

    with pytest.raises(ValueError, match="field enabled must be a boolean"):
        service.submit(
            request.request_id,
            {"count": 1, "enabled": 1, "items": []},
        )

    with pytest.raises(ValueError, match="field items must be an array"):
        service.submit(
            request.request_id,
            {"count": 1, "enabled": True, "items": {}},
        )

    submitted = service.submit(
        request.request_id,
        {"count": 1, "enabled": True, "items": ["ok"]},
    )
    assert submitted.status == "submitted"


def test_pending_input_type_validation_exposes_structured_error_details() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-structured-error",
        execution_id="execution-structured-error",
        node_id="node-structured-error",
        fields=(PendingInputField(field_id="attempt_count", label="Attempts", value_type="integer"),),
    )
    service.create(request)
    service.activate(request.request_id)

    with pytest.raises(ValueError) as exc_info:
        service.submit(request.request_id, {"attempt_count": "not-an-integer"})

    assert exc_info.value.error_code == "operation.input_invalid"  # type: ignore[attr-defined]
    assert exc_info.value.details == {  # type: ignore[attr-defined]
        "validation_kind": "type_mismatch",
        "field_id": "attempt_count",
        "expected_type": "integer",
        "actual_type": "string",
    }
    assert service.get_snapshot(request.request_id).status.value == "waiting"


def test_pending_input_accepts_list_type_alias_used_by_external_forms() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-list-alias",
        execution_id="execution-list-alias",
        node_id="node-list-alias",
        fields=(PendingInputField(field_id="items", label="Items", value_type="list"),),
    )
    service.create(request)
    service.activate(request.request_id)

    submitted = service.submit(request.request_id, {"items": ["one", "two"]})

    assert submitted.status == "submitted"


def test_pending_input_rejects_duplicate_submission_with_terminal_state() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-duplicate",
        execution_id="execution-duplicate",
        node_id="node-duplicate",
        fields=(PendingInputField(field_id="answer", label="Answer"),),
    )
    service.create(request)
    service.activate(request.request_id)
    service.submit(request.request_id, {"answer": "first"})

    with pytest.raises(PendingInputStateError) as exc_info:
        service.submit(request.request_id, {"answer": "second"})

    assert exc_info.value.state == "submitted"


def test_pending_input_bounds_terminal_submitted_records() -> None:
    service = PendingInputService(terminal_record_limit=1)

    for index in (1, 2):
        request = PendingInputRequest(
            request_id=f"request-limit-{index}",
            execution_id=f"execution-limit-{index}",
            node_id=f"node-limit-{index}",
            fields=(PendingInputField(field_id="answer", label="Answer"),),
        )
        service.create(request)
        service.activate(request.request_id)
        service.submit(request.request_id, {"answer": str(index)})

    with pytest.raises(ValueError, match="pending input request was not found"):
        service.get_snapshot("request-limit-1")
    assert service.get_snapshot("request-limit-2").status == "submitted"


def test_pending_input_bounds_terminal_timed_out_records() -> None:
    service = PendingInputService(terminal_record_limit=1)

    for index in (1, 2):
        request = PendingInputRequest(
            request_id=f"request-timeout-limit-{index}",
            execution_id=f"execution-timeout-limit-{index}",
            node_id=f"node-timeout-limit-{index}",
            fields=(PendingInputField(field_id="answer", label="Answer"),),
            timeout_seconds=0.001,
        )
        service.create(request)
        assert service.wait(request.request_id, CancellationContext()).status == "timed_out"

    with pytest.raises(ValueError, match="pending input request was not found"):
        service.get_snapshot("request-timeout-limit-1")
    assert service.get_snapshot("request-timeout-limit-2").status == "timed_out"


def test_pending_input_clears_submitted_values_and_retains_terminal_metadata_at_session_end() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-sensitive",
        execution_id="execution-1",
        node_id="node-1",
        fields=(PendingInputField(field_id="password", label="Password", sensitive=True),),
    )
    service.create(request)
    cancellation = CancellationContext()
    result_holder: list[object] = []
    worker = Thread(
        target=lambda: result_holder.append(
            service.wait(request_id=request.request_id, cancellation=cancellation)
        ),
        daemon=True,
    )
    worker.start()
    deadline = monotonic() + 1
    while service.get_snapshot(request.request_id).status != "waiting" and monotonic() < deadline:
        sleep(0.01)

    service.submit(request.request_id, {"password": "private-password"})
    worker.join(timeout=1)

    assert result_holder[0].values == {"password": "private-password"}
    assert service._records[request.request_id].values == {}  # type: ignore[attr-defined]

    service.cancel_session(request.execution_id)

    terminal = service.get_snapshot(request.request_id)
    assert terminal.status == "submitted"


def test_pending_input_times_out_when_positive_timeout_expires() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-timeout",
        execution_id="execution-1",
        node_id="node-1",
        fields=(PendingInputField(field_id="value", label="Value"),),
        timeout_seconds=0.02,
    )
    service.create(request)

    result = service.wait(request_id=request.request_id, cancellation=CancellationContext())

    assert result.status == "timed_out"
    assert result.values == {}
    assert service.get_snapshot(request.request_id).status == "timed_out"


def test_pending_input_wait_is_cancelled_without_timeout() -> None:
    service = PendingInputService()
    request = PendingInputRequest(
        request_id="request-cancelled",
        execution_id="execution-1",
        node_id="node-1",
        fields=(PendingInputField(field_id="value", label="Value"),),
        timeout_seconds=0,
    )
    service.create(request)
    cancellation = CancellationContext()
    result_holder: list[object] = []
    worker = Thread(
        target=lambda: result_holder.append(
            service.wait(request_id=request.request_id, cancellation=cancellation)
        ),
        daemon=True,
    )
    worker.start()
    deadline = monotonic() + 1
    while service.get_snapshot(request.request_id).status != "waiting" and monotonic() < deadline:
        sleep(0.01)

    cancellation.request_cancel("session cancelled")
    worker.join(timeout=1)

    assert worker.is_alive() is False
    assert result_holder[0].status == "cancelled"
