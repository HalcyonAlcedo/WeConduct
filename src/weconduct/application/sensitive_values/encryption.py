from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


_ENCRYPTION_SCHEMA_VERSION = 1
_SALT_BYTES = 16
_NONCE_BYTES = 12
_KEY_BYTES = 32
_MIN_SCRYPT_N = 2**14  # 兼容 0.9.0 之前已保存的合法 envelope。
_MAX_SCRYPT_N = 2**17
_MAX_SCRYPT_R = 8
_MAX_SCRYPT_P = 4
_MAX_SCRYPT_MEMORY_BYTES = 128 * 1024 * 1024
_SCRYPT_PARAMS = {
    "name": "scrypt",
    "n": _MAX_SCRYPT_N,
    "r": 8,
    "p": 1,
    "key_length": _KEY_BYTES,
}


@dataclass(frozen=True)
class SensitiveUnlockError(ValueError):
    error_code: str = "sensitive.unlock_failed"

    def __str__(self) -> str:
        return self.error_code


def encrypt_parameter_values(
    values: Mapping[str, object],
    *,
    password: str,
    parameter_set_id: str,
) -> dict[str, Any]:
    if not isinstance(parameter_set_id, str) or not parameter_set_id.strip():
        raise ValueError("parameter_set_id must be a non-empty string")
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    normalized_parameter_set_id = parameter_set_id.strip()
    key = _derive_key(password=password, salt=salt, params=_SCRYPT_PARAMS)
    encrypted = AESGCM(key).encrypt(
        nonce,
        json.dumps(dict(values), ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
        _build_aad(normalized_parameter_set_id),
    )
    return {
        "encryption_schema_version": _ENCRYPTION_SCHEMA_VERSION,
        "parameter_set_id": normalized_parameter_set_id,
        "kdf": {**_SCRYPT_PARAMS, "salt": _encode(salt)},
        "cipher": {"name": "aes-256-gcm", "nonce": _encode(nonce), "ciphertext": _encode(encrypted)},
    }


def decrypt_parameter_values(envelope: Mapping[str, object], *, password: str) -> dict[str, object]:
    try:
        parameter_set_id = envelope["parameter_set_id"]
        kdf = envelope["kdf"]
        cipher = envelope["cipher"]
        if (
            envelope.get("encryption_schema_version") != _ENCRYPTION_SCHEMA_VERSION
            or not isinstance(parameter_set_id, str)
            or not isinstance(kdf, Mapping)
            or not isinstance(cipher, Mapping)
            or kdf.get("name") != "scrypt"
            or cipher.get("name") != "aes-256-gcm"
        ):
            raise ValueError
        params = {
            "name": "scrypt",
            "n": _positive_int(kdf.get("n")),
            "r": _positive_int(kdf.get("r")),
            "p": _positive_int(kdf.get("p")),
            "key_length": _positive_int(kdf.get("key_length")),
        }
        if params["key_length"] != _KEY_BYTES:
            raise ValueError
        _validate_scrypt_params(params)
        salt = _decode(kdf.get("salt"))
        nonce = _decode(cipher.get("nonce"))
        ciphertext = _decode(cipher.get("ciphertext"))
        if len(salt) < _SALT_BYTES or len(nonce) != _NONCE_BYTES:
            raise ValueError
        plaintext = AESGCM(_derive_key(password=password, salt=salt, params=params)).decrypt(
            nonce,
            ciphertext,
            _build_aad(parameter_set_id),
        )
        values = json.loads(plaintext.decode("utf-8"))
        if not isinstance(values, dict):
            raise ValueError
        return values
    except (InvalidTag, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        raise SensitiveUnlockError() from None


def _derive_key(*, password: str, salt: bytes, params: Mapping[str, object]) -> bytes:
    if not isinstance(password, str):
        raise ValueError("password must be a string")
    return Scrypt(
        salt=salt,
        length=int(params["key_length"]),
        n=int(params["n"]),
        r=int(params["r"]),
        p=int(params["p"]),
    ).derive(password.encode("utf-8"))


def _validate_scrypt_params(params: Mapping[str, int]) -> None:
    n = params["n"]
    r = params["r"]
    p = params["p"]
    if n < _MIN_SCRYPT_N or n > _MAX_SCRYPT_N or n & (n - 1):
        raise ValueError
    if r > _MAX_SCRYPT_R or p > _MAX_SCRYPT_P:
        raise ValueError
    if n * r * 128 > _MAX_SCRYPT_MEMORY_BYTES:
        raise ValueError


def _build_aad(parameter_set_id: str) -> bytes:
    return f"{_ENCRYPTION_SCHEMA_VERSION}:{parameter_set_id}".encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError
    return base64.b64decode(value.encode("ascii"), validate=True)


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError
    return value
