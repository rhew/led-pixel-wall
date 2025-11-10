from typing import List, Tuple

DDP_SEQUENCE_MAX = 255


def build_ddp_packet(sequence: int, payload: bytes) -> bytes:
    flags_version = 0x41
    data_type = 0x01
    offset = 0
    data_len = len(payload)
    header = bytes([
        flags_version,
        sequence & 0xFF,
        data_type,
        (offset >> 8) & 0xFF,
        offset & 0xFF,
        (data_len >> 8) & 0xFF,
        data_len & 0xFF,
        0x00,
        0x00,
        0x00,
    ])
    return header + payload


def pixels_to_bytes(pixels: List[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)
