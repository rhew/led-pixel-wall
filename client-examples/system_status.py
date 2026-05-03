#!/usr/bin/env python3
"""Render local CPU and memory status to the LED wall."""

import time
from typing import List, Tuple

from wallclient import DdpClient, PANEL_HEIGHT, PANEL_WIDTH, PanelConfig
from wallclient import blend_color, serpentine_index, usage_color

STATUS_UPDATE_SECONDS = 3.0
STATUS_CPU_ROWS = 8
STATUS_FADE_SECONDS = 0.8


class SystemStatusDisplay:
    def __init__(self) -> None:
        self.prev_cpu_totals, self.prev_cpu_idles = self._read_cpu_times()
        self.last_update = -STATUS_UPDATE_SECONDS
        self.display_cpu_percents = [0.0] * STATUS_CPU_ROWS
        self.target_cpu_percents = [0.0] * STATUS_CPU_ROWS
        self.start_cpu_percents = [0.0] * STATUS_CPU_ROWS
        self.display_memory_percent = 0.0
        self.target_memory_percent = self._read_memory_percent()
        self.start_memory_percent = 0.0
        self.transition_start = 0.0

    def _read_cpu_times(self) -> Tuple[List[int], List[int]]:
        totals = []
        idles = []
        with open("/proc/stat", "r", encoding="utf-8") as stat_file:
            for line in stat_file:
                if not line.startswith("cpu") or line.startswith("cpu "):
                    continue
                fields = line.split()
                if len(totals) >= STATUS_CPU_ROWS:
                    break
                values = [int(value) for value in fields[1:]]
                idle = values[3] + values[4]
                totals.append(sum(values))
                idles.append(idle)
        return totals, idles

    def _read_memory_percent(self) -> float:
        mem_total = 0
        mem_available = 0
        with open("/proc/meminfo", "r", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
                if mem_total and mem_available:
                    break
        if mem_total <= 0:
            return 0.0
        used = mem_total - mem_available
        return max(0.0, min(100.0, (used / mem_total) * 100.0))

    def _update_stats(self, elapsed: float) -> None:
        current_totals, current_idles = self._read_cpu_times()
        cpu_percents = []
        for index in range(STATUS_CPU_ROWS):
            if index >= len(current_totals) or index >= len(self.prev_cpu_totals):
                cpu_percents.append(0.0)
                continue
            delta_total = current_totals[index] - self.prev_cpu_totals[index]
            delta_idle = current_idles[index] - self.prev_cpu_idles[index]
            if delta_total <= 0:
                cpu_percents.append(0.0)
                continue
            busy = delta_total - delta_idle
            cpu_percents.append(max(0.0, min(100.0, (busy / delta_total) * 100.0)))

        self.prev_cpu_totals = current_totals
        self.prev_cpu_idles = current_idles
        self.start_cpu_percents = self.display_cpu_percents[:]
        self.target_cpu_percents = cpu_percents
        self.start_memory_percent = self.display_memory_percent
        self.target_memory_percent = self._read_memory_percent()
        self.transition_start = elapsed

    def _update_display(self, elapsed: float) -> None:
        progress = min(1.0, max(0.0, (elapsed - self.transition_start) / STATUS_FADE_SECONDS))
        eased = progress * progress * (3.0 - 2.0 * progress)
        self.display_cpu_percents = [
            start + (target - start) * eased
            for start, target in zip(self.start_cpu_percents, self.target_cpu_percents)
        ]
        self.display_memory_percent = (
            self.start_memory_percent
            + (self.target_memory_percent - self.start_memory_percent) * eased
        )

    def _render_bar(
        self,
        pixels: List[Tuple[int, int, int]],
        y: int,
        percent: float,
    ) -> None:
        color = usage_color(percent)
        fill = (max(0.0, min(100.0, percent)) / 100.0) * PANEL_WIDTH
        whole_pixels = int(fill)
        partial = fill - whole_pixels

        for x in range(PANEL_WIDTH):
            pixels[serpentine_index(x, y)] = (0, 0, 0)

        for x in range(min(whole_pixels, PANEL_WIDTH)):
            pixels[serpentine_index(x, y)] = color

        if whole_pixels < PANEL_WIDTH and partial > 0.0:
            pixels[serpentine_index(whole_pixels, y)] = blend_color(color, partial)

    def frame(self, elapsed: float) -> List[Tuple[int, int, int]]:
        if elapsed - self.last_update >= STATUS_UPDATE_SECONDS:
            self._update_stats(elapsed)
            self.last_update = elapsed
        self._update_display(elapsed)

        pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)

        for row in range(min(STATUS_CPU_ROWS, PANEL_HEIGHT)):
            self._render_bar(pixels, row, self.display_cpu_percents[row])

        if PANEL_HEIGHT > STATUS_CPU_ROWS:
            self._render_bar(pixels, PANEL_HEIGHT - 1, self.display_memory_percent)

        return pixels


def run() -> None:
    client = DdpClient(PanelConfig())
    display = SystemStatusDisplay()
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
