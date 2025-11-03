#!/usr/bin/env python3
"""Real-time audio visualizer that streams to the LED wall over DDP.

Captures system audio via sounddevice (PulseAudio/ALSA monitor on Linux) and
converts the spectrum into vertical bars for each column on the panel.
"""

from __future__ import annotations

import argparse
import math
import queue
import socket
import sys
import time
from typing import List, Optional, Sequence, Tuple

import numpy as np
import sounddevice as sd

CONTROLLER_IP = "192.168.86.32"
CONTROLLER_PORT = 4048
PANEL_WIDTH = 10
PANEL_HEIGHT = 5
DDP_SEQUENCE_MAX = 255
SAMPLE_RATE = 48_000
FFT_SIZE = 2048
SPECTRUM_SMOOTHING = 0.6
BASELINE_SMOOTHING = 0.995
THRESHOLD_DB = 8.0
DYNAMIC_RANGE_DB = 18.0
FLOOR_DB = -80.0
PEAK_DECAY = 0.92
TARGET_FPS = 30.0
BEAT_ENVELOPE_DECAY = 0.55
BEAT_BASELINE_DECAY = 0.995
BEAT_THRESHOLD_RATIO = 1.8
BEAT_COOLDOWN_FRAMES = max(1, int(TARGET_FPS * 0.15))
BEAT_PULSE_DECAY = 0.88


def serpentine_index(x: int, y: int, width: int, height: int) -> int:
    hw_y = height - 1 - y
    if hw_y % 2 == 0:
        return hw_y * width + x
    return hw_y * width + (width - 1 - x)


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


def pixels_to_bytes(pixels: Sequence[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)


class SpectrumAnalyzer:
    def __init__(self, width: int) -> None:
        self.width = width
        self.window = np.hanning(FFT_SIZE)
        self._levels = np.zeros(width, dtype=np.float32)
        self._freq_edges = self._compute_frequency_edges()
        self._baseline_db = np.full(width, FLOOR_DB, dtype=np.float32)
        self._baseline_initialized = np.zeros(width, dtype=bool)

    def _compute_frequency_edges(self) -> np.ndarray:
        nyquist = SAMPLE_RATE / 2.0
        start_hz = 60.0
        end_hz = max(start_hz * 2.0, nyquist)
        edges = np.geomspace(start_hz, end_hz, num=self.width + 1)
        bin_freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
        return np.clip(edges, bin_freqs[1], bin_freqs[-1])

    @property
    def levels(self) -> np.ndarray:
        return self._levels

    def process(self, mono_block: np.ndarray) -> None:
        if mono_block.size != FFT_SIZE:
            if mono_block.size < FFT_SIZE:
                padded = np.zeros(FFT_SIZE, dtype=np.float32)
                padded[: mono_block.size] = mono_block
                mono_block = padded
            else:
                mono_block = mono_block[:FFT_SIZE]

        windowed = mono_block * self.window
        spectrum = np.fft.rfft(windowed)
        magnitude = np.abs(spectrum) + 1e-9
        amps_db = 20.0 * np.log10(magnitude)

        next_levels = np.zeros_like(self._levels)
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)

        for idx in range(self.width):
            low = self._freq_edges[idx]
            high = self._freq_edges[idx + 1]
            mask = (freqs >= low) & (freqs < high)
            if not np.any(mask):
                continue
            mean_db = float(np.mean(amps_db[mask]))
            baseline = float(self._baseline_db[idx])
            if not self._baseline_initialized[idx]:
                baseline = mean_db
                self._baseline_initialized[idx] = True
            elif mean_db < baseline:
                baseline = mean_db
            else:
                baseline = baseline * BASELINE_SMOOTHING + mean_db * (1.0 - BASELINE_SMOOTHING)
            self._baseline_db[idx] = baseline

            delta_db = mean_db - baseline - THRESHOLD_DB
            normalized = delta_db / DYNAMIC_RANGE_DB
            next_levels[idx] = np.clip(normalized, 0.0, 1.0)

        self._levels = self._levels * SPECTRUM_SMOOTHING + next_levels * (1.0 - SPECTRUM_SMOOTHING)


