#!/usr/bin/env python3
"""
Generate animated weather background PNGs for the LED wall.

Outputs the core asset set:
  - clear-day.png / clear-night.png
  - rain-day.png / rain-night.png
  - snow-day.png / snow-night.png
  - sleet-day.png / sleet-night.png
  - thunder-day.png / thunder-night.png
  - fog-day.png / fog-night.png
  - severe.png

Usage:
    ./generate_weather_backgrounds.py --width 10 --height 5 --output-dir assets/
"""

import argparse
import math
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from PIL import Image

DAY_COLOR = (0, 80, 255)        # Bright blue sky
NIGHT_COLOR = (0, 0, 0)         # Unlit / night
RAIN_DROP_COLOR = (220, 240, 255)
RAIN_TAIL_INTENSITY = (1.0, 0.65, 0.4, 0.2)
RAIN_FRAME_DURATION_MS = 120
PRECIP_DAY_CLOUD = (50, 50, 50)
PRECIP_DAY_SKY = (50, 50, 200)
SNOW_TAIL_INTENSITY = (1.0,)
SNOW_FRAME_DURATION_MS = 270
SLEET_TAIL_INTENSITY = (1.0,)
SLEET_FRAME_DURATION_MS = 30
THUNDER_LIGHTNING_FRAMES = 2
SEVERE_FRAME_COUNT = 30
SEVERE_FRAME_DURATION_MS = 50
SEVERE_INNER_COLOR = (40, 0, 0)
SEVERE_OUTER_COLOR = (255, 48, 48)
FOG_FRAME_COUNT = 36
FOG_FRAME_DURATION_MS = 120
FOG_DAY_BASE = 150
FOG_DAY_RANGE = 100
FOG_NIGHT_BASE = 5
FOG_NIGHT_RANGE = 45


def create_png(path: Path, width: int, height: int, color: tuple[int, int, int]) -> None:
    """Create a solid-color PNG at the given path."""
    image = Image.new("RGB", (width, height), color)
    image.save(path, format="PNG")


def _build_gradient_rows(
    height: int,
    cloud_color: tuple[int, int, int],
    sky_color: tuple[int, int, int],
    top_fraction: float = 0.3,
) -> List[Tuple[int, int, int]]:
    rows: List[Tuple[int, int, int]] = []
    for y in range(height):
        if height == 1:
            raw_t = 0.0
        else:
            raw_t = y / (height - 1)

        if raw_t <= top_fraction:
            t = 0.0
        else:
            denominator = max(1e-6, 1.0 - top_fraction)
            t = (raw_t - top_fraction) / denominator

        rows.append(tuple(
            int(cloud_color[c] + (sky_color[c] - cloud_color[c]) * t)
            for c in range(3)
        ))
    return rows


