from __future__ import annotations

import pytest

from weconduct.packaging.msgpack_codec import packb, unpackb


LEGACY_PAYLOAD = bytes.fromhex(
    "84a46e616d65a66c6567616379a4626c6f62c40200ffa56974656d739301c3c0a5726174696fcb3ff8000000000000"
)


def test_unpackb_reads_legacy_payload() -> None:
    assert unpackb(LEGACY_PAYLOAD) == {
        "name": "legacy",
        "blob": b"\x00\xff",
        "items": [1, True, None],
        "ratio": 1.5,
    }


def test_unpackb_accepts_standard_msgpack_float32() -> None:
    assert unpackb(bytes.fromhex("ca3fa00000")) == 1.25


def test_unpackb_rejects_trailing_payload() -> None:
    with pytest.raises(ValueError, match="extra bytes"):
        unpackb(packb({"value": 1}) + b"\xc0")


def test_packb_rejects_non_string_map_keys() -> None:
    with pytest.raises(TypeError, match="map key"):
        packb({1: "invalid"})
