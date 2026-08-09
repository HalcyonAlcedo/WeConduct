from __future__ import annotations

import pytest
import httpx

from weconduct.application.sensitive_values.models import SensitiveConsumer, SensitiveRef
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.network_runtime.access_policy import NetworkAccessPolicy
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


def test_oauth_service_applies_network_access_policy_before_token_exchange() -> None:
    observed = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["called"] = True
        return httpx.Response(200, json={"access_token": "token"}, request=request)

    sensitive = SensitiveValueService()
    service = OAuthService(
        sensitive_values=sensitive,
        transport=httpx.MockTransport(handler),
    )
    secret = sensitive.create("client-secret", scope_id="session-policy", source="runtime_input")
    request = service.build_client_credentials_request(
        token_url="http://127.0.0.1:8080/token",
        client_id="client-id",
        client_secret=secret,
        scope=None,
        scope_id="session-policy",
    )

    with pytest.raises(OAuthConfigurationError, match="oauth.token_exchange_failed"):
        service.exchange_client_credentials(request=request, scope_id="session-policy")

    assert observed["called"] is False


def test_oauth_service_executes_client_credentials_exchange_without_exposing_secret() -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("authorization", "")
        observed["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"access_token": "access-secret", "token_type": "Bearer", "expires_in": 60},
            request=request,
        )

    sensitive = SensitiveValueService()
    service = OAuthService(
        sensitive_values=sensitive,
        transport=httpx.MockTransport(handler),
        access_policy=NetworkAccessPolicy(allowed_hostnames=frozenset({"example.test"})),
    )
    client_secret = sensitive.create("client-secret", scope_id="session-2", source="runtime_input")
    request = service.build_client_credentials_request(
        token_url="https://example.test/oauth/token",
        client_id="client-id",
        client_secret=client_secret,
        scope="read",
        scope_id="session-2",
    )

    state = service.exchange_client_credentials(request=request, scope_id="session-2")

    assert state.token_type == "Bearer"
    assert "client-secret" not in observed["body"]
    assert "client-id" in observed["body"]
    assert sensitive.resolve(state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "access-secret"


def test_oauth_service_rejects_unwrapped_custom_transport() -> None:
    class CustomTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

    with pytest.raises(OAuthConfigurationError, match="oauth.custom_transport_unsupported"):
        OAuthService(
            sensitive_values=SensitiveValueService(),
            transport=CustomTransport(),
        )


def test_oauth_service_refreshes_a_token_and_normalizes_provider_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "secret provider detail"},
            request=request,
        )

    sensitive = SensitiveValueService()
    service = OAuthService(
        sensitive_values=sensitive,
        transport=httpx.MockTransport(handler),
    )
    refresh_ref = sensitive.create("refresh-secret", scope_id="session-3", source="runtime_input")

    with pytest.raises(OAuthConfigurationError, match="oauth.token_exchange_failed") as exc_info:
        service.refresh_access_token(
            token_url="https://example.test/oauth/token",
            refresh_token=refresh_ref,
            scope_id="session-3",
        )

    assert "secret provider detail" not in str(exc_info.value)
