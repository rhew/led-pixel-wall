#!/usr/bin/env python3
"""
NOAA temperature demo for the LED Pixel Wall.

Fetches the latest observation temperature for the configured location and
renders it to the panel. Sunrise/sunset comes from sunrise-sunset.org, so the
background (and digit color) depend purely on the sun cycle rather than the
forecast API. A --test-backgrounds mode cycles through every animation.
"""

import argparse
import time
from datetime import datetime
from typing import Optional

from wallclient import DdpClient, PanelConfig
from wallclient.config import env_str
from weatherlib import backgrounds, noaa, sun

RETRY_INTERVAL_SEC = 60.0
FETCH_INTERVAL_SEC = 300.0
TEST_MODE_TEMPERATURE = 72


def parse_args() -> argparse.Namespace:
    defaults = PanelConfig()
    parser = argparse.ArgumentParser(description="LED wall weather display")
    parser.add_argument(
        "--controller-ip",
        default=defaults.controller_ip,
        help="Controller IP address (default: LED_WALL_CONTROLLER_IP).",
    )
    parser.add_argument(
        "--controller-port",
        type=int,
        default=defaults.controller_port,
        help=f"Controller UDP port (default: {defaults.controller_port}).",
    )
    parser.add_argument(
        "--location",
        default=env_str("LED_WALL_WEATHER_LOCATION"),
        help="Weather location query (default: LED_WALL_WEATHER_LOCATION).",
    )
    parser.add_argument(
        "--test-backgrounds",
        action="store_true",
        help="Cycle through every background animation instead of fetching NOAA data.",
    )
    return parser.parse_args()


def run_background_test(args: argparse.Namespace) -> None:
    backgrounds_to_show = backgrounds.iter_background_states_for_test()

    client = DdpClient(PanelConfig(controller_ip=args.controller_ip, controller_port=args.controller_port))
    print("Entering background test mode. Press Ctrl-C to stop.")
    try:
        while True:
            for label, state in backgrounds_to_show:
                print(f"Displaying '{label}' with digit color {state.digit_color}")
                cycle_duration = sum(state.durations) if state.durations else backgrounds.FRAME_INTERVAL_SEC * len(state.frames)
                min_duration = max(3.0, 2.0 * cycle_duration)
                start_time = time.time()
                state.frame_index = 0
                while True:
                    frame = backgrounds.build_frame_pixels(state, TEST_MODE_TEMPERATURE, None)
                    client.send(frame)
                    duration = state.next_duration()
                    state.advance_frame()
                    time.sleep(max(duration, 0.01))
                    if state.frame_index == 0 and (time.time() - start_time) >= min_duration:
                        break
    except KeyboardInterrupt:
        print("Background test stopped.")
    finally:
        client.close()


def run_weather_display(args: argparse.Namespace) -> None:
    if not args.location:
        raise SystemExit("Set LED_WALL_WEATHER_LOCATION or pass --location.")

    controller_ip = args.controller_ip
    controller_port = args.controller_port
    client = DdpClient(PanelConfig(controller_ip=controller_ip, controller_port=controller_port))
    last_fetch = 0.0
    current_temp: Optional[int] = None
    icon_key = backgrounds.DEFAULT_ANIMATION_KEY
    indicator_level: Optional[str] = None
    overlay_text: Optional[str] = None
    fetch_failed = False

    try:
        lat, lon = noaa.geocode_location(args.location)
        print(f"Geocoded '{args.location}' -> lat={lat:.4f}, lon={lon:.4f}")
    except Exception as exc:
        raise SystemExit(f"Failed to geocode '{args.location}': {exc}")

    properties = noaa.fetch_point_properties(lat, lon)
    stations_url = properties.get("observationStations")
    if not stations_url:
        raise SystemExit("Point metadata missing observation stations URL")

    sun_tracker = sun.SunTracker(lat, lon, datetime.now().astimezone().tzinfo)
    state = backgrounds.build_display_state(icon_key, sun_tracker.is_day())

    try:
        while True:
            sun_tracker.update_if_needed()
            is_daytime = sun_tracker.is_day()
            backgrounds.update_display_state(state, state.background_key, is_daytime)

            now = time.time()
            if (current_temp is None and overlay_text is None) or (now - last_fetch) >= FETCH_INTERVAL_SEC:
                try:
                    current_temp, icon_code, indicator_level = noaa.fetch_observation_temp_and_icon(stations_url)
                    last_fetch = now
                    overlay_text = None
                    if indicator_level == "red":
                        current_temp = None
                        indicator_level = None
                        overlay_text = "??"
                        icon_key = "fog"
                        fetch_failed = True
                        backgrounds.update_display_state(state, icon_key, is_daytime)
                        print(
                            "Using no-data display for stale observation: "
                            f"icon='{icon_code}', age>=2h, animation='{state.background_source}'"
                        )
                    else:
                        icon_key = backgrounds.animation_key_for_icon(icon_code)
                        backgrounds.update_display_state(state, icon_key, is_daytime)
                        print(
                            "Fetched NOAA temperature: "
                            f"{current_temp}°F ({'day' if is_daytime else 'night'}) "
                            f"icon='{icon_code}', animation='{state.background_source}', "
                            f"indicator='{indicator_level or 'none'}'"
                        )
                        fetch_failed = False
                except Exception as exc:
                    print(f"NOAA fetch failed: {exc}")
                    last_fetch = now - (FETCH_INTERVAL_SEC - RETRY_INTERVAL_SEC)
                    current_temp = None
                    overlay_text = "??"
                    icon_key = "fog"
                    indicator_level = None
                    fetch_failed = True
                    backgrounds.update_display_state(state, icon_key, is_daytime)

            frame = backgrounds.build_frame_pixels(state, current_temp, indicator_level, overlay_text)
            client.send(frame)
            duration = state.next_duration()
            state.advance_frame()
            sleep_duration = min(RETRY_INTERVAL_SEC, duration) if fetch_failed else duration
            time.sleep(max(sleep_duration, 0.01))
    except KeyboardInterrupt:
        print("Stopping weather display.")
    finally:
        client.close()


def main() -> None:
    args = parse_args()
    if args.test_backgrounds:
        run_background_test(args)
    else:
        run_weather_display(args)


if __name__ == "__main__":
    main()
