#!/usr/bin/env python3
"""Minimal DDP client that paints the LED Pixel Wall solid blue.

Assumes the controller is reachable at 192.168.86.32 and provisioned for 100 LEDs.
"""

import socket
import struct

CONTROLLER_IP = "192.168.86.32"
CONTROLLER_PORT = 4048
LED_COUNT = 100


def build_ddp_packet(sequence: int, rgb_bytes: bytes) -> bytes:
    """Constructs a DDP packet for channel offset 0."""
    flags_version = 0x41  # 0x40 data flag + version 1
    data_type = 0x01  # packed RGB
    offset = 0
    length = len(rgb_bytes)
    data_id = 0  # single canvas

    header = struct.pack(
        ">BBBH H H",
        flags_version,
        sequence & 0xFF,
        data_type,
        offset,
        length,
        data_id,
    )
    reserved = b"\x00"  # 10th byte (timecode); unused but must be present
    return header + reserved + rgb_bytes


def main() -> None:
    solid_blue = bytes([0xFF, 0x00, 0x00] * LED_COUNT)
    packet = build_ddp_packet(sequence=2, rgb_bytes=solid_blue)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, (CONTROLLER_IP, CONTROLLER_PORT))
    print(f"Sent {len(packet)} bytes to {CONTROLLER_IP}:{CONTROLLER_PORT}")


if __name__ == "__main__":
    main()
