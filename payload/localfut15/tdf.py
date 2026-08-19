"""Blaze Fire2 framing and TDF wire codec.

Extracted verbatim from server.py. FIFA 15's port 10051 connection speaks the
Fire2 Blaze frame used by later BlazeSDK builds, carrying TDF-encoded fields.

This module is deliberately protocol-only: encoding, decoding and framing, with
no knowledge of game state. The _blaze_* payload builders that assemble actual
responses stay in server.py, because they read CFG and STATE.
"""

from __future__ import annotations

from dataclasses import dataclass


_TDF_VARINT = 0x0


_TDF_STRING = 0x1


_TDF_BLOB = 0x2


_TDF_GROUP = 0x3


_TDF_LIST = 0x4


_TDF_MAP = 0x5


_TDF_UNION = 0x6


_TDF_OBJECT_TYPE = 0x8


_TDF_OBJECT_ID = 0x9


def _tdf_tag(tag: str | bytes, value_type: int) -> bytes:
    """Encode a 1-4 character Blaze TDF tag plus type byte."""
    raw = tag.encode("ascii") if isinstance(tag, str) else bytes(tag)
    if not 1 <= len(raw) <= 4:
        raise ValueError(f"TDF tag must be 1-4 bytes: {raw!r}")
    out = [0, 0, 0, int(value_type) & 0xFF]
    if len(raw) > 0:
        out[0] |= (raw[0] & 0x40) << 1
        out[0] |= (raw[0] & 0x10) << 2
        out[0] |= (raw[0] & 0x0F) << 2
    if len(raw) > 1:
        out[0] |= (raw[1] & 0x40) >> 5
        out[0] |= (raw[1] & 0x10) >> 4
        out[1] |= (raw[1] & 0x0F) << 4
    if len(raw) > 2:
        out[1] |= (raw[2] & 0x40) >> 3
        out[1] |= (raw[2] & 0x10) >> 2
        out[1] |= (raw[2] & 0x0C) >> 2
        out[2] |= (raw[2] & 0x03) << 6
    if len(raw) > 3:
        out[2] |= (raw[3] & 0x40) >> 1
        out[2] |= raw[3] & 0x1F
    return bytes(out)


def _tdf_varint(value: int) -> bytes:
    value = int(value)
    if value < 0:
        # Blaze serializes signed integers through their unsigned bit pattern.
        value &= (1 << 64) - 1
    if value < 0x40:
        return bytes([value])
    out = bytearray([(value & 0x3F) | 0x80])
    value >>= 6
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def _tdf_str_value(value: str) -> bytes:
    raw = str(value).encode("utf-8")
    return _tdf_varint(len(raw) + 1) + raw + b"\x00"


def _tdf_field_int(tag: str, value: int) -> bytes:
    return _tdf_tag(tag, _TDF_VARINT) + _tdf_varint(value)


def _tdf_field_str(tag: str, value: str) -> bytes:
    return _tdf_tag(tag, _TDF_STRING) + _tdf_str_value(value)


def _tdf_field_blob(tag: str, value: bytes) -> bytes:
    raw = bytes(value)
    return _tdf_tag(tag, _TDF_BLOB) + _tdf_varint(len(raw)) + raw


def _tdf_field_object_id(tag: str, component: int, entity_type: int, entity_id: int) -> bytes:
    """Encode Blaze Heat2 ObjectId: component, entity type, then 64-bit id as varints."""
    return (
        _tdf_tag(tag, _TDF_OBJECT_ID)
        + _tdf_varint(component)
        + _tdf_varint(entity_type)
        + _tdf_varint(entity_id)
    )


def _tdf_field_group(tag: str, body: bytes) -> bytes:
    return _tdf_tag(tag, _TDF_GROUP) + body + b"\x00"


def _tdf_field_list_int(tag: str, values: list[int] | tuple[int, ...]) -> bytes:
    out = bytearray(_tdf_tag(tag, _TDF_LIST))
    out.append(_TDF_VARINT)
    out.extend(_tdf_varint(len(values)))
    for value in values:
        out.extend(_tdf_varint(value))
    return bytes(out)


def _tdf_field_list_groups(tag: str, groups: list[bytes]) -> bytes:
    out = bytearray(_tdf_tag(tag, _TDF_LIST))
    out.append(_TDF_GROUP)
    out.extend(_tdf_varint(len(groups)))
    for body in groups:
        out.extend(body)
        out.append(0)  # each group body terminator
    return bytes(out)


def _tdf_field_map_str_str(tag: str, values: list[tuple[str, str]]) -> bytes:
    out = bytearray(_tdf_tag(tag, _TDF_MAP))
    out.extend((_TDF_STRING, _TDF_STRING))
    out.extend(_tdf_varint(len(values)))
    for key, value in values:
        out.extend(_tdf_str_value(key))
        out.extend(_tdf_str_value(value))
    return bytes(out)


