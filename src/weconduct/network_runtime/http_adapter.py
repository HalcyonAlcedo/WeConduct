from __future__ import annotations

import asyncio
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from time import perf_counter
from urllib.parse import urljoin

import httpx

from .access_policy import NetworkAccessPolicy
from .models import NetworkContextSnapshot, NetworkOperation, NetworkResult
from .resources import ResponseBodyStore
from .proxy import ProxyResolver
from .tls import TlsResolver


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
        self._client = client or httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )
        self._owns_client = client is None
        self._response_root_directory = Path(response_root_directory)
        self._access_policy = access_policy or NetworkAccessPolicy()
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
            headers = {**snapshot.headers, **operation.headers}
            query = {
                **dict(httpx.URL(operation.url).params),
                **snapshot.query,
                **operation.query,
            }
            content = operation.content
            if operation.upload_file_path is not None:
                content = _iter_upload_file_chunks(operation.upload_file_path)
            request_url = operation.url
            client = self._client_for_snapshot(snapshot, request_url)
            for _ in range(10):
                self._access_policy.validate_url(request_url)
                async with client.stream(
                    operation.method,
                    request_url,
                    headers=headers,
                    params=query,
                    cookies=snapshot.cookies,
                    content=content,
                    timeout=operation.timeout_seconds,
                ) as response:
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
                return NetworkResult(
                    status="failed",
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    transport_error="network.too_many_redirects",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
        except asyncio.CancelledError:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error="network.cancelled",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return NetworkResult(
                status="failed",
                operation_id=operation.operation_id,
                session_id=operation.session_id,
                transport_error=str(exc),
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
    ) -> httpx.AsyncClient:
        tls_config = snapshot.tls if isinstance(snapshot.tls, dict) else {}
        resolved = TlsResolver().resolve(tls_config)
        verify_argument: str | bool = True if resolved.verify == "system" else resolved.verify
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
            verify_argument,
            resolved.client_cert,
            resolved.certificate_pins,
            resolved_proxy.mode,
            resolved_proxy.url,
        )
        cached = self._tls_clients.get(key)
        if cached is not None:
            return cached
        client = httpx.AsyncClient(
            transport=self._transport,
            verify=verify_argument,
            cert=resolved.client_cert,
            proxy=resolved_proxy.url,
            trust_env=False,
            follow_redirects=False,
        )
        self._tls_clients[key] = client
        return client

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
