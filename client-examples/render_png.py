#!/usr/bin/env python3
"""
Render one or more PNG images to the LED wall via DDP.

Usage examples:
    ./render_png.py clear-day.png
    ./render_png.py weather-backgrounds/
"""

import argparse
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from PIL import Image
from wallclient import DdpClient, PanelConfig, pixels_to_bytes, serpentine_index

DISPLAY_SECONDS = 5.0
IMAGE_MODE = "RGB"
MIN_FRAME_DURATION = 0.05  # seconds


def read_key(prompt: str) -> str:
    """Read a single key press, supporting arrow keys. Falls back to input."""
    if not sys.stdin.isatty():
        try:
            return input(prompt)
        except EOFError:
            return "q"

    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch1 = sys.stdin.read(1)
        if ch1 == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "C":
                    return "RIGHT"
                if ch3 == "D":
                    return "LEFT"
                if ch3 == "A":
                    return "UP"
                if ch3 == "B":
                    return "DOWN"
            return "ESC"
        if ch1 in ("\r", "\n"):
            return "ENTER"
        if ch1.lower() == "q":
            return "QUIT"
        if ch1.lower() == "n":
            return "NEXT"
        return ch1
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def load_frames(path: Path) -> List[Tuple[int, int, List[Tuple[int, int, int]], float]]:
    """Load a PNG/APNG and return a list of (width, height, pixels, duration_seconds)."""
    frames: List[Tuple[int, int, List[Tuple[int, int, int]], float]] = []
    with Image.open(path) as img:
        frame_count = getattr(img, "n_frames", 1)
        for frame_index in range(frame_count):
            img.seek(frame_index)
            frame = img.convert(IMAGE_MODE)
            width, height = frame.size
            pixels = list(frame.getdata())
            duration_ms = img.info.get("duration", 0)
            duration_sec = max(duration_ms / 1000.0, MIN_FRAME_DURATION) if frame_count > 1 else 0.0
            frames.append((width, height, pixels, duration_sec))
    return frames