def _build_drop_schedule(width: int, drop_span: int) -> List[tuple[int, int]]:
    if width == 1:
        column_order = [0]
    elif width == 2:
        column_order = [0, 1]
    else:
        base_columns = [0, width // 2, width - 1]
        for _ in range(width):
            base_columns.append((base_columns[-1] + 3) % width)
        column_order = base_columns

    spacing = max(2, drop_span // 2)
    jitter = max(1, spacing // 3)

    schedule: List[tuple[int, int]] = []
    current_start = 0
    for column in column_order:
        schedule.append((current_start, column))
        current_start += spacing
        current_start += ((current_start // spacing) % jitter)
    return schedule


def create_percipitation_png(
    path: Path,
    width: int,
    height: int,
    cloud_color: tuple[int, int, int],
    sky_color: tuple[int, int, int],
    tail_intensity: Iterable[float] = RAIN_TAIL_INTENSITY,
    frame_duration_ms: int = RAIN_FRAME_DURATION_MS,
    with_lightning: bool = False,
) -> None:
    """Create a looping precipitation animation as an animated PNG."""
    if width < 1 or height < 1:
        raise ValueError("Width and height must be positive for precipitation animation.")

    drop_span = height
    tail_values = list(tail_intensity) or [1.0]
    schedule = _build_drop_schedule(width, drop_span)
    total_frames = schedule[-1][0] + drop_span
    gradient_rows = _build_gradient_rows(height, cloud_color, sky_color)

    frames: List[Image.Image] = []
    for frame_index in range(total_frames):
        frame = Image.new("RGB", (width, height))
        pixels = frame.load()
        for y in range(height):
            row_color = gradient_rows[y]
            for x in range(width):
                pixels[x, y] = row_color
        for start, column in schedule:
            progress = frame_index - start
            if -len(tail_values) < progress < drop_span:
                for tail_index, intensity in enumerate(tail_values):
                    y = progress - tail_index
                    if 0 <= column < width and 0 <= y < height:
                        background = gradient_rows[y]
                        blend = tuple(
                            min(255, int(background[c] + (RAIN_DROP_COLOR[c] - background[c]) * intensity))
                            for c in range(3)
                        )
                        pixels[column, y] = blend
        frames.append(frame)

    if with_lightning and frames:
        lightning_frames = frames * THUNDER_LIGHTNING_FRAMES
        mid = len(lightning_frames) // 2
        flash_indices = [mid, min(mid + 1, len(lightning_frames) - 1)]
        for idx in flash_indices:
            lightning_frames[idx] = Image.new("RGB", (width, height), (255, 255, 255))
        frames = lightning_frames

    first, *rest = frames
    first.save(
        path,
        save_all=True,
        append_images=rest,
        loop=0,
        duration=frame_duration_ms,
    )


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


PhaseGenerator = Callable[[int, int], Tuple[float, float, Optional[float]]]
PixelMapper = Callable[[int, int, float, Optional[float]], Tuple[int, int, int]]


def _build_phase_field(
    width: int,
    height: int,
    generator: PhaseGenerator,
) -> tuple[List[List[float]], List[List[float]], float, Optional[List[List[float]]]]:
    cos_field: List[List[float]] = []
    sin_field: List[List[float]] = []
    extra_field: List[List[float]] = []
    amplitude_max = 1e-6
    extras_present = False

    for y in range(height):
        cos_row: List[float] = []
        sin_row: List[float] = []
        extra_row: List[float] = []
        for x in range(width):
            cos_val, sin_val, extra = generator(x, y)
            cos_row.append(cos_val)
            sin_row.append(sin_val)
            extra_row.append(extra if extra is not None else 0.0)
            extras_present = extras_present or (extra is not None)
            amplitude_max = max(amplitude_max, math.hypot(cos_val, sin_val))
        cos_field.append(cos_row)
        sin_field.append(sin_row)
        extra_field.append(extra_row)

    return cos_field, sin_field, amplitude_max, extra_field if extras_present else None


def _render_phase_field(
    path: Path,
    width: int,
    height: int,
    frame_count: int,
    frame_duration_ms: int,
    cos_field: List[List[float]],
    sin_field: List[List[float]],
    amplitude_max: float,
    extra_field: Optional[List[List[float]]],
    pixel_fn: PixelMapper,
) -> None:
    amplitude = max(amplitude_max, 1e-6)
    frames: List[Image.Image] = []
    for frame_index in range(frame_count):
        phase = (frame_index + 0.5) / frame_count
        theta = 2.0 * math.pi * phase
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        frame = Image.new("RGB", (width, height))
        pixels = frame.load()
        for y in range(height):
            for x in range(width):
                mix = (
                    cos_field[y][x] * cos_theta +
                    sin_field[y][x] * sin_theta
                ) / amplitude
                mix = max(-1.0, min(1.0, mix))
                extra = extra_field[y][x] if extra_field is not None else None
                pixels[x, y] = pixel_fn(x, y, mix, extra)
        frames.append(frame)

    first, *rest = frames
    first.save(
        path,
        save_all=True,
        append_images=rest,
        loop=0,
        duration=frame_duration_ms,
    )


def create_severe_animation(path: Path, width: int, height: int) -> None:
    frames: List[Image.Image] = []
    for frame_index in range(SEVERE_FRAME_COUNT):
        phase = frame_index / SEVERE_FRAME_COUNT
        intensity = 0.3 + 0.7 * (0.5 * (1 + math.sin(2 * math.pi * phase)))
        color = _lerp_color(SEVERE_INNER_COLOR, SEVERE_OUTER_COLOR, intensity)
        frame = Image.new("RGB", (width, height), color)
        frames.append(frame)

    first, *rest = frames
    first.save(
        path,
        save_all=True,
        append_images=rest,
        loop=0,
        duration=SEVERE_FRAME_DURATION_MS,
    )


def create_fog_animation(path: Path, width: int, height: int, *, is_day: bool) -> None:
    base = FOG_DAY_BASE if is_day else FOG_NIGHT_BASE
    value_range = FOG_DAY_RANGE if is_day else FOG_NIGHT_RANGE

    def generator(x: int, y: int) -> Tuple[float, float, Optional[float]]:
        nx = x / max(1.0, width - 1)
        ny = y / max(1.0, height - 1)
        cos_val = (
            math.sin((nx * 1.8 + ny * 0.6) * math.pi * 2.0)
            + math.sin(((nx - ny) * 1.3) * math.pi * 2.0)
        )
        sin_val = (
            math.sin((ny * 1.5) * math.pi * 2.0)
            + math.sin(((nx + ny * 0.5) * 1.1) * math.pi * 2.0)
        )
        return cos_val, sin_val, None

    cos_field, sin_field, amplitude_max, _ = _build_phase_field(width, height, generator)

    def pixel_fn(_: int, __: int, mix: float, ___: Optional[float]) -> tuple[int, int, int]:
        value = base + value_range * (0.5 + 0.5 * mix)
        brightness = max(0, min(255, int(round(value))))
        return (brightness, brightness, brightness)

    _render_phase_field(
        path,
        width,
        height,
        FOG_FRAME_COUNT,
        FOG_FRAME_DURATION_MS,
        cos_field,
        sin_field,
        amplitude_max,
        None,
        pixel_fn,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate baseline weather background PNGs."
    )
    parser.add_argument(
        "--width",
        type=int,
        default=10,
        help="Image width in pixels (default: 10).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=5,
        help="Image height in pixels (default: 5).",
    )
    parser.add_argument(
        "--output-dir",
        default="weather-backgrounds",
        help="Directory to write generated images (created if missing).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("Width and height must be positive integers.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    day_path = output_dir / "clear-day.png"
    night_path = output_dir / "clear-night.png"
    rain_day_path = output_dir / "rain-day.png"
    rain_night_path = output_dir / "rain-night.png"
    snow_day_path = output_dir / "snow-day.png"
    snow_night_path = output_dir / "snow-night.png"
    sleet_day_path = output_dir / "sleet-day.png"
    sleet_night_path = output_dir / "sleet-night.png"
    thunder_day_path = output_dir / "thunder-day.png"
    thunder_night_path = output_dir / "thunder-night.png"
    fog_day_path = output_dir / "fog-day.png"
    fog_night_path = output_dir / "fog-night.png"
    severe_path = output_dir / "severe.png"

    create_png(day_path, args.width, args.height, DAY_COLOR)
    create_png(night_path, args.width, args.height, NIGHT_COLOR)
    create_percipitation_png(
        rain_day_path,
        args.width,
        args.height,
        PRECIP_DAY_CLOUD,
        PRECIP_DAY_SKY,
        tail_intensity=RAIN_TAIL_INTENSITY,
        frame_duration_ms=RAIN_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        rain_night_path,
        args.width,
        args.height,
        NIGHT_COLOR,
        NIGHT_COLOR,
        tail_intensity=RAIN_TAIL_INTENSITY,
        frame_duration_ms=RAIN_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        snow_day_path,
        args.width,
        args.height,
        PRECIP_DAY_CLOUD,
        PRECIP_DAY_SKY,
        tail_intensity=SNOW_TAIL_INTENSITY,
        frame_duration_ms=SNOW_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        snow_night_path,
        args.width,
        args.height,
        NIGHT_COLOR,
        NIGHT_COLOR,
        tail_intensity=SNOW_TAIL_INTENSITY,
        frame_duration_ms=SNOW_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        sleet_day_path,
        args.width,
        args.height,
        PRECIP_DAY_CLOUD,
        PRECIP_DAY_SKY,
        tail_intensity=SLEET_TAIL_INTENSITY,
        frame_duration_ms=SLEET_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        sleet_night_path,
        args.width,
        args.height,
        NIGHT_COLOR,
        NIGHT_COLOR,
        tail_intensity=SLEET_TAIL_INTENSITY,
        frame_duration_ms=SLEET_FRAME_DURATION_MS,
    )
    create_percipitation_png(
        thunder_day_path,
        args.width,
        args.height,
        PRECIP_DAY_CLOUD,
        PRECIP_DAY_SKY,
        tail_intensity=RAIN_TAIL_INTENSITY,
        frame_duration_ms=RAIN_FRAME_DURATION_MS,
        with_lightning=True,
    )
    create_percipitation_png(
        thunder_night_path,
        args.width,
        args.height,
        NIGHT_COLOR,
        NIGHT_COLOR,
        tail_intensity=RAIN_TAIL_INTENSITY,
        frame_duration_ms=RAIN_FRAME_DURATION_MS,
        with_lightning=True,
    )
    create_fog_animation(
        fog_day_path,
        args.width,
        args.height,
        is_day=True,
    )
    create_fog_animation(
        fog_night_path,
        args.width,
        args.height,
        is_day=False,
    )
    create_severe_animation(
        severe_path,
        args.width,
        args.height,
    )

    print(f"Generated backgrounds in {output_dir.resolve()}")


if __name__ == "__main__":
    main()
