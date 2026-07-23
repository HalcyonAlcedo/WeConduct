from __future__ import annotations

import pytest

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
