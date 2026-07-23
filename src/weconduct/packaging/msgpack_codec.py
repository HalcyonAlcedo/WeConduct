from __future__ import annotations

from collections.abc import Mapping, Sequence

import msgpack


def packb(value: object) -> bytes:
    """Encode the stable WeConduct MsgPack value subset."""
    _validate_encodable(value)
    try:
        return msgpack.packb(value, use_bin_type=True, strict_types=True)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TypeError(f"unsupported msgpack value: {type(value)!r}") from exc


def unpackb(payload: bytes) -> object:
    """Decode exactly one MsgPack value with UTF-8 strings and string map keys."""
    try:
        return msgpack.unpackb(payload, raw=False, strict_map_key=True)
    except msgpack.ExtraData as exc:
        raise ValueError("extra bytes after msgpack payload") from exc
    except (
        msgpack.FormatError,
        msgpack.OutOfData,
        msgpack.StackError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise ValueError(str(exc) or "invalid msgpack payload") from exc


def _validate_encodable(value: object) -> None:
    if value is None or isinstance(value, bool | int | float | str | bytes):
        return
    if isinstance(value, list):
        for item in value:
            _validate_encodable(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"unsupported msgpack map key type: {type(key)!r}")
            _validate_encodable(item)
        return
    if isinstance(value, Sequence):
        raise TypeError(f"unsupported msgpack type: {type(value)!r}")
    raise TypeError(f"unsupported msgpack type: {type(value)!r}")
