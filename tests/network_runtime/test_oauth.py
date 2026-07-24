from __future__ import annotations

import pytest

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.network_runtime.oauth import OAuthConfigurationError, OAuthService


def test_oauth_service_keeps_client_and_token_secrets_as_sensitive_refs() -> None:
    sensitive = SensitiveValueService()
    service = OAuthService(sensitive_values=sensitive)
    client_secret = sensitive.create(
        "client-secret",
        scope_id="session-1",
        source="runtime_input",
    )

    request = service.build_client_credentials_request(
        token_url="https://example.test/oauth/token",
        client_id="client-id",
        client_secret=client_secret,
        scope="read write",
        scope_id="session-1",
    )
    state = service.accept_token_response(
        request_id=request.request_id,
        scope_id="session-1",
        response={
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )

    assert isinstance(state.access_token, SensitiveRef)
    assert isinstance(state.refresh_token, SensitiveRef)
    assert "access-secret" not in repr(state)
    assert sensitive.resolve(state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "access-secret"


def test_oauth_service_rejects_invalid_token_responses_without_leaking_values() -> None:
    service = OAuthService(sensitive_values=SensitiveValueService())

    with pytest.raises(OAuthConfigurationError, match="access_token") as exc_info:
        service.accept_token_response(
            request_id="request-1",
            scope_id="session-1",
            response={"error": "invalid_grant", "error_description": "secret details"},
        )

    assert "secret details" not in str(exc_info.value)
