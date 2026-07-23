from __future__ import annotations

import importlib.util

import httpx


def test_090_network_runtime_dependencies_are_importable() -> None:
    required_modules = (
        "httpx_sse",
        "websockets",
        "graphql",
        "authlib",
        "cryptography",
        "msgpack",
        "socksio",
        "python_socks",
    )

    missing = [module for module in required_modules if importlib.util.find_spec(module) is None]

    assert missing == []


def test_090_httpx_client_disables_implicit_environment_proxy_discovery() -> None:
    client = httpx.AsyncClient(http2=True, trust_env=False)

    try:
        assert client._trust_env is False
    finally:
        import asyncio

        asyncio.run(client.aclose())
