from __future__ import annotations

import pytest

from weconduct.network_runtime.proxy import ProxyConfigurationError, ProxyResolver


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
