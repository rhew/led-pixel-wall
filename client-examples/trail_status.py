#!/usr/bin/env python3
"""Render local trail status to the LED wall."""

import math
import socket
import time
from typing import List, Tuple

from trailstatuslib import fetch_tmtb_trail_statuses

CONTROLLER_IP = "192.168.86.28"
CONTROLLER_PORT = 4048
PANEL_WIDTH = 10
PANEL_HEIGHT = 10
DDP_SEQUENCE_MAX = 255
FRAME_INTERVAL = 0.1
TRAIL_STATUS_REFRESH_SECONDS = 300.0
TRAIL_STATUS_BLINK_HOURS = 2.0
TRAIL_STATUS_DIM_HOURS = 24.0
TRAIL_STATUS_NORMAL_BRIGHTNESS = 0.72
TRAIL_STATUS_MIN_BRIGHTNESS = 0.18


def serpentine_index(x: int, y: int) -> int:
    hw_y = PANEL_HEIGHT - 1 - y
    if hw_y % 2 == 0:
        return hw_y * PANEL_WIDTH + x
    return hw_y * PANEL_WIDTH + (PANEL_WIDTH - 1 - x)


def pixels_to_bytes(pixels: List[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)


def make_ddp_packet(sequence: int, pixels: List[Tuple[int, int, int]]) -> bytes:
    payload = pixels_to_bytes(pixels)
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


def blend_color(color: Tuple[int, int, int], scale: float) -> Tuple[int, int, int]:
    scale = max(0.0, min(1.0, scale))
    return (
        int(color[0] * scale),
        int(color[1] * scale),
        int(color[2] * scale),
    )


class TrailStatusDisplay:
    def __init__(self) -> None:
        self.last_refresh = -TRAIL_STATUS_REFRESH_SECONDS
        self.trails = []
        self.fetch_error = None

    def _format_age(self, updated_epoch: int | None) -> str:
        if updated_epoch is None:
            return "--h --m"

        delta_seconds = max(0, int(time.time() - updated_epoch))
        hours = delta_seconds // 3600
        minutes = (delta_seconds % 3600) // 60
        return f"{hours}h {minutes:02d}m"

    def _log_trails(self) -> None:
        for trail in self.trails:
            print(
                f"{self._format_age(trail.updated_epoch):>8}  "
                f"{trail.status:<7}  {trail.name}"
            )

    def _refresh(self) -> None:
        trails = fetch_tmtb_trail_statuses()
        self.trails = sorted(trails, key=lambda trail: trail.name.lower())
        self.fetch_error = None
        self._log_trails()

    def _status_color(self, status: str) -> Tuple[int, int, int]:
        normalized = status.lower()
        if normalized == "open":
            return (0, 220, 40)
        if normalized == "closed":
            return (255, 16, 0)
        return (210, 150, 0)

    def _brightness(self, updated_epoch: int | None, elapsed: float) -> float:
        if updated_epoch is None:
            return TRAIL_STATUS_MIN_BRIGHTNESS
        age_hours = max(0.0, (time.time() - updated_epoch) / 3600.0)
        if age_hours <= TRAIL_STATUS_BLINK_HOURS:
            return TRAIL_STATUS_NORMAL_BRIGHTNESS * (
                0.5 + 0.5 * math.sin(elapsed * math.tau / 2.6)
            )
        if age_hours >= TRAIL_STATUS_DIM_HOURS:
            return TRAIL_STATUS_MIN_BRIGHTNESS

        progress = (age_hours - TRAIL_STATUS_BLINK_HOURS) / (
            TRAIL_STATUS_DIM_HOURS - TRAIL_STATUS_BLINK_HOURS
        )
        return TRAIL_STATUS_NORMAL_BRIGHTNESS - (
            TRAIL_STATUS_NORMAL_BRIGHTNESS - TRAIL_STATUS_MIN_BRIGHTNESS
        ) * progress

    def frame(self, elapsed: float) -> List[Tuple[int, int, int]]:
        if elapsed - self.last_refresh >= TRAIL_STATUS_REFRESH_SECONDS:
            try:
                self._refresh()
            except Exception as exc:
                self.fetch_error = str(exc)
            self.last_refresh = elapsed

        pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
        if not self.trails:
            return pixels

        columns = 1 if len(self.trails) <= PANEL_HEIGHT else 2
        rows_per_column = math.ceil(len(self.trails) / columns)
        row_height = max(1, PANEL_HEIGHT // rows_per_column)
        top_padding = max(0, PANEL_HEIGHT - row_height * rows_per_column)
        column_width = PANEL_WIDTH // columns

        for index, trail in enumerate(self.trails[: rows_per_column * columns]):
            column = index // rows_per_column
            row = index % rows_per_column
            start_x = column * column_width
            start_y = top_padding + row * row_height
            color = self._status_color(trail.status)
            brightness = self._brightness(trail.updated_epoch, elapsed)
            scaled = blend_color(color, brightness)

            for y in range(start_y, min(start_y + row_height, PANEL_HEIGHT)):
                for x in range(start_x, min(start_x + column_width, PANEL_WIDTH)):
                    pixels[serpentine_index(x, y)] = scaled

        return pixels


def run() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    display = TrailStatusDisplay()
    sequence = 0
    start = time.perf_counter()
    blank_pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
    try:
        sock.sendto(make_ddp_packet(sequence, blank_pixels), (CONTROLLER_IP, CONTROLLER_PORT))
        sequence = (sequence + 1) % (DDP_SEQUENCE_MAX + 1)

        while True:
            now = time.perf_counter()
            elapsed = now - start
            sock.sendto(
                make_ddp_packet(sequence, display.frame(elapsed)),
                (CONTROLLER_IP, CONTROLLER_PORT),
            )
            sequence = (sequence + 1) % (DDP_SEQUENCE_MAX + 1)
            spent = time.perf_counter() - now
            time.sleep(max(0.0, FRAME_INTERVAL - spent))
    finally:
        sock.close()


if __name__ == "__main__":
    run()
