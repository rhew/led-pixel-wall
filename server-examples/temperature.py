#!/usr/bin/env python3
"""
NOAA temperature demo for the LED Pixel Wall.

Periodically fetches the latest hourly forecast temperature in Fahrenheit
from the National Weather Service (api.weather.gov) and displays it on the
10×5 pixel wall via DDP.
"""

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Tuple

CONTROLLER_IP = "192.168.86.32"
CONTROLLER_PORT = 4048
PANEL_WIDTH = 10
PANEL_HEIGHT = 5
DDP_SEQUENCE_MAX = 255
RETRY_INTERVAL_SEC = 60.0

LOCATION_QUERY = "Cary, NC"

FETCH_INTERVAL_SEC = 300.0

# NOAA requires a descriptive User-Agent with contact details.
CONTACT_EMAIL = "contact@example.com"
USER_AGENT = f"led-pixel-wall-thermometer/1.0 ({CONTACT_EMAIL})"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"

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


def fetch_noaa_temperature(lat: float, lon: float) -> int:
    point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    point_data = _fetch_json(point_url)
    properties = point_data.get("properties", {})

    stations_url = properties.get("observationStations")
    if stations_url:
        try:
            stations = _fetch_json(stations_url)
            station_features = stations.get("features", [])
            if station_features:
                station_id = station_features[0].get("id")
                if station_id:
                    latest_obs_url = f"{station_id}/observations/latest"
                    obs_data = _fetch_json(latest_obs_url)
                    obs_props = obs_data.get("properties", {})
                    temp_obj = obs_props.get("temperature")
                    if temp_obj and temp_obj.get("value") is not None:
                        temp_c = float(temp_obj["value"])
                        temp_f = _c_to_f(temp_c)
                        return int(round(temp_f))
        except Exception as exc:
            print(f"Observation fetch failed, falling back to forecast: {exc}")

    forecast_url = properties.get("forecastHourly") or properties.get("forecast")
    if not forecast_url:
        raise RuntimeError("No forecast or observation URL in point metadata")

    forecast_data = _fetch_json(forecast_url)
    periods = forecast_data.get("properties", {}).get("periods", [])
    if not periods:
        raise RuntimeError("No forecast periods returned")

    period = periods[0]
    temp = period.get("temperature")
    unit = period.get("temperatureUnit", "F").upper()
    if temp is None:
        raise RuntimeError("Temperature missing from forecast period")

    temp_f = float(temp)
    if unit == "C":
        temp_f = _c_to_f(temp_f)
    return int(round(temp_f))


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


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def temperature_tint(temp_f: int) -> Tuple[int, int, int]:
    """Map the Fahrenheit reading to a full-intensity red or blue tint."""
    if temp_f <= 32:
        intensity = clamp((32 - temp_f) / 32.0, 0.0, 1.0)
        fade = int(255 * (1.0 - intensity))
        return (fade, fade, 255)
    else:
        intensity = clamp((temp_f - 32) / (100 - 32), 0.0, 1.0)
        fade = int(255 * (1.0 - intensity))
        return (255, fade, fade)


def render_temperature(temp_f: int) -> List[Tuple[int, int, int]]:
    """
    Render the temperature onto a 10×5 canvas.
    Returns a list of 50 RGB tuples in panel order.
    """
    tint_color = temperature_tint(temp_f)

    canvas = [[(0, 0, 0) for _ in range(PANEL_WIDTH)] for _ in range(PANEL_HEIGHT)]

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
                        canvas[y][px] = tint_color
        x += width + spacing

    pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
    for y in range(PANEL_HEIGHT):
        for x in range(PANEL_WIDTH):
            idx = serpentine_index(x, y)
            pixels[idx] = canvas[y][x]
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
    data_id = 0

    header = bytes([
        flags_version,
        sequence & 0xFF,
        data_type,
        (offset >> 8) & 0xFF,
        offset & 0xFF,
        (data_len >> 8) & 0xFF,
        data_len & 0xFF,
        (data_id >> 8) & 0xFF,
        data_id & 0xFF,
        0x00,  # timecode (unused)
    ])
    return header + payload


def pixels_to_bytes(pixels: List[Tuple[int, int, int]]) -> bytes:
    buf = bytearray()
    for r, g, b in pixels:
        buf.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(buf)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence = 0
    last_fetch = 0.0
    current_temp = None
    render_pixels = None
    error_state = False

    try:
        lat, lon = geocode_location(LOCATION_QUERY)
        print(f"Geocoded '{LOCATION_QUERY}' -> lat={lat:.4f}, lon={lon:.4f}")
    except Exception as exc:
        raise SystemExit(f"Failed to geocode '{LOCATION_QUERY}': {exc}")

    try:
        while True:
            now = time.time()
            should_fetch = current_temp is None or (now - last_fetch) >= FETCH_INTERVAL_SEC
            if should_fetch:
                try:
                    current_temp = fetch_noaa_temperature(lat, lon)
                    last_fetch = now
                    print(f"Fetched NOAA temperature: {current_temp}°F")
                    render_pixels = render_temperature(current_temp)
                    error_state = False
                except Exception as exc:
                    print(f"NOAA fetch failed: {exc}")
                    last_fetch = now - (FETCH_INTERVAL_SEC - RETRY_INTERVAL_SEC)
                    error_state = True
                    if render_pixels is None and current_temp is not None:
                        render_pixels = render_temperature(current_temp)

            frame = (
                render_pixels[:]
                if render_pixels is not None
                else [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
            )
            if error_state:
                idx = serpentine_index(0, 0)
                frame[idx] = (255, 0, 0)
            payload = pixels_to_bytes(frame)

            packet = build_ddp_packet(sequence, payload)
            sock.sendto(packet, (CONTROLLER_IP, CONTROLLER_PORT))
            print(f"Sent payload seq={sequence}")
            sequence = (sequence + 1) % (DDP_SEQUENCE_MAX + 1)
            sleep_duration = RETRY_INTERVAL_SEC if error_state else FETCH_INTERVAL_SEC
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        print("Stopping temperature demo.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
