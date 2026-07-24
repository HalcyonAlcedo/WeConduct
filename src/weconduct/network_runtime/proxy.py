from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Mapping
from urllib.parse import urlsplit


class ProxyConfigurationError(ValueError):
    """Raised when proxy configuration cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedProxy:
    mode: str
    url: str | None = field(default=None, repr=False)
    source: str = "explicit"


class ProxyResolver:
    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        source = os.environ if environment is None else environment
        self._environment = {str(key).upper(): str(value) for key, value in source.items()}

    def resolve(self, configuration: Mapping[str, object], target_url: str) -> ResolvedProxy:
        if not isinstance(configuration, Mapping):
            raise ProxyConfigurationError("proxy configuration is invalid: expected an object")
        mode = configuration.get("mode")
        if not isinstance(mode, str) or not mode.strip():
            raise ProxyConfigurationError("proxy configuration is invalid: mode is required")
        normalized_mode = mode.strip().lower()
        if normalized_mode == "direct":
            return ResolvedProxy(mode="direct", source="direct")
        if normalized_mode == "manual":
            raw_url = configuration.get("url")
            if not isinstance(raw_url, str) or not raw_url.strip():
                raise ProxyConfigurationError("proxy configuration is invalid: manual url is required")
            return self._parse_proxy_url(raw_url.strip(), source="manual")
        if normalized_mode == "environment":
            return self._resolve_environment(target_url)
        if normalized_mode in {"windows_system", "pac", "wpad"}:
            raise ProxyConfigurationError(
                f"proxy configuration is not implemented: {normalized_mode}"
            )
        raise ProxyConfigurationError(f"proxy configuration is invalid: unsupported mode {mode!r}")

    def _resolve_environment(self, target_url: str) -> ResolvedProxy:
        parsed = urlsplit(target_url)
        scheme = parsed.scheme.upper()
        candidates = (
            f"{scheme}_PROXY",
            "ALL_PROXY",
        )
        raw_url = next(
            (self._environment.get(name) for name in candidates if self._environment.get(name)),
            None,
        )
        if raw_url is None:
            raise ProxyConfigurationError(
                "proxy configuration is invalid: environment proxy is unavailable"
            )
        return self._parse_proxy_url(raw_url, source="environment")

    @staticmethod
    def _parse_proxy_url(raw_url: str, *, source: str) -> ResolvedProxy:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
            raise ProxyConfigurationError(f"proxy configuration is invalid: unsupported url {raw_url!r}")
        if parsed.port is None or parsed.port <= 0 or parsed.port > 65535:
            raise ProxyConfigurationError(f"proxy configuration is invalid: port is required in {raw_url!r}")
        mode = "http" if parsed.scheme in {"http", "https"} else parsed.scheme
        return ResolvedProxy(mode=mode, url=raw_url, source=source)
