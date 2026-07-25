from __future__ import annotations

import json
import sys

from weconduct.cli.main import main
from weconduct.application.pending_input.models import PendingInputField, PendingInputRequest, PendingInputSnapshot
from weconduct.cli.main import _prompt_pending_input_values, _run_runtime_session_with_cli_input


def test_cli_operation_adapter_uses_shared_invoke_with_cli_caller() -> None:
    from weconduct.cli.operation_adapter import CliOperationAdapter

    calls: list[dict[str, object]] = []

    class _OperationService:
        def describe(self, operation_id: str) -> object:
            return type("Descriptor", (), {"operation_id": operation_id, "contract_version": "1"})()

        def invoke(
            self,
            operation_id: str,
            payload: dict[str, object],
            *,
            caller: object,
            idempotency_key: str | None,
        ) -> dict[str, object]:
            calls.append(
                {
                    "operation_id": operation_id,
                    "payload": payload,
                    "caller": caller,
                    "idempotency_key": idempotency_key,
                }
            )
            return {"capabilities": {}}

    descriptor, result = CliOperationAdapter(_OperationService()).invoke(
        "host.capabilities",
        {},
    )

    assert descriptor.contract_version == "1"
    assert result == {"capabilities": {}}
    assert calls[0]["caller"].caller_id == "cli:local"
    assert calls[0]["caller"].permissions == frozenset({"operation.invoke"})


def test_cli_operation_uses_operation_registry_and_json_contract(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "operation", "host.capabilities", "--payload", "{}"],
    )

    exit_code = main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation_id"] == "host.capabilities"
    assert "capabilities" in payload["result"]


def test_cli_operation_returns_nonzero_for_invalid_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["weconduct", "operation", "project.create", "--payload", "{}"],
    )

    exit_code = main()
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert payload["error_code"] == "operation.input_invalid"


def test_cli_pending_input_uses_getpass_for_sensitive_fields(monkeypatch) -> None:
    request = PendingInputRequest(
        request_id="request-cli",
        execution_id="execution-cli",
        node_id="node-cli",
        fields=(
            PendingInputField(field_id="name", label="Name"),
            PendingInputField(field_id="secret", label="Secret", sensitive=True),
        ),
    )
    snapshot = PendingInputSnapshot(
        request_id=request.request_id,
        execution_id=request.execution_id,
        node_id=request.node_id,
        status="waiting",
        fields=request.fields,
        timeout_seconds=0,
    )
    plain_prompts: list[str] = []
    secret_prompts: list[str] = []
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: plain_prompts.append(prompt) or "alice",
    )
    monkeypatch.setattr(
        "weconduct.cli.main.getpass.getpass",
        lambda prompt: secret_prompts.append(prompt) or "top-secret",
    )

    values = _prompt_pending_input_values(snapshot)

    assert values == {"name": "alice", "secret": "top-secret"}
    assert plain_prompts == ["Name: "]
    assert secret_prompts == ["Secret: "]


def test_cli_runtime_worker_submits_pending_input_without_blocking_runtime_thread(monkeypatch) -> None:
    request = PendingInputRequest(
        request_id="request-runtime-cli",
        execution_id="execution-runtime-cli",
        node_id="node-runtime-cli",
        fields=(PendingInputField(field_id="name", label="Name"),),
    )
    snapshot = PendingInputSnapshot(
        request_id=request.request_id,
        execution_id=request.execution_id,
        node_id=request.node_id,
        status="waiting",
        fields=request.fields,
        timeout_seconds=0,
    )

    class _Service:
        def __init__(self) -> None:
            self.pending = True
            self.submitted: dict[str, object] | None = None

        def run_runtime_session(self, *, session_id: str) -> dict:
            while self.pending:
                pass
            return {"status": "completed", "session_id": session_id}

        def get_pending_input_snapshot(self, *, execution_id: str):
            return snapshot if self.pending else None

        def submit_pending_input(self, *, execution_id: str, request_id: str, values: dict):
            self.submitted = values
            self.pending = False
            return {"status": "submitted"}

    service = _Service()
    monkeypatch.setattr("weconduct.cli.main._prompt_pending_input_values", lambda current: {"name": "alice"})

    result = _run_runtime_session_with_cli_input(service, session_id=request.execution_id)

    assert result == {"status": "completed", "session_id": request.execution_id}
    assert service.submitted == {"name": "alice"}
