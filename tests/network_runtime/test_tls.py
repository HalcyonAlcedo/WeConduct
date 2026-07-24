from __future__ import annotations

import pytest

from weconduct.network_runtime.tls import TlsConfigurationError, TlsResolver


def test_tls_resolver_defaults_to_system_ca() -> None:
    resolved = TlsResolver().resolve({})

    assert resolved.verify == "system"
    assert resolved.ca_file is None
    assert resolved.audit_events == ()


def test_tls_resolver_requires_existing_custom_ca_and_supports_mtls(tmp_path) -> None:
    ca_file = tmp_path / "ca.pem"
    cert_file = tmp_path / "client.pem"
    key_file = tmp_path / "client.key"
    ca_file.write_text("ca", encoding="ascii")
    cert_file.write_text("cert", encoding="ascii")
    key_file.write_text("key", encoding="ascii")

    resolved = TlsResolver().resolve(
        {
            "verify": "custom_ca",
            "ca_file": str(ca_file),
            "client_cert_file": str(cert_file),
            "client_key_file": str(key_file),
        }
    )

    assert resolved.verify == str(ca_file)
    assert resolved.client_cert == (str(cert_file), str(key_file))


def test_tls_resolver_records_insecure_audit_event_and_can_hard_block_it() -> None:
    resolved = TlsResolver().resolve({"verify": "insecure"})

    assert resolved.verify is False
    assert resolved.audit_events == ("network.tls_insecure",)

    with pytest.raises(TlsConfigurationError, match="insecure TLS is disabled"):
        TlsResolver(allow_insecure=False).resolve({"verify": "insecure"})


def test_tls_resolver_rejects_invalid_pin_and_incomplete_mtls(tmp_path) -> None:
    with pytest.raises(TlsConfigurationError, match="certificate pin"):
        TlsResolver().resolve({"certificate_pins": ["not-a-sha256-pin"]})

    cert_file = tmp_path / "client.pem"
    cert_file.write_text("cert", encoding="ascii")
    with pytest.raises(TlsConfigurationError, match="client certificate and key"):
        TlsResolver().resolve({"client_cert_file": str(cert_file)})
