from __future__ import annotations

import ctypes
from multiprocessing import get_context
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

from .proxy import ProxyConfigurationError, ResolvedProxy, _validate_pac_url_shape


class WindowsProxyResolverWorker:
    """Resolve WinHTTP/system/PAC proxy settings in a terminable child process."""

    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("proxy worker timeout must be greater than zero")
        self._timeout_seconds = float(timeout_seconds)

    def resolve(
        self,
        target_url: str,
        *,
        mode: str,
        pac_url: str | None = None,
    ) -> ResolvedProxy:
        context = get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(
            target=_resolve_proxy_in_worker,
            args=(child, target_url, mode, pac_url),
            daemon=True,
        )
        process.start()
        child.close()
        try:
            if not parent.poll(self._timeout_seconds):
                process.terminate()
                process.join(timeout=1)
                raise ProxyConfigurationError("proxy resolution failed: worker timeout")
            payload = parent.recv()
        finally:
            parent.close()
            if process.is_alive():
                process.join(timeout=1)
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            message = payload.get("message") if isinstance(payload, dict) else None
            raise ProxyConfigurationError(
                f"proxy resolution failed: {message or 'worker error'}"
            )
        proxy = payload.get("proxy")
        if not isinstance(proxy, ResolvedProxy):
            raise ProxyConfigurationError("proxy resolution failed: invalid worker result")
        return proxy


def _resolve_proxy_in_worker(connection, target_url: str, mode: str, pac_url: str | None) -> None:
    try:
        connection.send(
            {
                "status": "ok",
                "proxy": _resolve_with_winhttp(target_url, mode=mode, pac_url=pac_url),
            }
        )
    except BaseException as exc:
        connection.send({"status": "error", "message": str(exc)})
    finally:
        connection.close()


def _resolve_with_winhttp(
    target_url: str,
    *,
    mode: str,
    pac_url: str | None,
) -> ResolvedProxy:
    if sys.platform != "win32":
        raise ProxyConfigurationError("WinHTTP proxy resolution is only available on Windows")
    parsed_target = urlsplit(target_url)
    if parsed_target.scheme not in {"http", "https"} or not parsed_target.hostname:
        raise ProxyConfigurationError("proxy resolution failed: target URL is invalid")

    from ctypes import wintypes

    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL
    HINTERNET = wintypes.HANDLE
    LPVOID = ctypes.c_void_p

    class CurrentUserProxyConfig(ctypes.Structure):
        _fields_ = [
            ("fAutoDetect", BOOL),
            ("lpszAutoConfigUrl", LPVOID),
            ("lpszProxy", LPVOID),
            ("lpszProxyBypass", LPVOID),
        ]

    class AutoProxyOptions(ctypes.Structure):
        _fields_ = [
            ("dwFlags", DWORD),
            ("dwAutoDetectFlags", DWORD),
            ("lpszAutoConfigUrl", wintypes.LPWSTR),
            ("lpvReserved", wintypes.LPVOID),
            ("dwReserved", DWORD),
            ("fAutoLogonIfChallenged", BOOL),
        ]

    class ProxyInfo(ctypes.Structure):
        _fields_ = [
            ("dwAccessType", DWORD),
            ("lpszProxy", LPVOID),
            ("lpszProxyBypass", LPVOID),
        ]

    winhttp = ctypes.WinDLL("winhttp")
    winhttp.WinHttpOpen.argtypes = [wintypes.LPCWSTR, DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD]
    winhttp.WinHttpOpen.restype = HINTERNET
    winhttp.WinHttpCloseHandle.argtypes = [HINTERNET]
    winhttp.WinHttpCloseHandle.restype = BOOL
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.argtypes = [ctypes.POINTER(CurrentUserProxyConfig)]
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.restype = BOOL
    winhttp.WinHttpGetProxyForUrl.argtypes = [
        HINTERNET,
        wintypes.LPCWSTR,
        ctypes.POINTER(AutoProxyOptions),
        ctypes.POINTER(ProxyInfo),
    ]
    winhttp.WinHttpGetProxyForUrl.restype = BOOL
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    config = CurrentUserProxyConfig()
    if not winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(config)):
        raise ProxyConfigurationError("proxy resolution failed: WinHTTP user config unavailable")

    handle = winhttp.WinHttpOpen("WeConduct/0.9", 1, None, None, 0)
    if not handle:
        raise ProxyConfigurationError("proxy resolution failed: WinHttpOpen")

    allocated: list[Any] = [
        config.lpszAutoConfigUrl,
        config.lpszProxy,
        config.lpszProxyBypass,
    ]
    try:
        normalized_mode = mode.strip().lower()
        if normalized_mode == "windows_system" and config.lpszProxy:
            return _parse_winhttp_proxy_list(
                _read_winhttp_wide_string(config.lpszProxy),
                target_url,
                source=normalized_mode,
            )

        options = AutoProxyOptions()
        if normalized_mode == "pac":
            requested_pac_url = pac_url or _read_winhttp_wide_string(
                config.lpszAutoConfigUrl
            )
            if not requested_pac_url:
                raise ProxyConfigurationError("proxy resolution failed: PAC URL unavailable")
            requested_pac_url = _validate_pac_url_shape(requested_pac_url)
            _configure_winhttp_auto_proxy_options(
                options,
                mode=normalized_mode,
                pac_url=requested_pac_url,
            )
        else:
            _configure_winhttp_auto_proxy_options(options, mode=normalized_mode, pac_url=None)
        info = ProxyInfo()
        if not winhttp.WinHttpGetProxyForUrl(handle, target_url, ctypes.byref(options), ctypes.byref(info)):
            raise ProxyConfigurationError("proxy resolution failed: WinHttpGetProxyForUrl")
        allocated.extend([info.lpszProxy, info.lpszProxyBypass])
        if not info.lpszProxy:
            # WinHTTP reports PAC/WPAD's explicit DIRECT result as
            # WINHTTP_ACCESS_TYPE_NO_PROXY (1) with a null proxy string.
            if info.dwAccessType == 1 and normalized_mode in {"pac", "wpad"}:
                return ResolvedProxy(mode="direct", source=normalized_mode)
            raise ProxyConfigurationError("proxy resolution failed: WinHTTP returned no proxy")
        return _parse_winhttp_proxy_list(
            _read_winhttp_wide_string(info.lpszProxy),
            target_url,
            source=normalized_mode,
        )
    finally:
        for pointer in allocated:
            if pointer:
                try:
                    kernel32.GlobalFree(pointer)
                except BaseException:
                    pass
        winhttp.WinHttpCloseHandle(handle)


