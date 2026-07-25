from __future__ import annotations

import asyncio
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
import ssl
from time import perf_counter
from urllib.parse import urljoin

import httpx

from .access_policy import NetworkAccessPolicy
from .authentication import apply_static_auth
from .errors import build_network_error
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .resources import ResponseBodyStore
from .proxy import ProxyResolver
from .tls import ResolvedTls, TlsResolver, verify_response_certificate_pins
from .transport import PinnedDnsAsyncHTTPTransport


class HttpxAdapter:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        response_root_directory: Path,
        access_policy: NetworkAccessPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = transport
        self._access_policy = access_policy or NetworkAccessPolicy()
        self._client = client or self._build_client()
        self._owns_client = client is None
        self._response_root_directory = Path(response_root_directory)
        self._stores: dict[str, ResponseBodyStore] = {}
        self._tls_clients: dict[tuple[object, ...], httpx.AsyncClient] = {}

    def execute(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkResult:
        return asyncio.run(self.execute_async(operation, snapshot))

    async def execute_async(
        self,
        operation: NetworkOperation,
        snapshot: NetworkContextSnapshot,
    ) -> NetworkResult:
        started_at = perf_counter()
        try:
            headers = apply_static_auth(
                {**snapshot.headers, **operation.headers},
                snapshot.auth,
            )
            query = {
                **dict(httpx.URL(operation.url).params),
                **snapshot.query,
                **operation.query,
            }
            content = operation.content
            if operation.upload_stream is not None:
                content = operation.upload_stream
            elif operation.upload_file_path is not None:
                content = _iter_upload_file_chunks(operation.upload_file_path)
            request_url = operation.url
            tls_config = snapshot.tls if isinstance(snapshot.tls, dict) else {}
            resolved_tls = TlsResolver().resolve(tls_config)
            client = self._client_for_snapshot(snapshot, request_url, resolved_tls=resolved_tls)
            for _ in range(10):
                resolved_target = self._access_policy.validate_url(request_url)
                request_extensions = (
                    {"weconduct.resolved_network_target": resolved_target}
                    if resolved_target is not None
                    else None
                )
                async with client.stream(
                    operation.method,
                    request_url,
                    headers=headers,
                    params=query,
                    cookies=snapshot.cookies,
                    content=content,
                    timeout=operation.timeout_seconds,
                    extensions=request_extensions,
                ) as response:
                    verify_response_certificate_pins(response, resolved_tls.certificate_pins)
                    redirect_target = response.headers.get("location")
                    if response.status_code not in {301, 302, 303, 307, 308} or not redirect_target:
                        store = self._stores.setdefault(
                            operation.session_id,
                            ResponseBodyStore(
                                session_id=operation.session_id,
                                root_directory=self._response_root_directory,
                            ),
                        )
                        body_ref = await store.create_from_async_chunks(
                            response.aiter_bytes(),
                            content_type=response.headers.get("content-type"),
                            force_file=operation.response_storage == "file",
                        )
                        break
                    request_url = urljoin(request_url, redirect_target)
            else:
                error = build_network_error(
                    "network.too_many_redirects",
                    operation=operation,
                    snapshot=snapshot,
                )
                return NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error=error.error_code,
                    error=error,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
        except asyncio.CancelledError:
            error = build_network_error(
                "network.cancelled",
                operation=operation,
                snapshot=snapshot,
            )
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=error.error_code,
                error=error,
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        except (httpx.HTTPError, ValueError) as exc:
            error = build_network_error(exc, operation=operation, snapshot=snapshot)
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=error.error_code,
                error=error,
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        return NetworkResult(
            status="succeeded",
            operation_id=operation.operation_id,
            session_id=operation.session_id,
            status_code=response.status_code,
            headers=dict(response.headers),
            body_ref=body_ref,
            final_url=str(response.url),
            set_cookies=_parse_set_cookie_headers(response.headers),
            duration_ms=(perf_counter() - started_at) * 1000,
        )

    def close_session(self, session_id: str) -> None:
        store = self._stores.pop(session_id, None)
        if store is not None:
            store.close()

    def close(self) -> None:
        for session_id in list(self._stores):
            self.close_session(session_id)

    def _client_for_snapshot(
        self,
        snapshot: NetworkContextSnapshot,
        target_url: str = "https://example.invalid/",
        *,
        resolved_tls: ResolvedTls | None = None,
    ) -> httpx.AsyncClient:
        resolved = resolved_tls
        if resolved is None:
            tls_config = snapshot.tls if isinstance(snapshot.tls, dict) else {}
            resolved = TlsResolver().resolve(tls_config)
        verify_argument: ssl.SSLContext | bool
        if resolved.verify == "system":
            verify_argument = True
        elif resolved.verify is False:
            verify_argument = False
        else:
            verify_argument = ssl.create_default_context(cafile=resolved.verify)
        if resolved.client_cert is not None:
            if isinstance(verify_argument, ssl.SSLContext):
                client_context = verify_argument
            elif verify_argument is False:
                client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                client_context.check_hostname = False
                client_context.verify_mode = ssl.CERT_NONE
            else:
                client_context = ssl.create_default_context()
            client_context.load_cert_chain(*resolved.client_cert)
            verify_argument = client_context
        proxy_config = snapshot.proxy if isinstance(snapshot.proxy, dict) else {"mode": "direct"}
        resolved_proxy = ProxyResolver().resolve(proxy_config, target_url)
        if (
            resolved.verify == "system"
            and resolved.client_cert is None
            and resolved_proxy.mode == "direct"
        ):
            return self._client
        key = (
            resolved.verify,
            resolved.client_cert,
            resolved.certificate_pins,
            resolved_proxy.mode,
            resolved_proxy.url,
        )
        cached = self._tls_clients.get(key)
        if cached is not None:
            return cached
        client = self._build_client(verify=verify_argument, proxy=resolved_proxy.url)
        self._tls_clients[key] = client
        return client

    def _build_client(
        self,
        *,
        verify: ssl.SSLContext | bool = True,
        proxy: str | None = None,
    ) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport,
                verify=verify,
                proxy=proxy,
                trust_env=False,
                follow_redirects=False,
                http2=True,
            )
        return httpx.AsyncClient(
            transport=PinnedDnsAsyncHTTPTransport(
                access_policy=self._access_policy,
                verify=verify,
                proxy=proxy,
                trust_env=False,
                http2=True,
            ),
            trust_env=False,
            follow_redirects=False,
            http2=True,
        )

    async def aclose(self) -> None:
        self.close()
        for client in tuple(self._tls_clients.values()):
            await client.aclose()
        self._tls_clients.clear()
        if self._owns_client:
            await self._client.aclose()


async def _iter_upload_file_chunks(path: Path, *, chunk_size: int = 64 * 1024):
    with Path(path).open("rb") as handle:
        while chunk := await asyncio.to_thread(handle.read, chunk_size):
            yield chunk


def _parse_set_cookie_headers(headers: httpx.Headers) -> dict[str, str | None]:
    changes: dict[str, str | None] = {}
    for raw_header in headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        try:
            parsed.load(raw_header)
        except (CookieError, ValueError):
            continue
        for name, morsel in parsed.items():
            max_age = morsel["max-age"].strip().lower()
            changes[name] = None if max_age == "0" else morsel.value
    return changes
