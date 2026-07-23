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
