from __future__ import annotations

from threading import Thread
from time import monotonic, sleep

import pytest

from weconduct.application.pending_input.models import (
    PendingInputField,
    PendingInputRequest,
)
from weconduct.application.pending_input.service import PendingInputService
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
    with pytest.raises(ValueError, match="request is not waiting"):
        service.submit(request.request_id, {"username": "other", "password": "other"})


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


def test_pending_input_clears_submitted_values_and_removes_records_at_session_end() -> None:
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

    with pytest.raises(ValueError, match="pending input request was not found"):
        service.get_snapshot(request.request_id)


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
