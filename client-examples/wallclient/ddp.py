import socket
from typing import List, Sequence, Tuple

from .config import PanelConfig
from .panel import blank_frame

DDP_SEQUENCE_MAX = 255


def pixels_to_bytes(pixels: Sequence[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)


def build_ddp_packet(sequence: int, payload: bytes) -> bytes:
    return bytes([
        0x41,
        sequence & 0xFF,
        0x01,
        0x00,
        0x00,
        (len(payload) >> 8) & 0xFF,
        len(payload) & 0xFF,
        0x00,
        0x00,
        0x00,
    ]) + payload


class DdpClient:
    def __init__(self, config: PanelConfig) -> None:
        self.config = config
        self.sequence = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, pixels: Sequence[Tuple[int, int, int]]) -> None:
        self.send_payload(pixels_to_bytes(pixels))

    def send_payload(self, payload: bytes) -> None:
        packet = build_ddp_packet(self.sequence, payload)
        self.sock.sendto(packet, (self.config.controller_ip, self.config.controller_port))
        self.sequence = (self.sequence + 1) % (DDP_SEQUENCE_MAX + 1)

    def send_blank(self) -> None:
        self.send(blank_frame(self.config.width, self.config.height))

    def close(self) -> None:
        self.sock.close()
