from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
from pathlib import Path
import re
import ssl
from typing import Mapping


class TlsConfigurationError(ValueError):
    """Raised when TLS settings violate the network security contract."""


@dataclass(frozen=True)
class ResolvedTls:
    verify: str | bool
    ca_file: str | None = None
    client_cert: tuple[str, str] | None = None
    certificate_pins: tuple[str, ...] = ()
    audit_events: tuple[str, ...] = field(default_factory=tuple)


class TlsResolver:
    def __init__(self, *, allow_insecure: bool = True) -> None:
        self._allow_insecure = allow_insecure

    def resolve(self, configuration: Mapping[str, object] | None) -> ResolvedTls:
        config = configuration if isinstance(configuration, Mapping) else {}
        raw_verify = config.get("verify", "system")
        if not isinstance(raw_verify, str):
            raise TlsConfigurationError("TLS verify mode must be a string")
        verify_mode = raw_verify.strip().lower()
        if verify_mode in {"system", "default"}:
            verify: str | bool = "system"
            ca_file = None
        elif verify_mode in {"custom_ca", "custom-ca"}:
            ca_file = self._require_file(config.get("ca_file"), "custom CA file")
            verify = ca_file
        elif verify_mode in {"insecure", "false"}:
            if not self._allow_insecure:
                raise TlsConfigurationError("insecure TLS is disabled by the security policy")
            verify = False
            ca_file = None
        else:
            raise TlsConfigurationError(f"unsupported TLS verify mode: {raw_verify!r}")

        cert_value = config.get("client_cert_file")
        key_value = config.get("client_key_file")
        if cert_value is None and key_value is None:
            client_cert = None
        elif cert_value is None or key_value is None:
            raise TlsConfigurationError("client certificate and key must be configured together")
        else:
            client_cert = (
                self._require_file(cert_value, "client certificate"),
                self._require_file(key_value, "client key"),
            )

        raw_pins = config.get("certificate_pins", ())
        if not isinstance(raw_pins, (list, tuple)):
            raise TlsConfigurationError("certificate_pins must be a list")
        pins: list[str] = []
        for raw_pin in raw_pins:
            if not isinstance(raw_pin, str):
                raise TlsConfigurationError("certificate pin must be a string")
            pin = raw_pin.strip().lower().removeprefix("sha256/")
            if re.fullmatch(r"[0-9a-f]{64}", pin) is None:
                raise TlsConfigurationError("certificate pin must be a SHA-256 digest")
            pins.append(pin)

        return ResolvedTls(
            verify=verify,
            ca_file=ca_file,
            client_cert=client_cert,
            certificate_pins=tuple(pins),
            audit_events=("network.tls_insecure",) if verify is False else (),
        )

    @staticmethod
    def _require_file(value: object, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TlsConfigurationError(f"{label} must be configured")
        path = Path(value).expanduser()
        if not path.is_file():
            raise TlsConfigurationError(f"{label} does not exist")
        return str(path.resolve())


def build_ssl_context(resolved_tls: ResolvedTls) -> ssl.SSLContext:
    if resolved_tls.verify is False:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif resolved_tls.verify == "system":
        context = ssl.create_default_context()
    else:
        context = ssl.create_default_context(cafile=resolved_tls.verify)
    if resolved_tls.client_cert is not None:
        context.load_cert_chain(*resolved_tls.client_cert)
    return context


def verify_certificate_pins_from_der(
    certificate: bytes | None,
    pins: tuple[str, ...],
) -> None:
    if not pins:
        return
    if not isinstance(certificate, bytes) or not certificate:
        raise ValueError("network.tls_pin_unavailable")
    digest = hashlib.sha256(certificate).hexdigest()
    if not any(hmac.compare_digest(digest, pin) for pin in pins):
        raise ValueError("network.tls_pin_mismatch")


def verify_response_certificate_pins(response: object, pins: tuple[str, ...]) -> None:
    if not pins:
        return
    extensions = getattr(response, "extensions", None)
    stream = extensions.get("network_stream") if isinstance(extensions, Mapping) else None
    get_extra_info = getattr(stream, "get_extra_info", None)
    if not callable(get_extra_info):
        raise ValueError("network.tls_pin_unavailable")
    ssl_object = get_extra_info("ssl_object")
    get_peer_certificate = getattr(ssl_object, "getpeercert", None)
    if not callable(get_peer_certificate):
        raise ValueError("network.tls_pin_unavailable")
    verify_certificate_pins_from_der(get_peer_certificate(binary_form=True), pins)


def verify_websocket_certificate_pins(socket: object, pins: tuple[str, ...]) -> None:
    if not pins:
        return
    transport = getattr(socket, "transport", None)
    get_extra_info = getattr(transport, "get_extra_info", None)
    if not callable(get_extra_info):
        raise ValueError("network.tls_pin_unavailable")
    ssl_object = get_extra_info("ssl_object")
    get_peer_certificate = getattr(ssl_object, "getpeercert", None)
    if not callable(get_peer_certificate):
        raise ValueError("network.tls_pin_unavailable")
    verify_certificate_pins_from_der(get_peer_certificate(binary_form=True), pins)
