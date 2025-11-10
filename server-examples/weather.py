#!/usr/bin/env python3
"""
NOAA temperature demo for the LED Pixel Wall.

Periodically fetches the latest hourly forecast temperature in Fahrenheit
from the National Weather Service (api.weather.gov) and displays it on the
10×5 pixel wall via DDP. A --test-backgrounds mode cycles through all
weather animations for quick visual validation.
"""

import argparse
import json
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta, time as dtime

from PIL import Image

CONTROLLER_IP = "192.168.86.32"
CONTROLLER_PORT = 4048
PANEL_WIDTH = 10
PANEL_HEIGHT = 5
DDP_SEQUENCE_MAX = 255
RETRY_INTERVAL_SEC = 60.0

LOCATION_QUERY = "Cary, NC"

FETCH_INTERVAL_SEC = 300.0
FRAME_INTERVAL_SEC = 1.0

# NOAA requires a descriptive User-Agent with contact details.
CONTACT_EMAIL = "contact@example.com"
USER_AGENT = f"led-pixel-wall-thermometer/1.0 ({CONTACT_EMAIL})"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
SUN_API_URL = "https://api.sunrise-sunset.org/json"

SERPENTINE = True

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

REQUEST_TIMEOUT = 10
OBS_MAX_AGE_SECONDS = 3600
DAY_DIGIT_COLOR = (255, 220, 60)
NIGHT_DIGIT_COLOR = (200, 200, 200)
FALLBACK_DAY_COLOR = (80, 120, 80)
FALLBACK_NIGHT_COLOR = (0, 30, 0)
DEFAULT_ANIMATION_KEY = "clear"
TEST_MODE_TEMPERATURE = 72
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
    "rain_sleet": "sleet",
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
FALLBACK_DAY_FRAME = [FALLBACK_DAY_COLOR] * (PANEL_WIDTH * PANEL_HEIGHT)
FALLBACK_NIGHT_FRAME = [FALLBACK_NIGHT_COLOR] * (PANEL_WIDTH * PANEL_HEIGHT)
FALLBACK_DURATIONS = [FRAME_INTERVAL_SEC]
FRAME_CACHE: Dict[
    Tuple[str, bool],
    Tuple[List[List[Tuple[int, int, int]]], List[float], str],
] = {}


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


class SunTracker:
    def __init__(self, lat: float, lon: float, tzinfo):
        self.lat = lat
        self.lon = lon
        self.tzinfo = tzinfo
        self.sunrise = datetime.now(tzinfo)
        self.sunset = datetime.now(tzinfo)
        self.refresh_ts = 0.0
        self.refresh()

    def refresh(self) -> None:
        self.sunrise, self.sunset, self.refresh_ts = _fetch_sun_cycle(
            self.lat, self.lon, self.tzinfo
        )

    def update_if_needed(self) -> None:
        if time.time() >= self.refresh_ts:
            try:
                self.refresh()
            except Exception as exc:
                print(f"Failed to refresh sunrise/sunset data: {exc}")
                self.refresh_ts = time.time() + 3600

    def is_day(self) -> bool:
        return _is_daytime(datetime.now(self.tzinfo), self.sunrise, self.sunset)


def _fetch_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json, application/json",
        },
    )
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        charset = resp.headers.get_content_charset() or "utf-8"
        data = resp.read().decode(charset)
    return json.loads(data)


def geocode_location(query: str) -> Tuple[float, float]:
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }
    url = GEOCODER_URL + "?" + urllib.parse.urlencode(params)
    data = _fetch_json(url)
    if not data:
        raise RuntimeError(f"Geocoder returned no matches for '{query}'")
    entry = data[0]
    lat = entry.get("lat")
    lon = entry.get("lon")
    if lat is None or lon is None:
        raise RuntimeError("Geocoder response missing coordinates")
    return float(lat), float(lon)


