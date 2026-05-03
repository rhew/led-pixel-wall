from typing import Tuple


def blend_color(color: Tuple[int, int, int], scale: float) -> Tuple[int, int, int]:
    scale = max(0.0, min(1.0, scale))
    return (
        int(color[0] * scale),
        int(color[1] * scale),
        int(color[2] * scale),
    )


def lerp_color(
    start: Tuple[int, int, int],
    end: Tuple[int, int, int],
    t: float,
) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(start[0] + (end[0] - start[0]) * t),
        int(start[1] + (end[1] - start[1]) * t),
        int(start[2] + (end[2] - start[2]) * t),
    )


def usage_color(percent: float) -> Tuple[int, int, int]:
    low = (0, 180, 24)
    mid = (240, 150, 0)
    high = (255, 16, 0)
    if percent <= 50.0:
        return lerp_color(low, mid, percent / 50.0)
    return lerp_color(mid, high, (percent - 50.0) / 50.0)
