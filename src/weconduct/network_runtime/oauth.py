from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import secrets
import ssl
from time import monotonic as _monotonic, sleep as _sleep, time
from typing import Callable, TYPE_CHECKING, Mapping
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
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


@dataclass(repr=False)
class OAuthAuthorizationCodePKCERequest:
    authorization_url: str
    client_id: str
    redirect_uri: str
    scope: str | None
    state: str
    nonce: str
    code_verifier: str
    code_challenge: str
    request_id: str = field(default_factory=lambda: f"oauth-authorization-{uuid4().hex}")
    _consumed: bool = field(default=False, repr=False)

    def __repr__(self) -> str:
        return (
            "OAuthAuthorizationCodePKCERequest("
            f"authorization_url={self.authorization_url!r}, client_id={self.client_id!r}, "
            f"redirect_uri={self.redirect_uri!r}, scope={self.scope!r}, "
            "state=<sensitive>, nonce=<sensitive>, code_verifier=<sensitive>, "
            "code_challenge=<sensitive>)"
        )


@dataclass(frozen=True, repr=False)
class OAuthDeviceCodeState:
    device_code: str
    user_code: str
    verification_uri: str
    expires_at: float
    interval: float

    def __repr__(self) -> str:
        return (
            "OAuthDeviceCodeState("
            f"user_code={self.user_code!r}, verification_uri={self.verification_uri!r}, "
            "device_code=<sensitive>)"
        )