def _c_to_f(value_c: float) -> float:
    return value_c * 9.0 / 5.0 + 32.0


def _parse_iso_timestamp(value: str) -> Optional[datetime]:
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _fetch_point_properties(lat: float, lon: float) -> dict:
    point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    return _fetch_json(point_url).get("properties", {})


def _fetch_sun_cycle(lat: float, lon: float, tzinfo) -> Tuple[datetime, datetime, float]:
    url = f"{SUN_API_URL}?lat={lat:.4f}&lng={lon:.4f}&formatted=0"
    data = _fetch_json(url)
    results = data.get("results", {})
    sunrise = _parse_iso_timestamp(results.get("sunrise", ""))
    sunset = _parse_iso_timestamp(results.get("sunset", ""))
    if not sunrise or not sunset:
        raise RuntimeError("Sunrise/sunset data missing from API response")
    sunrise_local = sunrise.astimezone(tzinfo)
    sunset_local = sunset.astimezone(tzinfo)
    local_now = datetime.now(tzinfo)
    tomorrow = (local_now + timedelta(days=1)).date()
    midnight_plus = datetime.combine(tomorrow, dtime(0, 0), tzinfo=tzinfo) + timedelta(seconds=1)
    print(
        "Sun cycle: "
        f"sunrise={sunrise_local.isoformat()}, "
        f"sunset={sunset_local.isoformat()} (local)"
    )
    return sunrise_local, sunset_local, midnight_plus.timestamp()


def _is_daytime(local_now: datetime, sunrise: datetime, sunset: datetime) -> bool:
    if sunrise <= sunset:
        return sunrise <= local_now < sunset
    # Polar day/night fallback
    return not (sunset <= local_now < sunrise)


def extract_icon_code(icon_url: Optional[str]) -> str:
    if not icon_url:
        return DEFAULT_ANIMATION_KEY
    try:
        parsed = urllib.parse.urlparse(icon_url)
    except Exception:
        return DEFAULT_ANIMATION_KEY
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return DEFAULT_ANIMATION_KEY
    last_segment = segments[-1]
    base = last_segment.split(",")[0].strip().lower()
    return base or DEFAULT_ANIMATION_KEY


def animation_key_for_icon(icon_code: str) -> str:
    return ICON_CODE_TO_KEY.get(icon_code.lower(), DEFAULT_ANIMATION_KEY)


def fetch_latest_observation(stations_url: str) -> Tuple[Optional[int], Optional[str]]:
    stations = _fetch_json(stations_url)
    for feature in stations.get("features", []):
        station_id = feature.get("id")
        if not station_id:
            continue
        try:
            obs = _fetch_json(f"{station_id}/observations/latest")
        except Exception as exc:
            print(f"Failed to read observation from {station_id}: {exc}")
            continue

        props = obs.get("properties", {})
        temp_obj = props.get("temperature")
        timestamp_str = props.get("timestamp")
        if not (temp_obj and temp_obj.get("value") is not None and timestamp_str):
            continue

        timestamp = _parse_iso_timestamp(timestamp_str)
        age_seconds = None
        if timestamp:
            age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age_seconds > OBS_MAX_AGE_SECONDS:
                print(
                    f"Observation from {station_id} stale "
                    f"({int(age_seconds)}s old); trying next station."
                )
                continue

        unit_code = (temp_obj.get("unitCode") or "").lower()
        temp_value = float(temp_obj["value"])
        if "celsius" in unit_code or unit_code.endswith("degc"):
            temp_f = _c_to_f(temp_value)
        elif "fahrenheit" in unit_code or unit_code.endswith("degf"):
            temp_f = temp_value
        else:
            print(f"Unknown observation unit '{unit_code}', assuming Celsius")
            temp_f = _c_to_f(temp_value)

        print(
            "Fetched NOAA temperature from observation: "
            f"{int(round(temp_f))}°F "
            f"(age {int(age_seconds) if age_seconds is not None else 'unknown'}s,"
            f" station {station_id})"
        )
        icon_url = props.get("icon") or ""
        icon_code = extract_icon_code(icon_url)
        return int(round(temp_f)), icon_code

    print("No fresh observations available.")
    return None, None


