from __future__ import annotations


def packb(value: object) -> bytes:
    encoder = _MsgpackEncoder()
    encoder.pack(value)
    return bytes(encoder.buffer)


def unpackb(payload: bytes) -> object:
    decoder = _MsgpackDecoder(payload)
    result = decoder.unpack()
    if decoder.offset != len(payload):
        raise ValueError("extra bytes after msgpack payload")
    return result


class _MsgpackEncoder:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def pack(self, value: object) -> None:
        if value is None:
            self.buffer.append(0xC0)
            return
        if value is False:
            self.buffer.append(0xC2)
            return
        if value is True:
            self.buffer.append(0xC3)
            return
        if isinstance(value, int):
            self._pack_int(value)
            return
        if isinstance(value, float):
            self.buffer.append(0xCB)
            import struct

            self.buffer.extend(struct.pack(">d", value))
            return
        if isinstance(value, str):
            self._pack_str(value)
            return
        if isinstance(value, bytes):
            self._pack_bin(value)
            return
        if isinstance(value, list):
            self._pack_array(value)
            return
        if isinstance(value, dict):
            self._pack_map(value)
            return
        raise TypeError(f"unsupported msgpack type: {type(value)!r}")

    def _pack_int(self, value: int) -> None:
        if 0 <= value <= 0x7F:
            self.buffer.append(value)
            return
        if -32 <= value < 0:
            self.buffer.append(0x100 + value)
            return
        if 0 <= value <= 0xFF:
            self.buffer.extend((0xCC, value))
            return
        if 0 <= value <= 0xFFFF:
            self.buffer.append(0xCD)
            self.buffer.extend(value.to_bytes(2, "big"))
            return
        if 0 <= value <= 0xFFFFFFFF:
            self.buffer.append(0xCE)
            self.buffer.extend(value.to_bytes(4, "big"))
            return
        if 0 <= value <= 0xFFFFFFFFFFFFFFFF:
            self.buffer.append(0xCF)
            self.buffer.extend(value.to_bytes(8, "big"))
            return
        if -0x80 <= value < 0:
            self.buffer.append(0xD0)
            self.buffer.extend(value.to_bytes(1, "big", signed=True))
            return
        if -0x8000 <= value < 0:
            self.buffer.append(0xD1)
            self.buffer.extend(value.to_bytes(2, "big", signed=True))
            return
        if -0x80000000 <= value < 0:
            self.buffer.append(0xD2)
            self.buffer.extend(value.to_bytes(4, "big", signed=True))
            return
        self.buffer.append(0xD3)
        self.buffer.extend(value.to_bytes(8, "big", signed=True))

    def _pack_str(self, value: str) -> None:
        encoded = value.encode("utf-8")
        length = len(encoded)
        if length <= 31:
            self.buffer.append(0xA0 | length)
        elif length <= 0xFF:
            self.buffer.extend((0xD9, length))
        elif length <= 0xFFFF:
            self.buffer.append(0xDA)
            self.buffer.extend(length.to_bytes(2, "big"))
        else:
            self.buffer.append(0xDB)
            self.buffer.extend(length.to_bytes(4, "big"))
        self.buffer.extend(encoded)

    def _pack_bin(self, value: bytes) -> None:
        length = len(value)
        if length <= 0xFF:
            self.buffer.extend((0xC4, length))
        elif length <= 0xFFFF:
            self.buffer.append(0xC5)
            self.buffer.extend(length.to_bytes(2, "big"))
        else:
            self.buffer.append(0xC6)
            self.buffer.extend(length.to_bytes(4, "big"))
        self.buffer.extend(value)

    def _pack_array(self, value: list[object]) -> None:
        length = len(value)
        if length <= 15:
            self.buffer.append(0x90 | length)
        elif length <= 0xFFFF:
            self.buffer.append(0xDC)
            self.buffer.extend(length.to_bytes(2, "big"))
        else:
            self.buffer.append(0xDD)
            self.buffer.extend(length.to_bytes(4, "big"))
        for item in value:
            self.pack(item)

    def _pack_map(self, value: dict[object, object]) -> None:
        items = list(value.items())
        length = len(items)
        if length <= 15:
            self.buffer.append(0x80 | length)
        elif length <= 0xFFFF:
            self.buffer.append(0xDE)
            self.buffer.extend(length.to_bytes(2, "big"))
        else:
            self.buffer.append(0xDF)
            self.buffer.extend(length.to_bytes(4, "big"))
        for key, item in items:
            if not isinstance(key, str):
                raise TypeError(f"unsupported msgpack map key type: {type(key)!r}")
            self.pack(key)
            self.pack(item)