def _tdf_field_map_str_group(tag: str, values: list[tuple[str, bytes]]) -> bytes:
    out = bytearray(_tdf_tag(tag, _TDF_MAP))
    out.extend((_TDF_STRING, _TDF_GROUP))
    out.extend(_tdf_varint(len(values)))
    for key, body in values:
        out.extend(_tdf_str_value(key))
        out.extend(body)
        out.append(0)  # group terminator
    return bytes(out)


def _tdf_decode_varint(raw: bytes, pos: int = 0) -> tuple[int, int]:
    if pos >= len(raw):
        raise ValueError("truncated TDF varint")
    first = raw[pos]
    pos += 1
    value = first & 0x3F
    shift = 6
    if first & 0x80:
        while True:
            if pos >= len(raw):
                raise ValueError("truncated TDF varint")
            b = raw[pos]
            pos += 1
            value |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
    return value, pos


def _tdf_get_string(raw: bytes, tag: str) -> str | None:
    marker = _tdf_tag(tag, _TDF_STRING)
    p = raw.find(marker)
    if p < 0:
        return None
    p += 4
    try:
        n, p = _tdf_decode_varint(raw, p)
    except ValueError:
        return None
    if n <= 0 or p + n > len(raw):
        return None
    value = raw[p:p+n]
    if value.endswith(b"\x00"):
        value = value[:-1]
    return value.decode("utf-8", errors="replace")


def _tdf_get_int_last(raw: bytes, tag: str) -> int | None:
    """Return the last matching Blaze varint field for nested report payloads."""
    marker = _tdf_tag(tag, _TDF_VARINT)
    p = raw.rfind(marker)
    if p < 0:
        return None
    p += len(marker)
    try:
        value, _ = _tdf_decode_varint(raw, p)
        return int(value)
    except ValueError:
        return None


def _tdf_debug_summary(raw: bytes) -> str:
    """Best-effort non-mutating TDF scout used only for compatibility logging."""
    if not raw:
        return "<empty>"
    # Extract printable ASCII runs; method/adaptor names often survive here.
    strings = []
    cur = bytearray()
    for b in raw:
        if 32 <= b <= 126:
            cur.append(b)
        else:
            if len(cur) >= 3:
                strings.append(cur.decode("ascii", errors="replace"))
            cur.clear()
    if len(cur) >= 3:
        strings.append(cur.decode("ascii", errors="replace"))

    # Best-effort scan for packed Blaze TDF 3-char tags. Do not attempt to parse
    # values recursively; malformed guesses are harmless because this is logging only.
    tags = []
    for i in range(max(0, len(raw) - 3)):
        chunk = raw[i:i+3]
        # Packed TDF tags commonly decode to uppercase alnum/_ names. Keep only
        # plausible candidates to avoid a wall of noise.
        try:
            v = int.from_bytes(chunk, "big")
            chars = [
                ((v >> 18) & 0x3F) + 32,
                ((v >> 12) & 0x3F) + 32,
                ((v >> 6) & 0x3F) + 32,
                (v & 0x3F) + 32,
            ]
            name = ''.join(chr(c) for c in chars).rstrip()
            if 2 <= len(name) <= 4 and all(c.isupper() or c.isdigit() or c == '_' for c in name):
                if name not in tags:
                    tags.append(name)
        except Exception:
            pass
        if len(tags) >= 24:
            break
    return f"hex={raw[:256].hex()} ascii={strings[:20]} tags={tags}"


@dataclass
class Fire2Packet:
    payload_size: int
    metadata_size: int
    component: int
    command: int
    msg_num: int
    msg_type: int
    metadata: bytes
    payload: bytes
    raw: bytes


def _fire2_try_parse(buf: bytearray) -> Fire2Packet | None:
    if len(buf) < 16:
        return None
    payload_size = int.from_bytes(buf[0:4], "big")
    metadata_size = int.from_bytes(buf[4:6], "big")
    total = 16 + metadata_size + payload_size
    if payload_size > 16 * 1024 * 1024 or metadata_size > 1024 * 1024:
        raise ValueError(f"unreasonable Fire2 sizes payload={payload_size} metadata={metadata_size}")
    if len(buf) < total:
        return None
    raw = bytes(buf[:total])
    del buf[:total]
    component = int.from_bytes(raw[6:8], "big")
    command = int.from_bytes(raw[8:10], "big")
    msg_num = int.from_bytes(raw[10:13], "big")
    msg_type = raw[13] >> 5
    metadata = raw[16:16 + metadata_size]
    payload = raw[16 + metadata_size:]
    return Fire2Packet(payload_size, metadata_size, component, command, msg_num, msg_type, metadata, payload, raw)


def _fire2_build(component: int, command: int, msg_num: int, msg_type: int, payload: bytes = b"", metadata: bytes = b"") -> bytes:
    out = bytearray()
    out += len(payload).to_bytes(4, "big")
    out += len(metadata).to_bytes(2, "big")
    out += int(component).to_bytes(2, "big")
    out += int(command).to_bytes(2, "big")
    out += (int(msg_num) & 0xFFFFFF).to_bytes(3, "big")
    out += bytes([(int(msg_type) & 0x07) << 5, 0, 0])
    out += metadata
    out += payload
    return bytes(out)
