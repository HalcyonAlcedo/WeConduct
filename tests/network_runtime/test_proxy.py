from __future__ import annotations

import pytest

from weconduct.network_runtime.proxy import ProxyConfigurationError, ProxyResolver, ResolvedProxy
from weconduct.network_runtime.windows_proxy_worker import _parse_winhttp_proxy_list


def test_proxy_resolver_returns_explicit_direct_mode() -> None:
    resolved = ProxyResolver().resolve({"mode": "direct"}, "https://example.test/api")

    assert resolved.mode == "direct"
    assert resolved.url is None


def test_proxy_resolver_parses_manual_http_and_socks5h_without_direct_fallback() -> None:
    resolver = ProxyResolver()

    http_proxy = resolver.resolve(
        {"mode": "manual", "url": "http://proxy.example.test:8080"},
        "https://example.test/api",
    )
    socks_proxy = resolver.resolve(
        {"mode": "manual", "url": "socks5h://proxy.example.test:1080"},
        "https://example.test/api",
    )

    assert http_proxy.mode == "http"
    assert http_proxy.url == "http://proxy.example.test:8080"
    assert socks_proxy.mode == "socks5h"
    assert socks_proxy.url == "socks5h://proxy.example.test:1080"


def test_proxy_resolver_requires_a_supported_proxy_url_for_manual_mode() -> None:
    with pytest.raises(ProxyConfigurationError, match="proxy configuration is invalid"):
        ProxyResolver().resolve(
            {"mode": "manual", "url": "ftp://proxy.example.test:21"},
            "https://example.test/api",
        )


def test_proxy_resolver_uses_explicit_environment_mapping_only() -> None:
    resolver = ProxyResolver(environment={"HTTPS_PROXY": "http://proxy.example.test:3128"})

    resolved = resolver.resolve({"mode": "environment"}, "https://example.test/api")

    assert resolved.mode == "http"
    assert resolved.url == "http://proxy.example.test:3128"


def test_proxy_resolver_delegates_windows_system_and_pac_modes_to_isolated_worker() -> None:
    class FakeWindowsWorker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        def resolve(self, target_url: str, *, mode: str, pac_url: str | None = None) -> ResolvedProxy:
            self.calls.append((target_url, mode, pac_url))
            return ResolvedProxy(mode="http", url="http://proxy.example.test:8080", source=mode)

    worker = FakeWindowsWorker()
    resolver = ProxyResolver(windows_worker=worker)

    windows = resolver.resolve(
        {"mode": "windows_system"},
        "https://example.test/resource",
    )
    pac = resolver.resolve(
        {"mode": "pac", "pac_url": "https://proxy.example.test/proxy.pac"},
        "https://example.test/resource",
    )

    assert windows.mode == "http"
    assert pac.mode == "http"
    assert worker.calls == [
        ("https://example.test/resource", "windows_system", None),
        ("https://example.test/resource", "pac", "https://proxy.example.test/proxy.pac"),
    ]


def test_proxy_resolver_rejects_worker_failure_without_direct_fallback() -> None:
    class FailingWorker:
        def resolve(self, target_url: str, *, mode: str, pac_url: str | None = None) -> ResolvedProxy:
            raise RuntimeError("worker unavailable")

    resolver = ProxyResolver(windows_worker=FailingWorker())

    with pytest.raises(ProxyConfigurationError, match="proxy resolution failed"):
        resolver.resolve({"mode": "wpad"}, "https://example.test/resource")


def test_winhttp_proxy_list_preserves_order_and_only_allows_explicit_direct() -> None:
    resolved = _parse_winhttp_proxy_list(
        "https=proxy.example.test:8443;DIRECT",
        "https://example.test/resource",
        source="pac",
    )
    assert resolved.mode == "http"
    assert resolved.url == "http://proxy.example.test:8443"

    direct = _parse_winhttp_proxy_list(
        "DIRECT",
        "https://example.test/resource",
        source="pac",
    )
    assert direct.mode == "direct"
    assert direct.url is None
