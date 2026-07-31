from __future__ import annotations

from importlib import import_module as _import_module
from typing import Callable


_NETWORK_DEPENDENCIES = (
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
)


def build_runtime_capabilities(
    *,
    import_module: Callable[[str], object] = _import_module,
) -> dict[str, object]:
    """Report capabilities only after their runtime dependencies can be imported."""
    dependencies: dict[str, dict[str, object]] = {}
    missing_dependencies: list[str] = []
    for dependency in _NETWORK_DEPENDENCIES:
        try:
            import_module(dependency)
        except Exception:  # noqa: BLE001 - optional bundled dependency probe
            dependencies[dependency] = {"available": False, "reason": "import_failed"}
            missing_dependencies.append(dependency)
        else:
            dependencies[dependency] = {"available": True}

    available = lambda name: dependencies[name]["available"] is True
    protocols = {
        "http1": available("httpx"),
        "http2": available("httpx") and available("h2"),
        "sse": available("httpx") and available("httpx_sse"),
        "websocket": available("websockets"),
        "graphql": available("httpx") and available("graphql"),
        # 0.9.0 仅支持 GraphQL Query/Mutation；订阅需要方案 C 的统一连接内核。
        "graphql_subscription": False,
        "oauth_client_credentials": available("httpx") and available("authlib"),
        "oauth_refresh": available("httpx") and available("authlib"),
        "http_proxy": available("httpx"),
        "socks_proxy": available("httpx") and available("socksio") and available("python_socks"),
    }

    return {
        "compiler_available": True,
        "graph_workspace_available": True,
        "runtime_available": True,
        "debug_available": True,
        "network": {
            "available": not missing_dependencies,
            "dependencies": dependencies,
            "missing_dependencies": missing_dependencies,
            "protocols": protocols,
        },
        "sensitive_input": {"available": available("cryptography")},
        "external_api_v1": {"available": True, "default_enabled": False},
        "python_run": {"available": True, "dynamic_schema": True},
        "plugins": {"available": False, "planned_version": "0.9.1"},
    }
