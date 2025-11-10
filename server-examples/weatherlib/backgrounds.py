from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PIL import Image

PANEL_WIDTH = 10
PANEL_HEIGHT = 5
SERPENTINE = True
FRAME_INTERVAL_SEC = 1.0
DEFAULT_ANIMATION_KEY = "clear"
DAY_DIGIT_COLOR = (255, 220, 60)
NIGHT_DIGIT_COLOR = (200, 200, 200)

FALLBACK_DAY_COLOR = (80, 120, 80)
FALLBACK_NIGHT_COLOR = (0, 30, 0)
FALLBACK_DAY_FRAME = [FALLBACK_DAY_COLOR] * (PANEL_WIDTH * PANEL_HEIGHT)
FALLBACK_NIGHT_FRAME = [FALLBACK_NIGHT_COLOR] * (PANEL_WIDTH * PANEL_HEIGHT)
FALLBACK_DURATIONS = [FRAME_INTERVAL_SEC]

DIGITS_3x5 = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["1", "1", "1", "1", "1"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "-": ["00", "00", "11", "00", "00"],
    " ": ["000", "000", "000", "000", "000"],
}

ICON_ANIMATIONS = {
    "clear": {
        "day": "weather-backgrounds/clear-day.png",
        "night": "weather-backgrounds/clear-night.png",
    },
    "cloudy": {
        "day": "weather-backgrounds/cloudy-day.png",
        "night": "weather-backgrounds/cloudy-night.png",
    },
    "overcast": {
        "day": "weather-backgrounds/overcast-day.png",
        "night": "weather-backgrounds/overcast-night.png",
    },
    "rain": {
        "day": "weather-backgrounds/rain-day.png",
        "night": "weather-backgrounds/rain-night.png",
    },
    "thunder": {
        "day": "weather-backgrounds/thunder-day.png",
        "night": "weather-backgrounds/thunder-night.png",
    },
    "snow": {
        "day": "weather-backgrounds/snow-day.png",
        "night": "weather-backgrounds/snow-night.png",
    },
    "sleet": {
        "day": "weather-backgrounds/sleet-day.png",
        "night": "weather-backgrounds/sleet-night.png",
    },
    "fog": {
        "day": "weather-backgrounds/fog-day.png",
        "night": "weather-backgrounds/fog-night.png",
    },
    "severe": {
        "day": "weather-backgrounds/severe.png",
        "night": "weather-backgrounds/severe.png",
    },
}

ICON_CODE_TO_KEY = {
    "skc": "clear",
    "few": "clear",
    "wind_skc": "clear",
    "wind_few": "clear",
    "hot": "clear",
    "cold": "clear",
    "sct": "cloudy",
    "bkn": "cloudy",
    "ovc": "overcast",
    "wind_sct": "cloudy",
    "wind_bkn": "cloudy",
    "wind_ovc": "overcast",
    "rain": "rain",
    "rain_showers": "rain",
    "rain_showers_hi": "rain",
    "rain_sleet": "rain",
    "rain_fzra": "rain",
    "rain_snow": "snow",
    "fzra": "rain",
    "tsra": "thunder",
    "tsra_sct": "thunder",
    "tsra_hi": "thunder",
    "sleet": "sleet",
    "snow": "snow",
    "snow_sleet": "snow",
    "snow_fzra": "snow",
    "blizzard": "snow",
    "fog": "fog",
    "dust": "fog",
    "smoke": "fog",
    "haze": "fog",
    "tornado": "severe",
    "hurricane": "severe",
    "tropical_storm": "severe",
}

_FRAME_CACHE: Dict[Tuple[str, bool], Tuple[List[List[Tuple[int, int, int]]], List[float], str]] = {}


@dataclass
class DisplayState:
    frames: List[List[Tuple[int, int, int]]]
    durations: List[float]
    frame_index: int
    digit_color: Tuple[int, int, int]
    background_key: str
    background_source: str
    is_day: bool

    def next_duration(self) -> float:
        if not self.durations:
            return FRAME_INTERVAL_SEC
        return self.durations[self.frame_index % len(self.durations)]

    def advance_frame(self) -> None:
        if self.frames:
            self.frame_index = (self.frame_index + 1) % len(self.frames)


def serpentine_index(x: int, y: int) -> int:
    hw_y = PANEL_HEIGHT - 1 - y
    if SERPENTINE:
        if hw_y % 2 == 0:
            idx = hw_y * PANEL_WIDTH + x
        else:
            idx = hw_y * PANEL_WIDTH + (PANEL_WIDTH - 1 - x)
    else:
        idx = hw_y * PANEL_WIDTH + x
    return idx


def load_background_frames(path: str) -> Tuple[List[List[Tuple[int, int, int]]], List[float]]:
    image = Image.open(path)
    frames: List[List[Tuple[int, int, int]]] = []
    durations: List[float] = []
    try:
        frame_count = getattr(image, "n_frames", 1)
        for idx in range(frame_count):
            image.seek(idx)
            rgb = image.convert("RGB")
            if rgb.size != (PANEL_WIDTH, PANEL_HEIGHT):
                raise RuntimeError(f"Background image must be {PANEL_WIDTH}x{PANEL_HEIGHT}")
            raw = list(rgb.getdata())
            ordered = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
            for y in range(PANEL_HEIGHT):
                for x in range(PANEL_WIDTH):
                    ordered[serpentine_index(x, y)] = raw[y * PANEL_WIDTH + x]
            frames.append(ordered)
            duration_ms = image.info.get("duration", FRAME_INTERVAL_SEC * 1000.0)
            frame_duration = max(duration_ms / 1000.0, 0.05)
            if frame_count == 1:
                frame_duration = FRAME_INTERVAL_SEC
            durations.append(frame_duration)
    finally:
        image.close()
    if not durations:
        durations = [FRAME_INTERVAL_SEC]
    return frames, durations


