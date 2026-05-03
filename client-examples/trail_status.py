#!/usr/bin/env python3
"""Render local trail status to the LED wall."""

import math
import time
from typing import List, Tuple

from trailstatuslib import fetch_tmtb_trail_statuses
from wallclient import DdpClient, PANEL_HEIGHT, PANEL_WIDTH, PanelConfig
from wallclient import blend_color, serpentine_index

TRAIL_STATUS_REFRESH_SECONDS = 300.0
TRAIL_STATUS_BLINK_HOURS = 2.0
TRAIL_STATUS_DIM_HOURS = 24.0
TRAIL_STATUS_NORMAL_BRIGHTNESS = 0.72
TRAIL_STATUS_MIN_BRIGHTNESS = 0.18


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
    client = DdpClient(PanelConfig())
    display = TrailStatusDisplay()
    start = time.perf_counter()
    try:
        client.send_blank()

        while True:
            now = time.perf_counter()
            elapsed = now - start
            client.send(display.frame(elapsed))
            spent = time.perf_counter() - now
            time.sleep(max(0.0, client.config.frame_interval - spent))
    finally:
        client.close()


if __name__ == "__main__":
    run()
