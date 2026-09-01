from __future__ import annotations

from weconduct.application.runtime_capabilities import build_runtime_capabilities


def test_runtime_capabilities_report_the_090_network_execution_surface() -> None:
    capabilities = build_runtime_capabilities()

    network = capabilities["network"]

    assert network["available"] is True
    assert network["protocols"] == {
        "http1": True,
        "http2": True,
        "sse": True,
        "websocket": True,
        "graphql": True,
        "graphql_subscription": True,
        "oauth_client_credentials": True,
        "oauth_refresh": True,
        "http_proxy": True,
        "socks_proxy": True,
    }
    assert set(network["dependencies"]) == {
        "httpx",
        "h2",
        "httpx_sse",
        "websockets",
        "graphql",
        "authlib",
        "cryptography",
        "msgpack",
        "socksio",
        "python_socks",
    }
    assert all(item["available"] is True for item in network["dependencies"].values())
    assert capabilities["sensitive_input"]["available"] is True
    assert capabilities["external_api_v1"] == {
        "available": True,
        "default_enabled": False,
    }
    assert capabilities["python_run"]["available"] is True
    assert capabilities["plugins"] == {
        "available": False,
        "planned": False,
    }


def test_runtime_capabilities_disable_only_the_dependent_protocols_when_an_import_fails() -> None:
    imported: list[str] = []

    def import_module(name: str) -> object:
        imported.append(name)
        if name == "websockets":
            raise ImportError("simulated missing websockets")
        return object()

    capabilities = build_runtime_capabilities(import_module=import_module)

    network = capabilities["network"]

    assert network["available"] is False
    assert network["missing_dependencies"] == ["websockets"]
    assert network["protocols"]["websocket"] is False
    assert network["protocols"]["graphql_subscription"] is False
    assert network["protocols"]["http1"] is True
    assert network["protocols"]["http2"] is True
    assert imported == [
        "httpx",
        "h2",
        "httpx_sse",
        "websockets",
        "graphql",
        "authlib",
        "cryptography",
        "msgpack",
        "socksio",
        "python_socks",
    ]
