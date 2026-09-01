from __future__ import annotations

import base64
import hashlib
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Iterator
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

import pytest

from weconduct.application.sensitive_values.models import SensitiveConsumer
from weconduct.application.sensitive_values.service import SensitiveValueService
from weconduct.network_runtime.oauth import (
    OAuthConfigurationError,
    OAuthService,
)
from weconduct.network_runtime.access_policy import NetworkAccessPolicy


@contextmanager
def _live_oauth_provider() -> Iterator[tuple[str, dict[str, object]]]:
    provider_state: dict[str, object] = {
        "requests": [],
        "authorization_challenge": None,
        "device_poll_count": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def _record(self, path: str, values: dict[str, str]) -> None:
            records = provider_state["requests"]
            assert isinstance(records, list)
            records.append({"path": path, "values": values})

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler hook
            parsed = urlsplit(self.path)
            if parsed.path != "/authorize":
                self._send_json(404, {"error": "not_found"})
                return
            values = {
                key: value[0]
                for key, value in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            self._record(parsed.path, values)
            provider_state["authorization_challenge"] = values.get("code_challenge")
            callback = values["redirect_uri"]
            location = f"{callback}?{urlencode({'code': 'live-auth-code', 'state': values['state'], 'nonce': values['nonce']})}"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler hook
            length = int(self.headers.get("Content-Length", "0"))
            values = {
                key: value[0]
                for key, value in parse_qs(
                    self.rfile.read(length).decode("utf-8"), keep_blank_values=True
                ).items()
            }
            parsed = urlsplit(self.path)
            self._record(parsed.path, values)
            if parsed.path == "/device":
                self._send_json(
                    200,
                    {
                        "device_code": "live-device-code",
                        "user_code": "LIVE-1234",
                        "verification_uri": f"http://127.0.0.1:{self.server.server_port}/verify",
                        "expires_in": 60,
                        "interval": 0.01,
                    },
                )
                return
            if parsed.path != "/token":
                self._send_json(404, {"error": "not_found"})
                return
            if values.get("grant_type") == "authorization_code":
                verifier = values.get("code_verifier", "")
                challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode("ascii")).digest()
                ).rstrip(b"=").decode("ascii")
                if values.get("code") != "live-auth-code" or challenge != provider_state["authorization_challenge"]:
                    self._send_json(400, {"error": "invalid_grant"})
                    return
                self._send_json(
                    200,
                    {
                        "access_token": "live-pkce-access",
                        "refresh_token": "live-pkce-refresh",
                        "token_type": "Bearer",
                        "expires_in": 60,
                    },
                )
                return
            if values.get("grant_type") == "urn:ietf:params:oauth:grant-type:device_code":
                poll_count = int(provider_state["device_poll_count"]) + 1
                provider_state["device_poll_count"] = poll_count
                if poll_count == 1:
                    self._send_json(400, {"error": "authorization_pending"})
                    return
                if values.get("device_code") != "live-device-code":
                    self._send_json(400, {"error": "invalid_grant"})
                    return
                self._send_json(
                    200,
                    {"access_token": "live-device-access", "token_type": "Bearer", "expires_in": 60},
                )
                return
            self._send_json(400, {"error": "unsupported_grant_type"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", provider_state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _service() -> OAuthService:
    return OAuthService(sensitive_values=object())  # type: ignore[arg-type]


def _network_service(handler):
    sensitive = SensitiveValueService()
    service = OAuthService(
        sensitive_values=sensitive,
        transport=httpx.MockTransport(handler),
        access_policy=NetworkAccessPolicy(allowed_hostnames={"example.test"}),
    )
    return service, sensitive


def test_authorization_code_pkce_generates_s256_and_validates_state_and_nonce() -> None:
    request = _service().begin_authorization_code_pkce(
        authorization_url="https://example.test/authorize",
        client_id="client",
        redirect_uri="http://127.0.0.1/callback",
        scope="openid",
    )

    expected = base64.urlsafe_b64encode(
        hashlib.sha256(request.code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert request.code_challenge == expected
    assert _service().validate_authorization_callback(request, state=request.state, code="auth-code", nonce=request.nonce) == "auth-code"


def test_authorization_code_pkce_rejects_callback_mismatch_and_consumes_verifier() -> None:
    service = _service()
    request = service.begin_authorization_code_pkce(
        authorization_url="https://example.test/authorize",
        client_id="client",
        redirect_uri="http://127.0.0.1/callback",
    )

    with pytest.raises(OAuthConfigurationError, match="oauth.authorization_state_mismatch"):
        service.validate_authorization_callback(request, state="wrong", code="auth-code", nonce=request.nonce)
    assert "auth-code" not in repr(request)
    assert request.code_verifier not in repr(request)

    assert service.validate_authorization_callback(
        request, state=request.state, code="auth-code", nonce=request.nonce
    ) == "auth-code"
    with pytest.raises(OAuthConfigurationError, match="oauth.authorization_callback_replayed"):
        service.validate_authorization_callback(
            request, state=request.state, code="auth-code", nonce=request.nonce
        )


def test_device_code_polling_honors_interval_timeout_and_pending_status() -> None:
    service = _service()
    device = service.create_device_code_state(
        device_code="device-secret",
        user_code="ABCD",
        verification_uri="https://example.test/device",
        expires_in=10,
        interval=2,
    )
    responses = iter(
        [
            {"error": "authorization_pending"},
            {"access_token": "token", "token_type": "Bearer"},
        ]
    )
    sleeps: list[float] = []
    now = [0.0]

    result = service.poll_device_code(
        device,
        poll_token=lambda _: next(responses),
        sleep=lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds)),
        monotonic=lambda: now[0],
    )

    assert result["access_token"] == "token"
    assert sleeps == [2]
    assert "device-secret" not in repr(device)
    assert "device-secret" not in repr(result)


def test_device_code_polling_supports_cancel_and_expiry() -> None:
    service = _service()
    cancelled = Event()
    device = service.create_device_code_state(
        device_code="device-secret",
        user_code="ABCD",
        verification_uri="https://example.test/device",
        expires_in=10,
    )

    with pytest.raises(OAuthConfigurationError, match="oauth.device_code_cancelled"):
        service.poll_device_code(
            device,
            poll_token=lambda _: cancelled.set() or {"error": "authorization_pending"},
            sleep=lambda _: None,
            is_cancelled=cancelled.is_set,
        )


def test_authorization_code_pkce_exchanges_code_and_clears_verifier() -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(
            {
                "url": str(request.url),
                **{key: value[0] for key, value in parse_qs(request.content.decode()).items()},
            }
        )
        return httpx.Response(
            200,
            json={"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 60},
            request=request,
        )

    service, sensitive = _network_service(handler)
    request = service.begin_authorization_code_pkce(
        authorization_url="https://example.test/authorize",
        client_id="client",
        redirect_uri="http://127.0.0.1/callback",
        scope="openid",
    )
    verifier = request.code_verifier

    state = service.exchange_authorization_code_pkce(
        request=request,
        token_url="https://example.test/token",
        state=request.state,
        code="authorization-code",
        nonce=request.nonce,
        scope_id="oauth-session",
    )

    assert observed["grant_type"] == "authorization_code"
    assert observed["client_id"] == "client"
    assert observed["redirect_uri"] == "http://127.0.0.1/callback"
    assert observed["code"] == "authorization-code"
    assert observed["code_verifier"] == verifier
    assert state.refresh_token is not None
    assert sensitive.resolve(state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "access-secret"
    assert request.code_verifier == ""


def test_device_code_exchange_requests_device_code_and_polls_token_endpoint() -> None:
    calls: list[dict[str, str]] = []
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        values = {key: value[0] for key, value in parse_qs(request.content.decode()).items()}
        calls.append(values)
        if request.url.path.endswith("/device"):
            return httpx.Response(
                200,
                json={
                    "device_code": "device-secret",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://example.test/verify",
                    "expires_in": 60,
                    "interval": 1,
                },
                request=request,
            )
        poll_count += 1
        if poll_count == 1:
            return httpx.Response(400, json={"error": "authorization_pending"}, request=request)
        return httpx.Response(
            200,
            json={"access_token": "device-access-secret", "token_type": "Bearer"},
            request=request,
        )

    service, sensitive = _network_service(handler)
    device = service.request_device_code(
        device_authorization_url="https://example.test/device",
        client_id="device-client",
        scope="openid",
    )
    state = service.exchange_device_code(
        device=device,
        token_url="https://example.test/token",
        client_id="device-client",
        scope_id="oauth-device-session",
        sleep=lambda _: None,
    )

    assert calls[0] == {"client_id": "device-client", "scope": "openid"}
    assert calls[1]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert calls[1]["device_code"] == "device-secret"
    assert calls[2]["device_code"] == "device-secret"
    assert sensitive.resolve(state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "device-access-secret"


def test_authorization_code_pkce_round_trips_through_live_http_provider() -> None:
    with _live_oauth_provider() as (base_url, provider_state):
        sensitive = SensitiveValueService()
        service = OAuthService(
            sensitive_values=sensitive,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        request = service.begin_authorization_code_pkce(
            authorization_url=f"{base_url}/authorize",
            client_id="fixture-client",
            redirect_uri="http://127.0.0.1/callback",
            scope="openid",
        )

        with httpx.Client(follow_redirects=False, trust_env=False) as client:
            authorization_response = client.get(request.authorization_url)

        assert authorization_response.status_code == 302
        callback = urlsplit(authorization_response.headers["location"])
        assert callback.path == "/callback"
        callback_values = {
            key: value[0]
            for key, value in parse_qs(callback.query, keep_blank_values=True).items()
        }
        token_state = service.exchange_authorization_code_pkce(
            request=request,
            token_url=f"{base_url}/token",
            state=callback_values["state"],
            code=callback_values["code"],
            nonce=callback_values["nonce"],
            scope_id="live-pkce-session",
        )

        assert sensitive.resolve(token_state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "live-pkce-access"
        assert request.code_verifier == ""
        assert provider_state["authorization_challenge"]
        requests = provider_state["requests"]
        assert isinstance(requests, list)
        assert [record["path"] for record in requests] == ["/authorize", "/token"]
        authorization_values = requests[0]["values"]
        token_values = requests[1]["values"]
        assert authorization_values["response_type"] == "code"
        assert authorization_values["code_challenge_method"] == "S256"
        assert authorization_values["scope"] == "openid"
        assert token_values["grant_type"] == "authorization_code"
        assert token_values["code"] == "live-auth-code"
        assert token_values["code_verifier"]


def test_device_code_round_trips_through_live_http_provider() -> None:
    with _live_oauth_provider() as (base_url, provider_state):
        sensitive = SensitiveValueService()
        service = OAuthService(
            sensitive_values=sensitive,
            access_policy=NetworkAccessPolicy(allow_loopback=True),
        )
        device = service.request_device_code(
            device_authorization_url=f"{base_url}/device",
            client_id="fixture-client",
            scope="openid",
        )
        token_state = service.exchange_device_code(
            device=device,
            token_url=f"{base_url}/token",
            client_id="fixture-client",
            scope_id="live-device-session",
            sleep=lambda _: None,
        )

        assert device.user_code == "LIVE-1234"
        assert sensitive.resolve(token_state.access_token, consumer=SensitiveConsumer.NETWORK_RUNTIME) == "live-device-access"
        assert provider_state["device_poll_count"] == 2
        requests = provider_state["requests"]
        assert isinstance(requests, list)
        assert [record["path"] for record in requests] == ["/device", "/token", "/token"]
        assert requests[0]["values"] == {"client_id": "fixture-client", "scope": "openid"}
        assert all(
            record["values"]["grant_type"]
            == "urn:ietf:params:oauth:grant-type:device_code"
            for record in requests[1:]
        )
        assert all(record["values"]["device_code"] == "live-device-code" for record in requests[1:])