def reorder_pixels(width: int, height: int, pixels: Sequence[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """Reorder image pixels into serpentine panel order."""
    if len(pixels) != width * height:
        raise ValueError("Pixel count does not match width * height")
    ordered = [(0, 0, 0)] * (width * height)
    for idx, (r, g, b) in enumerate(pixels):
        x = idx % width
        y = idx // width
        ordered_idx = serpentine_index(x, y, width, height)
        ordered[ordered_idx] = (r, g, b)
    return ordered


def iter_png_paths(target: Path) -> Iterable[Path]:
    if target.is_dir():
        for path in sorted(target.iterdir()):
            if path.suffix.lower() == ".png":
                yield path
    elif target.is_file():
        yield target
    else:
        raise SystemExit(f"No such file or directory: {target}")


def parse_args() -> argparse.Namespace:
    defaults = PanelConfig()
    parser = argparse.ArgumentParser(description="Render PNGs to the LED panel via DDP.")
    parser.add_argument("path", help="PNG file or directory of PNG files.")
    parser.add_argument("--width", type=int, default=defaults.width, help=f"Panel width in pixels (default: {defaults.width}).")
    parser.add_argument("--height", type=int, default=defaults.height, help=f"Panel height in pixels (default: {defaults.height}).")
    parser.add_argument("--ip", default=defaults.controller_ip, help="Controller IP address (default: LED_WALL_CONTROLLER_IP).")
    parser.add_argument("--port", type=int, default=defaults.controller_port, help=f"Controller DDP port (default: {defaults.controller_port}).")
    parser.add_argument("--seconds", type=float, default=DISPLAY_SECONDS, help="Display duration per image.")
    parser.add_argument(
        "--repeat",
        action="store_true",
        help="Loop through the provided images continuously.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="Advance one frame at a time; press Enter for next frame, 'q' to quit.",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="Display only the given frame number (1-based) for each animation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel_px = args.width * args.height * 3

    paths = list(iter_png_paths(Path(args.path)))
    if not paths:
        raise SystemExit("No PNG files found.")

    client = DdpClient(PanelConfig(
        width=args.width,
        height=args.height,
        controller_ip=args.ip,
        controller_port=args.port,
    ))
    quit_requested = False
    try:
        while True:
            for path in paths:
                frames = load_frames(path)
                if not frames:
                    continue

                width, height = frames[0][0], frames[0][1]
                if width != args.width or height != args.height:
                    raise SystemExit(f"{path} is {width}x{height}, expected {args.width}x{args.height}")

                prepared: List[Tuple[bytes, float]] = []
                for frame_width, frame_height, pixels, duration in frames:
                    if frame_width != width or frame_height != height:
                        raise SystemExit(f"{path} contains inconsistent frame sizes.")
                    ordered = reorder_pixels(width, height, pixels)
                    payload = pixels_to_bytes(ordered)
                    if len(payload) != panel_px:
                        raise SystemExit(f"{path} payload size mismatch.")
                    prepared.append((payload, duration))

                payloads = [payload for payload, _ in prepared]
                durations_raw = [duration for _, duration in prepared]

                if len(prepared) == 1:
                    print(f"{path} -> static {width}x{height}")
                    client.send_payload(payloads[0])
                    if args.step:
                        key = read_key("Press Enter/right for next, 'q' to quit: ")
                        if key in ("QUIT", "ESC", "q", "Q"):
                            quit_requested = True
                            break
                    else:
                        time.sleep(args.seconds)
                else:
                    avg_duration = sum(durations_raw) / len(durations_raw)
                    print(
                        f"{path} -> animation {width}x{height}, "
                        f"{len(prepared)} frames, "
                        f"frame duration {avg_duration:.3f}s avg"
                    )
                    if args.frame is not None:
                        idx = args.frame - 1
                        if idx < 0 or idx >= len(payloads):
                            raise SystemExit(
                                f"Frame {args.frame} out of range for {path} "
                                f"({len(payloads)} frames)"
                            )
                        print(f"Displaying frame {args.frame}/{len(payloads)}")
                        client.send_payload(payloads[idx])
                        print(
                            f"  frame {args.frame}/{len(payloads)} "
                            f"duration {durations_raw[idx]:.3f}s"
                        )
                        if args.step:
                            key = read_key("Press Enter/right for next image, 'q' to quit: ")
                            if key in ("QUIT", "ESC", "q", "Q"):
                                quit_requested = True
                        else:
                            time.sleep(args.seconds)
                        if quit_requested:
                            break
                        continue

                    if args.step:
                        frame_idx = 0
                        key_lower = ""
                        while not quit_requested:
                            payload = payloads[frame_idx]
                            client.send_payload(payload)
                            print(
                                f"  frame {frame_idx + 1}/{len(payloads)} "
                                f"duration {durations_raw[frame_idx]:.3f}s"
                            )
                            key_input = read_key(
                                "Right/Enter next, left previous, 'n' next image, 'q' to quit: "
                            )
                            key_lower = key_input.strip().lower()
                            if key_lower.startswith("q") or key_input in ("QUIT", "ESC"):
                                quit_requested = True
                                break
                            if key_lower.startswith("n"):
                                break
                            if key_input in ("LEFT", "DOWN"):
                                frame_idx = (frame_idx - 1) % len(payloads)
                            else:
                                frame_idx = (frame_idx + 1) % len(payloads)
                        if quit_requested:
                            break
                        if key_lower.startswith("n"):
                            continue
                        if not args.repeat:
                            break
                    else:
                        durations_clamped = [max(duration, MIN_FRAME_DURATION) for duration in durations_raw]
                        total_cycle = sum(durations_clamped)
                        target_duration = max(args.seconds, total_cycle)
                        start_time = time.monotonic()
                        elapsed = 0.0
                        print(f"Playing animation {path} for {target_duration:.2f}s")
                        while elapsed < target_duration:
                            for payload, duration in zip(payloads, durations_clamped):
                                client.send_payload(payload)
                                time.sleep(duration)
                                elapsed = time.monotonic() - start_time
                                if elapsed >= target_duration:
                                    break
                if quit_requested:
                    break
            if quit_requested or not args.repeat:
                break
    except KeyboardInterrupt:
        print("Stopping PNG renderer.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