class ColumnRenderer:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._peak_levels = np.zeros(width, dtype=np.float32)

    def render(self, levels: np.ndarray) -> List[Tuple[int, int, int]]:
        pixels: List[Tuple[int, int, int]] = [(0, 0, 0)] * (self.width * self.height)

        self._peak_levels *= PEAK_DECAY
        self._peak_levels = np.maximum(self._peak_levels, levels)

        for x in range(self.width):
            level = float(levels[x])
            peak = float(self._peak_levels[x])
            filled_rows = int(round(level * self.height))
            peak_row = int(round(peak * self.height))

            for y in range(self.height):
                draw_y = self.height - 1 - y
                idx = serpentine_index(x, draw_y, self.width, self.height)

                if y < filled_rows:
                    ratio = (y + 1) / self.height
                    color = hsv_to_rgb(0.58 - 0.58 * level, 1.0, 0.3 + 0.7 * ratio)
                    pixels[idx] = color
                elif y == peak_row and peak > 0.0:
                    pixels[idx] = (255, 255, 255)

        return pixels


class BeatDetector:
    def __init__(self) -> None:
        self.envelope = 0.0
        self.baseline = 1e-6
        self.cooldown = 0
        self.intensity = 0.0

    def process(self, mono_block: Optional[np.ndarray]) -> None:
        self.intensity *= BEAT_PULSE_DECAY
        if mono_block is None:
            if self.cooldown > 0:
                self.cooldown -= 1
            return

        energy = float(np.mean(mono_block * mono_block))
        self.envelope = self.envelope * BEAT_ENVELOPE_DECAY + energy * (1.0 - BEAT_ENVELOPE_DECAY)
        self.baseline = self.baseline * BEAT_BASELINE_DECAY + self.envelope * (1.0 - BEAT_BASELINE_DECAY)
        self.baseline = max(self.baseline, 1e-9)

        triggered = False
        if self.cooldown > 0:
            self.cooldown -= 1
        elif self.envelope > self.baseline * BEAT_THRESHOLD_RATIO:
            triggered = True
            self.cooldown = BEAT_COOLDOWN_FRAMES

        if triggered:
            excess = self.envelope - self.baseline
            denom = max(self.baseline * (BEAT_THRESHOLD_RATIO - 1.0), 1e-9)
            strength = np.clip(excess / denom, 0.0, 1.0)
            self.intensity = max(self.intensity, strength)

    @property
    def pulse(self) -> float:
        return float(np.clip(self.intensity, 0.0, 1.0))


class BeatPulseRenderer:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cx = (width - 1) / 2.0
        self.cy = (height - 1) / 2.0
        self.max_dist = max(
            math.hypot(x - self.cx, y - self.cy) for x in range(width) for y in range(height)
        )

    def render(self, pulse_strength: float) -> List[Tuple[int, int, int]]:
        if pulse_strength <= 0.0:
            return [(0, 0, 0)] * (self.width * self.height)

        pixels: List[Tuple[int, int, int]] = [(0, 0, 0)] * (self.width * self.height)
        scaled_strength = min(1.0, pulse_strength)

        for logical_y in range(self.height):
            actual_y = self.height - 1 - logical_y
            for x in range(self.width):
                idx = serpentine_index(x, actual_y, self.width, self.height)
                dist = math.hypot(x - self.cx, logical_y - self.cy)
                dist_norm = dist / self.max_dist
                falloff = max(0.0, scaled_strength - dist_norm)
                if falloff <= 0.0:
                    continue
                brightness = min(1.0, falloff * 1.6)
                hue = (0.58 - 0.25 * dist_norm) % 1.0
                saturation = min(1.0, 0.65 + 0.35 * falloff)
                pixels[idx] = hsv_to_rgb(hue, saturation, brightness)

        return pixels