class OAuthService:
    def __init__(
        self,
        *,
        sensitive_values: SensitiveValueService,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30.0,
        access_policy: NetworkAccessPolicy | None = None,
        allow_insecure_tls: bool = True,
    ) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise OAuthConfigurationError("oauth.custom_transport_unsupported")
        if not isinstance(allow_insecure_tls, bool):
            raise OAuthConfigurationError("oauth.allow_insecure_tls_invalid")
        self._sensitive_values = sensitive_values
        self._transport = transport
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._tls_resolver = TlsResolver(allow_insecure=allow_insecure_tls)
        if timeout_seconds <= 0:
            raise OAuthConfigurationError("oauth.timeout_invalid")
        self._timeout_seconds = float(timeout_seconds)

    def begin_authorization_code_pkce(
        self,
        *,
        authorization_url: str,
        client_id: str,
        redirect_uri: str,
        scope: str | None = None,
    ) -> OAuthAuthorizationCodePKCERequest:
        parsed = urlsplit(authorization_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.authorization_url_invalid")
        if not isinstance(client_id, str) or not client_id.strip():
            raise OAuthConfigurationError("oauth.client_id_required")
        if not isinstance(redirect_uri, str) or not redirect_uri.strip():
            raise OAuthConfigurationError("oauth.redirect_uri_required")
        verifier = secrets.token_urlsafe(48)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(
            {
                "response_type": "code",
                "client_id": client_id.strip(),
                "redirect_uri": redirect_uri.strip(),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "nonce": nonce,
            }
        )
        if isinstance(scope, str) and scope.strip():
            query["scope"] = scope.strip()
        return OAuthAuthorizationCodePKCERequest(
            authorization_url=urlunsplit(parsed._replace(query=urlencode(query))),
            client_id=client_id.strip(),
            redirect_uri=redirect_uri.strip(),
            scope=scope.strip() if isinstance(scope, str) and scope.strip() else None,
            state=state,
            nonce=nonce,
            code_verifier=verifier,
            code_challenge=challenge,
        )

    @staticmethod
    def validate_authorization_callback(
        request: OAuthAuthorizationCodePKCERequest,
        *,
        state: str,
        code: str,
        nonce: str,
    ) -> str:
        if not isinstance(request, OAuthAuthorizationCodePKCERequest):
            raise OAuthConfigurationError("oauth.authorization_request_invalid")
        if request._consumed:
            raise OAuthConfigurationError("oauth.authorization_callback_replayed")
        if not isinstance(state, str) or state != request.state:
            raise OAuthConfigurationError("oauth.authorization_state_mismatch")
        if not isinstance(nonce, str) or nonce != request.nonce:
            raise OAuthConfigurationError("oauth.authorization_nonce_mismatch")
        if not isinstance(code, str) or not code:
            raise OAuthConfigurationError("oauth.authorization_code_missing")
        request._consumed = True
        return code

    @staticmethod
    def create_device_code_state(
        *,
        device_code: str,
        user_code: str,
        verification_uri: str,
        expires_in: float,
        interval: float = 5.0,
        now: Callable[[], float] = _monotonic,
    ) -> OAuthDeviceCodeState:
        if not isinstance(device_code, str) or not device_code:
            raise OAuthConfigurationError("oauth.device_code_missing")
        if not isinstance(user_code, str) or not user_code:
            raise OAuthConfigurationError("oauth.user_code_missing")
        parsed = urlsplit(verification_uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.verification_uri_invalid")
        if expires_in <= 0 or interval <= 0:
            raise OAuthConfigurationError("oauth.device_code_timing_invalid")
        return OAuthDeviceCodeState(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_at=now() + float(expires_in),
            interval=float(interval),
        )

    @staticmethod
    def poll_device_code(
        device: OAuthDeviceCodeState,
        *,
        poll_token: Callable[[str], Mapping[str, object]],
        sleep: Callable[[float], None] = _sleep,
        monotonic: Callable[[], float] = _monotonic,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, object]:
        if not isinstance(device, OAuthDeviceCodeState):
            raise OAuthConfigurationError("oauth.device_code_state_invalid")
        interval = device.interval
        while True:
            if is_cancelled is not None and is_cancelled():
                raise OAuthConfigurationError("oauth.device_code_cancelled")
            if monotonic() >= device.expires_at:
                raise OAuthConfigurationError("oauth.device_code_expired")
            try:
                response = poll_token(device.device_code)
            except OAuthConfigurationError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize provider failures
                raise OAuthConfigurationError("oauth.device_code_poll_failed") from exc
            if not isinstance(response, Mapping):
                raise OAuthConfigurationError("oauth.device_code_response_invalid")
            if response.get("access_token"):
                return response
            error = response.get("error")
            if error == "authorization_pending":
                sleep(interval)
                continue
            if error == "slow_down":
                interval += 5.0
                sleep(interval)
                continue
            if error == "access_denied":
                raise OAuthConfigurationError("oauth.device_code_access_denied")
            if error == "expired_token":
                raise OAuthConfigurationError("oauth.device_code_expired")
            raise OAuthConfigurationError("oauth.device_code_poll_failed")

    def exchange_authorization_code_pkce(
        self,
        *,
        request: OAuthAuthorizationCodePKCERequest,
        token_url: str,
        state: str,
        code: str,
        nonce: str,
        scope_id: str,
        client_secret: SensitiveRef | None = None,
        snapshot: NetworkContextSnapshot | None = None,
    ) -> OAuthTokenState:
        """完成 Authorization Code + PKCE 交换，并在交换后销毁 verifier。"""
        if not isinstance(request, OAuthAuthorizationCodePKCERequest):
            raise OAuthConfigurationError("oauth.authorization_request_invalid")
        parsed = urlsplit(token_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.token_url_invalid")
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise OAuthConfigurationError("oauth.scope_id_required")
        authorization_code = self.validate_authorization_callback(
            request,
            state=state,
            code=code,
            nonce=nonce,
        )
        verifier = request.code_verifier
        if not isinstance(verifier, str) or not verifier:
            raise OAuthConfigurationError("oauth.code_verifier_missing")
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": request.redirect_uri,
            "client_id": request.client_id,
            "code_verifier": verifier,
        }
        if request.scope:
            data["scope"] = request.scope
        auth: tuple[str, str] | None = None
        if client_secret is not None:
            self._validate_scope(client_secret, scope_id)
            secret = self._resolve_secret(client_secret)
            if not isinstance(secret, str):
                raise OAuthConfigurationError("oauth.client_secret_invalid")
            auth = (request.client_id, secret)
        try:
            response = self._post_token(
                token_url,
                data=data,
                auth=auth,
                snapshot=snapshot,
            )
            return self.accept_token_response(
                request_id=request.request_id,
                scope_id=scope_id,
                response=response,
            )
        finally:
            # 授权码只能使用一次，verifier 不跨越授权会话生命周期保留。
            request.code_verifier = ""
            request.state = ""
            request.nonce = ""

    def request_device_code(
        self,
        *,
        device_authorization_url: str,
        client_id: str,
        scope: str | None = None,
        snapshot: NetworkContextSnapshot | None = None,
    ) -> OAuthDeviceCodeState:
        """请求 RFC 8628 device code，返回供 UI 展示和轮询使用的短期状态。"""
        parsed = urlsplit(device_authorization_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.device_authorization_url_invalid")
        if not isinstance(client_id, str) or not client_id.strip():
            raise OAuthConfigurationError("oauth.client_id_required")
        data = {"client_id": client_id.strip()}
        if isinstance(scope, str) and scope.strip():
            data["scope"] = scope.strip()
        payload = self._post_form(
            device_authorization_url,
            data=data,
            auth=None,
            snapshot=snapshot,
            failure_error_code="oauth.device_authorization_failed",
            response_error_code="oauth.device_authorization_response_invalid",
        )
        device_code = payload.get("device_code")
        user_code = payload.get("user_code")
        complete_uri = payload.get("verification_uri_complete")
        verification_uri = (
            complete_uri
            if isinstance(complete_uri, str) and complete_uri
            else payload.get("verification_uri")
        )
        expires_in = payload.get("expires_in")
        interval = payload.get("interval", 5)
        if not isinstance(device_code, str) or not device_code:
            raise OAuthConfigurationError("oauth.device_code_missing")
        if not isinstance(user_code, str) or not user_code:
            raise OAuthConfigurationError("oauth.user_code_missing")
        if not isinstance(verification_uri, str) or not verification_uri:
            raise OAuthConfigurationError("oauth.verification_uri_invalid")
        if (
            not isinstance(expires_in, (int, float))
            or isinstance(expires_in, bool)
            or expires_in <= 0
            or not isinstance(interval, (int, float))
            or isinstance(interval, bool)
            or interval <= 0
        ):
            raise OAuthConfigurationError("oauth.device_code_timing_invalid")
        return self.create_device_code_state(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_in=float(expires_in),
            interval=float(interval),
        )

    def exchange_device_code(
        self,
        *,
        device: OAuthDeviceCodeState,
        token_url: str,
        client_id: str,
        scope_id: str,
        scope: str | None = None,
        snapshot: NetworkContextSnapshot | None = None,
        sleep: Callable[[float], None] = _sleep,
        monotonic: Callable[[], float] = _monotonic,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> OAuthTokenState:
        """轮询 RFC 8628 token endpoint 并将成功 token 存入敏感值服务。"""
        if not isinstance(device, OAuthDeviceCodeState):
            raise OAuthConfigurationError("oauth.device_code_state_invalid")
        parsed = urlsplit(token_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OAuthConfigurationError("oauth.token_url_invalid")
        if not isinstance(client_id, str) or not client_id.strip():
            raise OAuthConfigurationError("oauth.client_id_required")
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise OAuthConfigurationError("oauth.scope_id_required")

        def poll_token(device_code: str) -> Mapping[str, object]:
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id.strip(),
            }
            if isinstance(scope, str) and scope.strip():
                data["scope"] = scope.strip()
            return self._post_form(
                token_url,
                data=data,
                auth=None,
                snapshot=snapshot,
                allowed_status_codes=frozenset(range(200, 300)) | frozenset({400}),
                failure_error_code="oauth.device_code_poll_failed",
                response_error_code="oauth.device_code_response_invalid",
            )

        response = self.poll_device_code(
            device,
            poll_token=poll_token,
            sleep=sleep,
            monotonic=monotonic,
            is_cancelled=is_cancelled,
        )
        return self.accept_token_response(
            request_id=f"oauth-device-{uuid4().hex}",
            scope_id=scope_id,
            response=response,
        )

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
        return self._post_form(
            token_url,
            data=data,
            auth=auth,
            snapshot=snapshot,
            failure_error_code="oauth.token_exchange_failed",
            response_error_code="oauth.token_response_invalid",
        )

    def _post_form(
        self,
        endpoint_url: str,
        *,
        data: Mapping[str, str],
        auth: tuple[str, str] | None,
        snapshot: NetworkContextSnapshot | None,
        allowed_status_codes: frozenset[int] | None = None,
        failure_error_code: str,
        response_error_code: str,
    ) -> Mapping[str, object]:
        try:
            resolved_target = self._access_policy.validate_url(endpoint_url)
            tls_config = snapshot.tls if isinstance(getattr(snapshot, "tls", None), dict) else {}
            resolved_tls = self._tls_resolver.resolve(tls_config)
            verify: ssl.SSLContext | bool = build_ssl_context(resolved_tls)
            proxy_config = snapshot.proxy if isinstance(getattr(snapshot, "proxy", None), dict) else {"mode": "direct"}
            resolved_proxy = ProxyResolver(access_policy=self._access_policy).resolve(
                proxy_config,
                endpoint_url,
            )
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
                    endpoint_url,
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
            raise OAuthConfigurationError(failure_error_code) from exc
        accepted = allowed_status_codes or frozenset(range(200, 300))
        if response.status_code not in accepted:
            raise OAuthConfigurationError(failure_error_code)
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise OAuthConfigurationError(response_error_code) from exc
        if not isinstance(payload, Mapping):
            raise OAuthConfigurationError(response_error_code)
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
