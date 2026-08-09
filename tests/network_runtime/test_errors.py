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
