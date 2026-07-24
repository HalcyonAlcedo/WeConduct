from __future__ import annotations

from dataclasses import asdict
from threading import Thread
from time import monotonic, sleep

from weconduct.application.pending_input.models import PendingInputField, PendingInputRequest
from weconduct.application.pending_input.service import PendingInputService
from weconduct.application.sensitive_values.encryption import encrypt_parameter_values
from weconduct.application.sensitive_values.models import SensitiveConsumer
from weconduct.application.sensitive_values.redaction import redact_sensitive_payload
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.runtime.engine import CancellationContext


def test_090_sensitive_workflow_unlocks_waits_and_redacts_event_payload() -> None:
    encrypted = encrypt_parameter_values(
        {"api_key": "integration-secret"},
        password="correct",
        parameter_set_id="integration-parameters",
    )
    sensitive = SensitiveValueService()
    unlocked = sensitive.unlock_encrypted_parameters(
        encrypted,
        password="correct",
        scope_id="integration-session",
    )
    ref = unlocked["api_key"]
    assert sensitive.resolve(ref, consumer=SensitiveConsumer.RUNTIME_EXECUTOR) == "integration-secret"

    pending = PendingInputService()
    request = PendingInputRequest(
        request_id="integration-input",
        execution_id="integration-session",
        node_id="input",
        fields=(PendingInputField(field_id="token", label="Token", sensitive=True),),
    )
    pending.create(request)
    result_holder: list[object] = []
    waiter = Thread(
        target=lambda: result_holder.append(
            pending.wait(request.request_id, CancellationContext())
        ),
        daemon=True,
    )
    waiter.start()
    deadline = monotonic() + 1
    while monotonic() < deadline:
        if pending.get_snapshot(request.request_id).status == "waiting":
            break
        sleep(0.01)
    pending.submit(request.request_id, {"token": "input-secret"})
    waiter.join(timeout=1)
    assert result_holder[0].status == "submitted"
    redacted_event = redact_sensitive_payload(
        asdict(result_holder[0]),
        secret_values=["input-secret"],
    )
    assert "input-secret" not in repr(redacted_event)

    sensitive.revoke_scope("integration-session")
    try:
        sensitive.resolve(ref, consumer=SensitiveConsumer.RUNTIME_EXECUTOR)
    except KeyError:
        pass
    else:
        raise AssertionError("revoked sensitive reference remained resolvable")
