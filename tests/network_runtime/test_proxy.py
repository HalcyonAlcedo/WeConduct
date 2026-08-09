from __future__ import annotations

import pytest

from weconduct.network_runtime.access_policy import NetworkAccessPolicy
from weconduct.network_runtime.proxy import ProxyConfigurationError, ProxyResolver, ResolvedProxy
from weconduct.network_runtime.windows_proxy_worker import (
    _configure_winhttp_auto_proxy_options,
    _parse_winhttp_proxy_list,
)


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


def test_proxy_resolver_does_not_include_credentials_in_validation_errors() -> None:
    with pytest.raises(ProxyConfigurationError) as exc_info:
        ProxyResolver().resolve(
            {"mode": "manual", "url": "ftp://proxy-user:proxy-secret@proxy.example.test:21"},
            "https://example.test/api",
        )

    assert "proxy-user" not in str(exc_info.value)
    assert "proxy-secret" not in str(exc_info.value)


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
    resolver = ProxyResolver(
        windows_worker=worker,
        access_policy=NetworkAccessPolicy(
            allowed_hostnames=frozenset({"proxy.example.test"})
        ),
    )

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


@pytest.mark.parametrize(
    "pac_url",
    [
        "file:///C:/Windows/win.ini",
        "//proxy.example.test/proxy.pac",
        "https://user:password@proxy.example.test/proxy.pac",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_proxy_resolver_rejects_unsafe_pac_url_before_starting_worker(pac_url: str) -> None:
    class RecordingWorker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        def resolve(self, target_url: str, *, mode: str, pac_url: str | None = None) -> ResolvedProxy:
            self.calls.append((target_url, mode, pac_url))
            return ResolvedProxy(mode="direct", source=mode)

    worker = RecordingWorker()
    resolver = ProxyResolver(windows_worker=worker)

    with pytest.raises(ProxyConfigurationError, match="PAC URL"):
        resolver.resolve({"mode": "pac", "pac_url": pac_url}, "https://example.test/resource")

    assert worker.calls == []


def test_proxy_resolver_rejects_private_proxy_returned_by_pac() -> None:
    class PrivateProxyWorker:
        def resolve(self, target_url: str, *, mode: str, pac_url: str | None = None) -> ResolvedProxy:
            return ResolvedProxy(mode="http", url="http://127.0.0.1:8080", source=mode)

    resolver = ProxyResolver(
        windows_worker=PrivateProxyWorker(),
        access_policy=NetworkAccessPolicy(allowed_hostnames=frozenset({"pac.example.test"})),
    )

    with pytest.raises(ProxyConfigurationError, match="proxy candidate"):
        resolver.resolve(
            {"mode": "pac", "pac_url": "https://pac.example.test/proxy.pac"},
            "https://example.test/resource",
        )


def test_proxy_resolver_accepts_policy_allowed_proxy_returned_by_pac() -> None:
    class PublicProxyWorker:
        def resolve(self, target_url: str, *, mode: str, pac_url: str | None = None) -> ResolvedProxy:
            return ResolvedProxy(mode="http", url="http://proxy.example.test:8080", source=mode)

    resolver = ProxyResolver(
        windows_worker=PublicProxyWorker(),
        access_policy=NetworkAccessPolicy(
            allowed_hostnames=frozenset({"pac.example.test", "proxy.example.test"})
        ),
    )

    resolved = resolver.resolve(
        {"mode": "pac", "pac_url": "https://pac.example.test/proxy.pac"},
        "https://example.test/resource",
    )

    assert resolved.url == "http://proxy.example.test:8080"


def test_winhttp_auto_proxy_options_never_auto_log_on_to_proxy() -> None:
    class Options:
        dwFlags = 0
        dwAutoDetectFlags = 0
        lpszAutoConfigUrl = None
        fAutoLogonIfChallenged = True

    options = Options()
    _configure_winhttp_auto_proxy_options(
        options,
        mode="wpad",
        pac_url=None,
    )

    assert options.fAutoLogonIfChallenged is False


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


def test_winhttp_proxy_list_rejects_candidate_with_embedded_credentials() -> None:
    with pytest.raises(ProxyConfigurationError, match="no supported candidate"):
        _parse_winhttp_proxy_list(
            "http://proxy-user:proxy-secret@proxy.example.test:8080",
            "https://example.test/resource",
            source="pac",
        )