class DDPClient:
    def __init__(self, ip: str, port: int) -> None:
        self.addr = (ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sequence = 0

    def send(self, pixels: Sequence[Tuple[int, int, int]]) -> None:
        payload = pixels_to_bytes(pixels)
        header = bytes(
            [
                0x41,
                self.sequence & 0xFF,
                0x01,
                0x00,
                0x00,
                (len(payload) >> 8) & 0xFF,
                len(payload) & 0xFF,
                0x00,
                0x00,
                0x00,
            ]
        )
        self.sock.sendto(header + payload, self.addr)
        self.sequence = (self.sequence + 1) % (DDP_SEQUENCE_MAX + 1)


def list_audio_devices() -> None:
    try:
        devices = sd.query_devices()
    except Exception as exc:  # pragma: no cover - device query errors
        print(f"Failed to query audio devices: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Available input devices:")
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue
        print(
            f"{idx}: {dev['name']}  (inputs={dev['max_input_channels']}, "
            f"default_samplerate={dev['default_samplerate']:.0f})"
        )


def drain_queue(q: "queue.Queue[np.ndarray]") -> Optional[np.ndarray]:
    chunk: Optional[np.ndarray] = None
    try:
        while True:
            chunk = q.get_nowait()
    except queue.Empty:
        pass
    return chunk


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audio-driven LED wall visualizer.")
    parser.add_argument("--ip", default=CONTROLLER_IP, help="Controller IP address.")
    parser.add_argument("--port", type=int, default=CONTROLLER_PORT, help="Controller DDP port.")
    parser.add_argument(
        "--device", default=None, help="Audio input device name or index (use --list-devices)."
    )
    parser.add_argument(
        "--mode",
        choices=["bars", "beat"],
        default="bars",
        help="Visualization style: column bars or beat pulse.",
    )
    parser.add_argument("--list-devices", action="store_true", help="List input devices and exit.")

    args = parser.parse_args(argv)

    if args.list_devices:
        list_audio_devices()
        return 0

    analyzer: Optional[SpectrumAnalyzer]
    renderer: Optional[ColumnRenderer]
    beat_detector: Optional[BeatDetector]
    beat_renderer: Optional[BeatPulseRenderer]

    if args.mode == "bars":
        analyzer = SpectrumAnalyzer(PANEL_WIDTH)
        renderer = ColumnRenderer(PANEL_WIDTH, PANEL_HEIGHT)
        beat_detector = None
        beat_renderer = None
    else:
        analyzer = None
        renderer = None
        beat_detector = BeatDetector()
        beat_renderer = BeatPulseRenderer(PANEL_WIDTH, PANEL_HEIGHT)

    ddp = DDPClient(args.ip, args.port)
    audio_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=8)

    def audio_callback(
        indata: np.ndarray, _frames: int, _time_info: dict, status: sd.CallbackFlags
    ) -> None:  # pragma: no cover - real-time callback
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        try:
            audio_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=FFT_SIZE,
        channels=1,
        dtype="float32",
        device=args.device,
        callback=audio_callback,
    )

    frame_interval = 1.0 / max(TARGET_FPS, 1.0)
    print("Starting audio visualizer. Press Ctrl+C to stop.")
    try:
        with stream:
            last_frame = time.perf_counter()
            while True:
                chunk = drain_queue(audio_queue)
                if chunk is not None:
                    mono = np.squeeze(chunk, axis=1)
                    if analyzer:
                        analyzer.process(mono)
                    if beat_detector:
                        beat_detector.process(mono)
                else:
                    if beat_detector:
                        beat_detector.process(None)

                if renderer and analyzer:
                    pixels = renderer.render(analyzer.levels)
                elif beat_renderer and beat_detector:
                    pixels = beat_renderer.render(beat_detector.pulse)
                else:
                    pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
                ddp.send(pixels)

                now = time.perf_counter()
                sleep_time = frame_interval - (now - last_frame)
                last_frame = now
                if sleep_time > 0:
                    time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nStopping audio visualizer.")
    except Exception as exc:
        print(f"Visualizer error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
