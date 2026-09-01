from __future__ import annotations

from weconduct.network_runtime.errors import build_network_error
from weconduct.network_runtime.models import NetworkContextSnapshot, NetworkOperation


def test_network_error_redacts_url_userinfo_and_compound_secret_parameter_names() -> None:
    operation = NetworkOperation(
        operation_id="network-error-redaction",
        session_id="network-error-session",
        method="GET",
        url="https://example.test/resource",
    )
    error = build_network_error(
        "request to https://alice:proxy-secret@example.test/resource?access_token=access-value"
        "&client_secret=client-value&refresh_token=refresh-value&api_key=api-value failed",
        operation=operation,
        snapshot=NetworkContextSnapshot(context_id="network-error-context"),
    )

    for secret in ("alice", "proxy-secret", "access-value", "client-value", "refresh-value", "api-value"):
        assert secret not in error.message
    assert "<redacted>" in error.message


def test_network_error_redacts_sensitive_details_and_complete_bodies() -> None:
    operation = NetworkOperation(
        operation_id="network-error-detail-redaction",
        session_id="network-error-session",
        method="POST",
        url="https://example.test/resource",
    )
    error = build_network_error(
        "network.transport_failed",
        operation=operation,
        snapshot=NetworkContextSnapshot(context_id="network-error-context"),
        details={
            "headers": {"Authorization": "Bearer secret-token", "content-type": "application/json"},
            "request_body": {"password": "secret-password"},
            "response_body": '{"token":"secret-token"}',
            "nested": {"api_key": "secret-key", "status_code": 502},
        },
    )

    assert error.details == {
        "headers": {"Authorization": "<redacted>", "content-type": "application/json"},
        "request_body": "<redacted>",
        "response_body": "<redacted>",
        "nested": {"api_key": "<redacted>", "status_code": 502},
    }
    assert "secret" not in repr(error)
