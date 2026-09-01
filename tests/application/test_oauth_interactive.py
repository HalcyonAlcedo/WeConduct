from __future__ import annotations

from time import monotonic, sleep

import pytest

from weconduct.application.oauth_interactive import OAuthInteractiveService
from weconduct.application.pending_input import PendingInputService
from weconduct.application.pending_input.models import PendingInputStatus
from weconduct.application.sensitive_values import SensitiveValueService
from weconduct.network_runtime.oauth import (
    OAuthAuthorizationCodePKCERequest,
    OAuthDeviceCodeState,
    OAuthTokenState,
)


class _FakeOAuthService:
    def __init__(self, sensitive_values: SensitiveValueService) -> None:
        self.sensitive_values = sensitive_values
        self.authorization_request = OAuthAuthorizationCodePKCERequest(
            authorization_url="https://example.test/authorize?state=private-state",
            client_id="client",
            redirect_uri="http://127.0.0.1/callback",
            scope="openid",
            state="private-state",
            nonce="private-nonce",
            code_verifier="private-verifier",
            code_challenge="private-challenge",
        )
        self.authorization_exchange: dict[str, object] | None = None
        self.device_exchange_count = 0

    def begin_authorization_code_pkce(self, **_: object) -> OAuthAuthorizationCodePKCERequest:
        return self.authorization_request

    def exchange_authorization_code_pkce(self, **kwargs: object) -> OAuthTokenState:
        self.authorization_exchange = kwargs
        return _token_state(self.sensitive_values, "pkce-secret")

    def request_device_code(self, **_: object) -> OAuthDeviceCodeState:
        return OAuthDeviceCodeState(
            device_code="private-device-code",
            user_code="ABCD-EFGH",
            verification_uri="https://example.test/device",
            expires_at=monotonic() + 60,
            interval=0.01,
        )

    def exchange_device_code(self, **_: object) -> OAuthTokenState:
        self.device_exchange_count += 1
        return _token_state(self.sensitive_values, "device-secret")


def _token_state(sensitive_values: SensitiveValueService, value: str) -> OAuthTokenState:
    return OAuthTokenState(
        access_token=sensitive_values.create(value, scope_id="flow-scope", source="derived"),
        refresh_token=None,
        token_type="Bearer",
        expires_at=monotonic() + 60,
    )


def _build_service(holder: list[_FakeOAuthService]) -> OAuthInteractiveService:
    def factory(sensitive_values: SensitiveValueService) -> _FakeOAuthService:
        service = _FakeOAuthService(sensitive_values)
        holder.append(service)
        return service

    return OAuthInteractiveService(
        pending_input_service=PendingInputService(),
        oauth_service_factory=factory,
    )


def _wait_for_status(service: OAuthInteractiveService, flow_id: str, expected: str) -> dict[str, object]:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        snapshot = service.get_flow(flow_id)
        if snapshot["status"] == expected:
            return snapshot
        sleep(0.01)
    return service.get_flow(flow_id)


def test_authorization_code_flow_uses_shared_pending_input_and_hides_callback_values() -> None:
    fake_services: list[_FakeOAuthService] = []
    service = _build_service(fake_services)

    started = service.begin_authorization_code(
        authorization_url="https://example.test/authorize",
        token_url="https://example.test/token",
        client_id="client",
        redirect_uri="http://127.0.0.1/callback",
        scope="openid",
        scope_id="flow-scope",
    )

    assert started["status"] == "waiting_input"
    assert "private-state" in started["authorization_url"]
    pending = started["pending_input"]
    assert isinstance(pending, dict)
    assert {field["field_id"] for field in pending["fields"]} == {"code", "state", "nonce"}
    assert "private-verifier" not in repr(started)
    flow_id = started["flow_id"]

    submitted = service.submit_flow(
        flow_id,
        {"code": "authorization-code", "state": "private-state", "nonce": "private-nonce"},
    )
    assert submitted["status"] in {"exchanging", "succeeded"}
    result = _wait_for_status(service, flow_id, "succeeded")

    assert result["status"] == "succeeded"
    assert "access_token" not in result
    assert "pkce-secret" not in repr(result)
    assert fake_services[0].authorization_exchange is not None
    assert fake_services[0].authorization_exchange["code"] == "authorization-code"


