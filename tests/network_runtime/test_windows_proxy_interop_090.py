from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from threading import Thread

import pytest

from weconduct.network_runtime.proxy import ResolvedProxy
from weconduct.network_runtime.windows_proxy_worker import WindowsProxyResolverWorker


@contextmanager
def _local_pac_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = b'function FindProxyForURL(url, host) { return "DIRECT"; }'
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/proxy.pac"
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@contextmanager
def _local_proxy_pac_server(proxy_port: int):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = (
                "function FindProxyForURL(url, host) { "
                f"return 'PROXY 127.0.0.1:{proxy_port}'; "
                "}"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/proxy.pac"
    finally:
        server.shutdown()
        thread.join(timeout=1)
        server.server_close()


@pytest.mark.skipif(sys.platform != "win32", reason="WinHTTP is Windows-only")
def test_windows_worker_resolves_explicit_local_pac_direct_without_system_proxy() -> None:
    with _local_pac_server() as pac_url:
        resolved = WindowsProxyResolverWorker(timeout_seconds=10).resolve(
            "http://example.com/resource",
            mode="pac",
            pac_url=pac_url,
        )

    assert isinstance(resolved, ResolvedProxy)
    assert resolved.mode == "direct"
    assert resolved.url is None
    assert resolved.source == "pac"


@pytest.mark.skipif(sys.platform != "win32", reason="WinHTTP is Windows-only")
def test_windows_worker_resolves_explicit_local_pac_proxy_without_worker_crash() -> None:
    with _local_proxy_pac_server(proxy_port=18080) as pac_url:
        resolved = WindowsProxyResolverWorker(timeout_seconds=5).resolve(
            "http://127.0.0.2:1/resource",
            mode="pac",
            pac_url=pac_url,
        )

    assert isinstance(resolved, ResolvedProxy)
    assert resolved.mode == "http"
    assert resolved.url == "http://127.0.0.1:18080"
    assert resolved.source == "pac"