def fetch_observation_temp_and_icon(stations_url: str) -> Tuple[int, str]:
    temp, icon_code = fetch_latest_observation(stations_url)
    if temp is None:
        raise RuntimeError("No fresh observations available")
    return temp, icon_code or DEFAULT_ANIMATION_KEY


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


def build_ddp_packet(sequence: int, payload: bytes) -> bytes:
    """
    Construct a DDP packet with sequence byte.
    We only send a single buffer (data ID 0) starting at offset 0.
    """
    flags_version = 0x41  # data flag + v1
    data_type = 0x01  # packed RGB
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
        0x00,  # timecode (unused)
    ])
    return header + payload


def pixels_to_bytes(pixels: List[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)


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
    if cache_key in FRAME_CACHE:
        return FRAME_CACHE[cache_key]

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
            FRAME_CACHE[cache_key] = (frames, durations, path)
            return FRAME_CACHE[cache_key]
        except Exception as exc:
            print(f"Failed to load background '{path}': {exc}")

    fallback_frames = [FALLBACK_DAY_FRAME] if is_daytime else [FALLBACK_NIGHT_FRAME]
    source = f"fallback-{variant}"
    print(f"Using fallback background for {variant} '{animation_key}'.")
    FRAME_CACHE[cache_key] = (fallback_frames, FALLBACK_DURATIONS[:], source)
    return FRAME_CACHE[cache_key]


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
    frame_pixels: List[Tuple[int, int, int]],
    digit_color: Tuple[int, int, int],
    current_temp: Optional[int],
    error_state: bool,
) -> List[Tuple[int, int, int]]:
    if current_temp is not None:
        frame = render_temperature(current_temp, frame_pixels, digit_color)
    else:
        frame = frame_pixels
    if error_state:
        idx = serpentine_index(0, 0)
        frame[idx] = (255, 0, 0)
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LED wall weather display")
    parser.add_argument(
        "--controller-ip",
        default=CONTROLLER_IP,
        help=f"Controller IP address (default: {CONTROLLER_IP})",
    )
    parser.add_argument(
        "--controller-port",
        type=int,
        default=CONTROLLER_PORT,
        help=f"Controller UDP port (default: {CONTROLLER_PORT})",
    )
    parser.add_argument(
        "--test-backgrounds",
        action="store_true",
        help="Cycle through every background animation instead of fetching NOAA data.",
    )
    return parser.parse_args()


