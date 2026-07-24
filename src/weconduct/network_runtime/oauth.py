from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

if TYPE_CHECKING:
    from weconduct.application.sensitive_values.models import SensitiveRef
    from weconduct.application.sensitive_values.service import SensitiveValueService


class OAuthConfigurationError(ValueError):
    """Stable OAuth configuration/protocol error without provider secret details."""


@dataclass(frozen=True, repr=False)
class OAuthClientCredentialsRequest:
    request_id: str
    token_url: str
    client_id: str
    client_secret: SensitiveRef
    scope: str | None = None

    def __repr__(self) -> str:
        return f"OAuthClientCredentialsRequest(request_id={self.request_id!r}, token_url={self.token_url!r})"


@dataclass(frozen=True, repr=False)
class OAuthTokenState:
    access_token: SensitiveRef
    refresh_token: SensitiveRef | None
    token_type: str
    expires_at: float | None

    def __repr__(self) -> str:
        return "OAuthTokenState(<sensitive>)"


class OAuthService:
    def __init__(self, *, sensitive_values: SensitiveValueService) -> None:
        self._sensitive_values = sensitive_values

    def build_client_credentials_request(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: SensitiveRef,
        scope: str | None,
        scope_id: str,
    ) -> OAuthClientCredentialsRequest:
        parsed = urlsplit(token_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.token_url_invalid")
        if not isinstance(client_id, str) or not client_id.strip():
            raise OAuthConfigurationError("oauth.client_id_required")
        from weconduct.application.sensitive_values.models import SensitiveRef

        if not isinstance(client_secret, SensitiveRef) or client_secret.scope_id != scope_id:
            raise OAuthConfigurationError("oauth.client_secret_sensitive_ref_required")
        return OAuthClientCredentialsRequest(
            request_id=f"oauth-request-{uuid4().hex}",
            token_url=token_url,
            client_id=client_id.strip(),
            client_secret=client_secret,
            scope=scope.strip() if isinstance(scope, str) and scope.strip() else None,
        )

    def accept_token_response(
        self,
        *,
        request_id: str,
        scope_id: str,
        response: Mapping[str, object],
    ) -> OAuthTokenState:
        if not isinstance(response, Mapping):
            raise OAuthConfigurationError("oauth.token_response_invalid")
        access_token = response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuthConfigurationError("oauth.access_token_missing")
        token_type = response.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type.strip():
            raise OAuthConfigurationError("oauth.token_type_invalid")
        expires_in = response.get("expires_in")
        if expires_in is not None and (
            not isinstance(expires_in, (int, float))
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise OAuthConfigurationError("oauth.expires_in_invalid")
        refresh_token = response.get("refresh_token")
        if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token):
            raise OAuthConfigurationError("oauth.refresh_token_invalid")
        access_ref = self._sensitive_values.create(
            access_token,
            scope_id=scope_id,
            source="derived",
        )
        refresh_ref = (
            self._sensitive_values.create(refresh_token, scope_id=scope_id, source="derived")
            if isinstance(refresh_token, str)
            else None
        )
        return OAuthTokenState(
            access_token=access_ref,
            refresh_token=refresh_ref,
            token_type=token_type.strip(),
            expires_at=(time() + float(expires_in)) if expires_in is not None else None,
        )