def _read_winhttp_wide_string(pointer: int | None) -> str:
    """复制 WinHTTP 所有的宽字符串，保留原始指针供 GlobalFree 释放。"""
    if not pointer:
        return ""
    return str(ctypes.wstring_at(pointer))


def _parse_winhttp_proxy_list(raw_value: str, target_url: str, *, source: str) -> ResolvedProxy:
    parsed_target = urlsplit(target_url)
    target_scheme = parsed_target.scheme.lower()
    candidates = [item.strip() for item in raw_value.split(";") if item.strip()]
    for candidate in candidates:
        if candidate.upper() == "DIRECT":
            return ResolvedProxy(mode="direct", source=source)
        if "=" in candidate:
            scheme, candidate = candidate.split("=", 1)
            if scheme.strip().lower() not in {target_scheme, "http", "https"}:
                continue
        candidate = candidate.strip()
        if "://" not in candidate:
            candidate = f"http://{candidate}"
        parsed = urlsplit(candidate)
        if (
            parsed.scheme not in {"http", "https", "socks5", "socks5h"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            continue
        try:
            port = parsed.port
        except ValueError:
            continue
        if port is None or port <= 0 or port > 65535:
            continue
        mode = parsed.scheme if parsed.scheme.startswith("socks") else "http"
        return ResolvedProxy(mode=mode, url=candidate, source=source)
    raise ProxyConfigurationError("proxy resolution failed: WinHTTP result has no supported candidate")


def _configure_winhttp_auto_proxy_options(options, *, mode: str, pac_url: str | None) -> None:
    """填充 WinHTTP 自动代理选项；绝不自动回应代理身份挑战。"""
    if mode == "pac":
        options.dwFlags = 0x2  # WINHTTP_AUTOPROXY_CONFIG_URL
        options.lpszAutoConfigUrl = pac_url
    elif mode == "wpad":
        options.dwFlags = 0x1  # WINHTTP_AUTOPROXY_AUTO_DETECT
        options.dwAutoDetectFlags = 0x3  # DHCP | DNS_A
    options.fAutoLogonIfChallenged = False