def test_device_code_flow_uses_shared_confirmation_and_supports_cancellation() -> None:
    fake_services: list[_FakeOAuthService] = []
    service = _build_service(fake_services)
    started = service.begin_device_code(
        device_authorization_url="https://example.test/device",
        token_url="https://example.test/token",
        client_id="client",
        scope="openid",
        scope_id="flow-scope",
    )

    assert started["status"] == "waiting_input"
    assert started["user_code"] == "ABCD-EFGH"
    assert "private-device-code" not in repr(started)
    flow_id = started["flow_id"]
    pending = started["pending_input"]
    assert isinstance(pending, dict)
    assert pending["fields"][0]["field_id"] == "approved"

    service.submit_flow(flow_id, {"approved": True})
    result = _wait_for_status(service, flow_id, "succeeded")
    assert result["status"] == "succeeded"
    assert fake_services[0].device_exchange_count == 1
    assert "device-secret" not in repr(result)

    cancelled = service.begin_device_code(
        device_authorization_url="https://example.test/device",
        token_url="https://example.test/token",
        client_id="client",
        scope_id="flow-scope",
    )
    service.cancel_flow(cancelled["flow_id"])
    assert service.get_flow(cancelled["flow_id"])["status"] == "cancelled"


def test_submit_flow_rejects_unknown_flow() -> None:
    service = OAuthInteractiveService(pending_input_service=PendingInputService())

    with pytest.raises(ValueError, match="oauth.flow_not_found"):
        service.submit_flow("missing-flow", {})


def test_close_revokes_each_flow_sensitive_scope_including_completed_tokens() -> None:
    fake_services: list[_FakeOAuthService] = []
    service = _build_service(fake_services)
    started = service.begin_device_code(
        device_authorization_url="https://example.test/device",
        token_url="https://example.test/token",
        client_id="client",
        scope_id="flow-scope",
    )
    flow_id = started["flow_id"]
    assert isinstance(flow_id, str)
    service.submit_flow(flow_id, {"approved": True})
    result = _wait_for_status(service, flow_id, "succeeded")
    assert result["status"] == "succeeded"

    flow = service._flows[flow_id]  # type: ignore[attr-defined]
    assert flow.sensitive_values.values_for_scope("flow-scope")

    service.close()

    assert flow.sensitive_values.values_for_scope("flow-scope") == ()


def test_submit_flow_maps_expired_pending_input_to_structured_oauth_error() -> None:
    fake_services: list[_FakeOAuthService] = []
    service = _build_service(fake_services)
    started = service.begin_device_code(
        device_authorization_url="https://example.test/device",
        token_url="https://example.test/token",
        client_id="client",
        scope_id="flow-scope",
    )
    flow_id = started["flow_id"]
    request_id = started["request_id"]
    assert isinstance(flow_id, str)
    assert isinstance(request_id, str)
    record = service.pending_input_service._records[request_id]  # type: ignore[attr-defined]
    record.status = PendingInputStatus.TIMED_OUT

    with pytest.raises(ValueError, match="oauth.flow_expired") as exc_info:
        service.submit_flow(flow_id, {"approved": True})

    assert getattr(exc_info.value, "error_code") == "oauth.flow_expired"


def test_submit_flow_rejects_duplicate_submission_with_structured_oauth_error() -> None:
    fake_services: list[_FakeOAuthService] = []
    service = _build_service(fake_services)
    started = service.begin_device_code(
        device_authorization_url="https://example.test/device",
        token_url="https://example.test/token",
        client_id="client",
        scope_id="flow-scope",
    )
    flow_id = started["flow_id"]
    assert isinstance(flow_id, str)
    service.submit_flow(flow_id, {"approved": True})

    with pytest.raises(ValueError, match="oauth.flow_state_conflict") as exc_info:
        service.submit_flow(flow_id, {"approved": True})

    assert getattr(exc_info.value, "error_code") == "oauth.flow_state_conflict"


def test_begin_oauth_flow_after_service_close_returns_structured_error() -> None:
    service = OAuthInteractiveService(pending_input_service=PendingInputService())
    service.close()

    with pytest.raises(ValueError, match="oauth.service_closed") as exc_info:
        service.begin_device_code(
            device_authorization_url="https://example.test/device",
            token_url="https://example.test/token",
            client_id="client",
            scope_id="flow-scope",
        )

    assert getattr(exc_info.value, "error_code") == "oauth.service_closed"