def get_background_frames(
    animation_key: str,
    is_daytime: bool,
) -> Tuple[List[List[Tuple[int, int, int]]], List[float], str]:
    cache_key = (animation_key, is_daytime)
    if cache_key in _FRAME_CACHE:
        return _FRAME_CACHE[cache_key]

    variant = "day" if is_daytime else "night"
    lookup_order = [animation_key]
    if animation_key != DEFAULT_ANIMATION_KEY:
        lookup_order.append(DEFAULT_ANIMATION_KEY)

    for key in lookup_order:
        variant_map = ICON_ANIMATIONS.get(key)
        if not variant_map:
            continue
        path = variant_map.get(variant)
        if not path:
            continue
        try:
            frames, durations = load_background_frames(path)
            _FRAME_CACHE[cache_key] = (frames, durations, path)
            return _FRAME_CACHE[cache_key]
        except Exception as exc:
            print(f"Failed to load background '{path}': {exc}")

    fallback_frames = [FALLBACK_DAY_FRAME] if is_daytime else [FALLBACK_NIGHT_FRAME]
    source = f"fallback-{variant}"
    print(f"Using fallback background for {variant} '{animation_key}'.")
    _FRAME_CACHE[cache_key] = (fallback_frames, FALLBACK_DURATIONS[:], source)
    return _FRAME_CACHE[cache_key]


def render_temperature(
    temp_f: int,
    base_pixels: List[Tuple[int, int, int]],
    digit_color: Tuple[int, int, int],
) -> List[Tuple[int, int, int]]:
    pixels = base_pixels[:]
    temp_str = str(temp_f)
    glyphs = [DIGITS_3x5.get(ch, DIGITS_3x5[" "]) for ch in temp_str]
    glyph_widths = [len(glyph[0]) if glyph else 0 for glyph in glyphs]

    spacing = 1
    total_width = sum(glyph_widths) + (len(glyphs) - 1) * spacing
    if total_width > PANEL_WIDTH:
        spacing = 0
        total_width = sum(glyph_widths) + (len(glyphs) - 1) * spacing

    start_x = max(((PANEL_WIDTH - total_width) + 1) // 2, 0)

    x = start_x
    for glyph, width in zip(glyphs, glyph_widths):
        for y, row in enumerate(glyph):
            for dx, bit in enumerate(row):
                if bit == "1":
                    px = x + dx
                    if 0 <= px < PANEL_WIDTH and 0 <= y < PANEL_HEIGHT:
                        idx = serpentine_index(px, y)
                        pixels[idx] = digit_color
        x += width + spacing

    return pixels


def build_display_state(icon_key: str, is_daytime: bool) -> DisplayState:
    frames, durations, source = get_background_frames(icon_key, is_daytime)
    digit_color = DAY_DIGIT_COLOR if is_daytime else NIGHT_DIGIT_COLOR
    return DisplayState(
        frames=frames,
        durations=durations,
        frame_index=0,
        digit_color=digit_color,
        background_key=icon_key,
        background_source=source,
        is_day=is_daytime,
    )


def update_display_state(state: DisplayState, icon_key: str, is_daytime: bool) -> None:
    needs_background = (
        icon_key != state.background_key or is_daytime != state.is_day
    )
    if needs_background:
        frames, durations, source = get_background_frames(icon_key, is_daytime)
        state.frames = frames
        state.durations = durations
        state.background_source = source
        state.background_key = icon_key
        state.is_day = is_daytime
        state.frame_index = 0
    state.digit_color = DAY_DIGIT_COLOR if is_daytime else NIGHT_DIGIT_COLOR


def build_frame_pixels(
    state: DisplayState,
    current_temp: Optional[int],
    error_state: bool,
) -> List[Tuple[int, int, int]]:
    base_pixels = state.frames[state.frame_index][:]
    if current_temp is not None:
        frame = render_temperature(current_temp, base_pixels, state.digit_color)
    else:
        frame = base_pixels
    if error_state:
        idx = serpentine_index(0, 0)
        frame[idx] = (255, 0, 0)
    return frame


def iter_background_states_for_test() -> List[Tuple[str, DisplayState]]:
    states: List[Tuple[str, DisplayState]] = []
    for key, variants in ICON_ANIMATIONS.items():
        for is_day, variant_name in ((True, "day"), (False, "night")):
            if variant_name not in variants:
                continue
            frames, durations, source = get_background_frames(key, is_day)
            label = f"{key}-{variant_name} ({source})"
            states.append((
                label,
                DisplayState(
                    frames=frames,
                    durations=durations,
                    frame_index=0,
                    digit_color=DAY_DIGIT_COLOR if is_day else NIGHT_DIGIT_COLOR,
                    background_key=key,
                    background_source=label,
                    is_day=is_day,
                ),
            ))

    states.append((
        "fallback-day",
        DisplayState(
            frames=[FALLBACK_DAY_FRAME],
            durations=FALLBACK_DURATIONS[:],
            frame_index=0,
            digit_color=DAY_DIGIT_COLOR,
            background_key="fallback",
            background_source="fallback-day",
            is_day=True,
        ),
    ))
    states.append((
        "fallback-night",
        DisplayState(
            frames=[FALLBACK_NIGHT_FRAME],
            durations=FALLBACK_DURATIONS[:],
            frame_index=0,
            digit_color=NIGHT_DIGIT_COLOR,
            background_key="fallback",
            background_source="fallback-night",
            is_day=False,
        ),
    ))
    return states


def animation_key_for_icon(icon_code: str) -> str:
    return ICON_CODE_TO_KEY.get(icon_code.lower(), DEFAULT_ANIMATION_KEY)