def run_background_test(args: argparse.Namespace) -> None:
    backgrounds: List[
        Tuple[str, List[List[Tuple[int, int, int]]], List[float], bool]
    ] = []
    for key, variants in ICON_ANIMATIONS.items():
        for is_day, variant_name in ((True, "day"), (False, "night")):
            if variant_name not in variants:
                continue
            frames, durations, source = get_background_frames(key, is_day)
            label = f"{key}-{variant_name} ({source})"
            backgrounds.append((label, frames, durations, is_day))

    backgrounds.append((
        "fallback-day",
        [FALLBACK_DAY_FRAME],
        FALLBACK_DURATIONS[:],
        True,
    ))
    backgrounds.append((
        "fallback-night",
        [FALLBACK_NIGHT_FRAME],
        FALLBACK_DURATIONS[:],
        False,
    ))

    if not backgrounds:
        print("No backgrounds available for testing.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence = 0
    print("Entering background test mode. Press Ctrl-C to stop.")
    try:
        while True:
            for label, frames, durations, is_day in backgrounds:
                digit_color = DAY_DIGIT_COLOR if is_day else NIGHT_DIGIT_COLOR
                print(f"Displaying '{label}' with digit color {digit_color}")
                cycle_duration = sum(durations) if durations else FRAME_INTERVAL_SEC * len(frames)
                min_duration = max(3.0, 2.0 * cycle_duration)
                start_time = time.time()
                frame_idx = 0
                while True:
                    base_pixels = frames[frame_idx]
                    frame = render_temperature(TEST_MODE_TEMPERATURE, base_pixels, digit_color)
                    payload = pixels_to_bytes(frame)
                    packet = build_ddp_packet(sequence, payload)
                    sock.sendto(packet, (args.controller_ip, args.controller_port))
                    sequence = (sequence + 1) % (DDP_SEQUENCE_MAX + 1)
                    if durations:
                        duration = durations[frame_idx % len(durations)]
                    else:
                        duration = FRAME_INTERVAL_SEC
                    time.sleep(max(duration, 0.01))
                    frame_idx = (frame_idx + 1) % len(frames)
                    elapsed = time.time() - start_time
                    if frame_idx == 0 and elapsed >= min_duration:
                        break
    except KeyboardInterrupt:
        print("Background test stopped.")
    finally:
        sock.close()


def run_weather_display(args: argparse.Namespace) -> None:
    controller_ip = args.controller_ip
    controller_port = args.controller_port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence = 0
    last_fetch = 0.0
    current_temp: Optional[int] = None
    icon_key = DEFAULT_ANIMATION_KEY
    error_state = False
    local_tz = datetime.now().astimezone().tzinfo

    try:
        lat, lon = geocode_location(LOCATION_QUERY)
        print(f"Geocoded '{LOCATION_QUERY}' -> lat={lat:.4f}, lon={lon:.4f}")
    except Exception as exc:
        raise SystemExit(f"Failed to geocode '{LOCATION_QUERY}': {exc}")

    properties = _fetch_point_properties(lat, lon)
    stations_url = properties.get("observationStations")
    if not stations_url:
        raise SystemExit("Point metadata missing observation stations URL")

    sun_tracker = SunTracker(lat, lon, local_tz)
    state = build_display_state(icon_key, sun_tracker.is_day())

    try:
        while True:
            sun_tracker.update_if_needed()
            is_daytime = sun_tracker.is_day()
            update_display_state(state, state.background_key, is_daytime)

            now = time.time()
            if current_temp is None or (now - last_fetch) >= FETCH_INTERVAL_SEC:
                try:
                    current_temp, icon_code = fetch_observation_temp_and_icon(stations_url)
                    last_fetch = now
                    icon_key = animation_key_for_icon(icon_code)
                    update_display_state(state, icon_key, is_daytime)
                    print(
                        "Fetched NOAA temperature: "
                        f"{current_temp}°F "
                        f"({'day' if is_daytime else 'night'}) "
                        f"icon='{icon_code}', animation='{state.background_source}'"
                    )
                    error_state = False
                except Exception as exc:
                    print(f"NOAA fetch failed: {exc}")
                    last_fetch = now - (FETCH_INTERVAL_SEC - RETRY_INTERVAL_SEC)
                    error_state = True
            payload = pixels_to_bytes(build_frame_pixels(
                state.frames[state.frame_index][:],
                state.digit_color,
                current_temp,
                error_state))
            packet = build_ddp_packet(sequence, payload)
            sock.sendto(packet, (controller_ip, controller_port))
            sequence = (sequence + 1) % (DDP_SEQUENCE_MAX + 1)
            duration = state.next_duration()
            state.advance_frame()
            sleep_duration = min(RETRY_INTERVAL_SEC, duration) if error_state else duration
            time.sleep(max(sleep_duration, 0.01))
    except KeyboardInterrupt:
        print("Stopping weather display.")
    finally:
        sock.close()


def main() -> None:
    args = parse_args()
    if args.test_backgrounds:
        run_background_test(args)
    else:
        run_weather_display(args)


if __name__ == "__main__":
    main()
