from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
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
            raise TlsConfigurationError(f"{label} does not exist: {path}")
        return str(path.resolve())