class _MsgpackDecoder:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0

    def unpack(self) -> object:
        if self.offset >= len(self.payload):
            raise ValueError("unexpected end of msgpack payload")
        prefix = self._read_u8()
        if prefix <= 0x7F:
            return prefix
        if prefix >= 0xE0:
            return prefix - 0x100
        if 0xA0 <= prefix <= 0xBF:
            return self._read_str(prefix & 0x1F)
        if 0x90 <= prefix <= 0x9F:
            return self._read_array(prefix & 0x0F)
        if 0x80 <= prefix <= 0x8F:
            return self._read_map(prefix & 0x0F)
        if prefix == 0xC0:
            return None
        if prefix == 0xC2:
            return False
        if prefix == 0xC3:
            return True
        if prefix == 0xC4:
            return self._read_bytes(self._read_uint(1))
        if prefix == 0xC5:
            return self._read_bytes(self._read_uint(2))
        if prefix == 0xC6:
            return self._read_bytes(self._read_uint(4))
        if prefix == 0xCB:
            import struct

            return struct.unpack(">d", self._read_bytes(8))[0]
        if prefix == 0xCC:
            return self._read_uint(1)
        if prefix == 0xCD:
            return self._read_uint(2)
        if prefix == 0xCE:
            return self._read_uint(4)
        if prefix == 0xCF:
            return self._read_uint(8)
        if prefix == 0xD0:
            return self._read_int(1)
        if prefix == 0xD1:
            return self._read_int(2)
        if prefix == 0xD2:
            return self._read_int(4)
        if prefix == 0xD3:
            return self._read_int(8)
        if prefix == 0xD9:
            return self._read_str(self._read_uint(1))
        if prefix == 0xDA:
            return self._read_str(self._read_uint(2))
        if prefix == 0xDB:
            return self._read_str(self._read_uint(4))
        if prefix == 0xDC:
            return self._read_array(self._read_uint(2))
        if prefix == 0xDD:
            return self._read_array(self._read_uint(4))
        if prefix == 0xDE:
            return self._read_map(self._read_uint(2))
        if prefix == 0xDF:
            return self._read_map(self._read_uint(4))
        raise ValueError(f"unsupported msgpack prefix: 0x{prefix:02x}")

    def _read_u8(self) -> int:
        value = self.payload[self.offset]
        self.offset += 1
        return value

    def _read_bytes(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.payload):
            raise ValueError("unexpected end of msgpack payload")
        value = self.payload[self.offset:end]
        self.offset = end
        return value

    def _read_uint(self, size: int) -> int:
        return int.from_bytes(self._read_bytes(size), "big", signed=False)

    def _read_int(self, size: int) -> int:
        return int.from_bytes(self._read_bytes(size), "big", signed=True)

    def _read_str(self, size: int) -> str:
        return self._read_bytes(size).decode("utf-8")

    def _read_array(self, size: int) -> list[object]:
        return [self.unpack() for _ in range(size)]

    def _read_map(self, size: int) -> dict[str, object]:
        result: dict[str, object] = {}
        for _ in range(size):
            key = self.unpack()
            if not isinstance(key, str):
                raise ValueError("msgpack map key must be string")
            result[key] = self.unpack()
        return result
