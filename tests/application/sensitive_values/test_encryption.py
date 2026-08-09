from __future__ import annotations

import pytest

from weconduct.application.sensitive_values import encryption
from weconduct.application.sensitive_values.encryption import (
    SensitiveUnlockError,
    decrypt_parameter_values,
    encrypt_parameter_values,
)


def test_encrypted_parameter_envelope_round_trips_with_versioned_aad() -> None:
    envelope = encrypt_parameter_values(
        {"api_key": "test-secret", "retries": 3},
        password="correct-password",
        parameter_set_id="parameters-1",
    )

    assert envelope["encryption_schema_version"] == 1
    assert envelope["parameter_set_id"] == "parameters-1"
    assert envelope["kdf"]["n"] >= 2**17
    assert decrypt_parameter_values(envelope, password="correct-password") == {
        "api_key": "test-secret",
        "retries": 3,
    }


@pytest.mark.parametrize("password", ["wrong-password", "correct-password"])
def test_parameter_unlock_normalizes_wrong_password_and_tampering(password: str) -> None:
    envelope = encrypt_parameter_values(
        {"api_key": "test-secret"},
        password="correct-password",
        parameter_set_id="parameters-1",
    )
    if password == "correct-password":
        envelope = {**envelope, "cipher": {**envelope["cipher"], "ciphertext": "AAAA"}}

    with pytest.raises(SensitiveUnlockError, match="sensitive.unlock_failed"):
        decrypt_parameter_values(envelope, password=password)


def test_parameter_unlock_keeps_legacy_scrypt_cost_compatible_and_rejects_excessive_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        encryption,
        "_SCRYPT_PARAMS",
        {"name": "scrypt", "n": 2**14, "r": 8, "p": 1, "key_length": 32},
    )
    legacy_envelope = encrypt_parameter_values(
        {"api_key": "legacy-secret"},
        password="correct-password",
        parameter_set_id="parameters-1",
    )

    assert decrypt_parameter_values(legacy_envelope, password="correct-password") == {
        "api_key": "legacy-secret"
    }

    excessive_envelope = {
        **legacy_envelope,
        "kdf": {**legacy_envelope["kdf"], "n": 2**18},
    }
    with pytest.raises(SensitiveUnlockError, match="sensitive.unlock_failed"):
        decrypt_parameter_values(excessive_envelope, password="correct-password")
