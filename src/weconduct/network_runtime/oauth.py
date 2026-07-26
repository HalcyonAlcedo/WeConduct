from __future__ import annotations

from dataclasses import dataclass, field
import json
import ssl
from time import time
from typing import TYPE_CHECKING, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .access_policy import NetworkAccessPolicy
from .models import NetworkContextSnapshot
from .proxy import ProxyResolver
from .tls import TlsResolver, build_ssl_context, verify_response_certificate_pins
from .transport import PinnedDnsHTTPTransport

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
    def __init__(
        self,
        *,
        sensitive_values: SensitiveValueService,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30.0,
        access_policy: NetworkAccessPolicy | None = None,
    ) -> None:
        self._sensitive_values = sensitive_values
        self._transport = transport
        self._access_policy = access_policy or NetworkAccessPolicy()
        if timeout_seconds <= 0:
            raise OAuthConfigurationError("oauth.timeout_invalid")
        self._timeout_seconds = float(timeout_seconds)

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

    def exchange_client_credentials(
        self,
        *,
        request: OAuthClientCredentialsRequest,
        scope_id: str,
        snapshot: NetworkContextSnapshot | None = None,
    ) -> OAuthTokenState:
        if not isinstance(request, OAuthClientCredentialsRequest):
            raise OAuthConfigurationError("oauth.request_invalid")
        self._validate_scope(request.client_secret, scope_id)
        secret = self._resolve_secret(request.client_secret)
        if not isinstance(secret, str):
            raise OAuthConfigurationError("oauth.client_secret_invalid")
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": request.client_id,
        }
        if request.scope:
            data["scope"] = request.scope
        response = self._post_token(
            request.token_url,
            data=data,
            auth=(request.client_id, secret),
            snapshot=snapshot,
        )
        return self.accept_token_response(
            request_id=request.request_id,
            scope_id=scope_id,
            response=response,
        )

    def refresh_access_token(
        self,
        *,
        token_url: str,
        refresh_token: SensitiveRef,
        scope_id: str,
        client_id: str | None = None,
        scope: str | None = None,
        snapshot: NetworkContextSnapshot | None = None,
    ) -> OAuthTokenState:
        parsed = urlsplit(token_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.token_url_invalid")
        self._validate_scope(refresh_token, scope_id)
        secret = self._resolve_secret(refresh_token)
        if not isinstance(secret, str):
            raise OAuthConfigurationError("oauth.refresh_token_invalid")
        data = {"grant_type": "refresh_token", "refresh_token": secret}
        if isinstance(scope, str) and scope.strip():
            data["scope"] = scope.strip()
        auth = (client_id.strip(), "") if isinstance(client_id, str) and client_id.strip() else None
        response = self._post_token(token_url, data=data, auth=auth, snapshot=snapshot)
        return self.accept_token_response(
            request_id=f"oauth-refresh-{uuid4().hex}",
            scope_id=scope_id,
            response=response,
        )

    def _post_token(
        self,
        token_url: str,
        *,
        data: Mapping[str, str],
        auth: tuple[str, str] | None,
        snapshot: NetworkContextSnapshot | None,
    ) -> Mapping[str, object]:
        try:
            resolved_target = self._access_policy.validate_url(token_url)
            tls_config = snapshot.tls if isinstance(getattr(snapshot, "tls", None), dict) else {}
            resolved_tls = TlsResolver().resolve(tls_config)
            verify: ssl.SSLContext | bool = build_ssl_context(resolved_tls)
            proxy_config = snapshot.proxy if isinstance(getattr(snapshot, "proxy", None), dict) else {"mode": "direct"}
            resolved_proxy = ProxyResolver().resolve(proxy_config, token_url)
            transport = self._transport or PinnedDnsHTTPTransport(
                access_policy=self._access_policy,
                verify=verify,
                proxy=resolved_proxy.url,
                trust_env=False,
                http2=True,
            )
            with httpx.Client(
                transport=transport,
                timeout=self._timeout_seconds,
                verify=verify,
                proxy=resolved_proxy.url if self._transport is not None else None,
                trust_env=False,
            ) as client:
                response = client.post(
                    token_url,
                    data=dict(data),
                    auth=auth,
                    extensions=(
                        {"weconduct.resolved_network_target": resolved_target}
                        if resolved_target is not None
                        else None
                    ),
                )
            verify_response_certificate_pins(response, resolved_tls.certificate_pins)
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthConfigurationError("oauth.token_exchange_failed") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise OAuthConfigurationError("oauth.token_exchange_failed")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise OAuthConfigurationError("oauth.token_response_invalid") from exc
        if not isinstance(payload, Mapping):
            raise OAuthConfigurationError("oauth.token_response_invalid")
        return payload

    def _resolve_secret(self, ref: SensitiveRef) -> object:
        from weconduct.application.sensitive_values.models import SensitiveConsumer

        return self._sensitive_values.resolve(
            ref,
            consumer=SensitiveConsumer.NETWORK_RUNTIME,
        )

    @staticmethod
    def _validate_scope(ref: SensitiveRef, scope_id: str) -> None:
        from weconduct.application.sensitive_values.models import SensitiveRef

        if not isinstance(ref, SensitiveRef) or ref.scope_id != scope_id:
            raise OAuthConfigurationError("oauth.sensitive_scope_mismatch")
