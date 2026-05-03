#!/usr/bin/env python3
"""LED wall effects demo for the 10×5 matrix."""

import argparse
import math
import random
import time
from typing import List, Optional, Tuple

from wallclient import DdpClient, PANEL_HEIGHT, PANEL_WIDTH, PanelConfig
from wallclient import serpentine_index

DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
LEFT_RIGHT_TURNS = {
    (1, 0): [(0, -1), (0, 1)],
    (-1, 0): [(0, 1), (0, -1)],
    (0, 1): [(1, 0), (-1, 0)],
    (0, -1): [(1, 0), (-1, 0)],
}
RANDOM_TURN_CHANCE = 0.06
WALL_SLIDE_TURN_CHANCE = 0.35
HIT_TURN_CHANCE = 0.75
TAIL_FADE_RATE = 9.5
TAIL_MIN_STRENGTH = 0.02
TAIL_LENGTH_LIMIT = 10
class HeatWaveEffect:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    def frame(self, dt: float, elapsed: float) -> List[Tuple[int, int, int]]:
        pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
        for y in range(PANEL_HEIGHT):
            for x in range(PANEL_WIDTH):
                rising = math.sin((y / 1.5) + elapsed)
                horizontal = math.sin((x / 2.2) - elapsed * 0.4)
                value = max(0.0, min(1.0, (rising + horizontal) * 0.5))

                intensity = value ** 1.2
                r = int(160 + 40 * intensity)
                g = int(15 + 100 * (intensity ** 1.8))
                b = int(2 + 20 * (intensity ** 0.8))

                idx = serpentine_index(x, y)
                pixels[idx] = (r, g, b)
        return pixels


class RadarTarget:
    def __init__(self, panel_width: int, panel_height: int) -> None:
        self.panel_width = panel_width
        self.panel_height = panel_height
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.strength = 0.0
        self.highlighted = False
        self.cooldown = 0.0
        self.last_ping = None
        self.is_red = False
        self.reset()

    def reset(self) -> None:
        spawn_edge = random.choice(["top", "left", "right", "bottom"])
        speed = random.uniform(0.12, 0.25)
        if spawn_edge == "top":
            self.x = random.uniform(-1.0, self.panel_width + 1.0)
            self.y = -random.uniform(1.0, 2.5)
            angle = random.uniform(math.pi * 0.3, math.pi * 0.7)
        elif spawn_edge == "bottom":
            self.x = random.uniform(-1.0, self.panel_width + 1.0)
            self.y = self.panel_height + random.uniform(1.0, 2.5)
            angle = random.uniform(-math.pi * 0.7, -math.pi * 0.3)
        elif spawn_edge == "left":
            self.x = -random.uniform(1.0, 2.5)
            self.y = random.uniform(-1.0, self.panel_height + 1.0)
            angle = random.uniform(-math.pi * 0.1, math.pi * 0.1)
        else:  # right
            self.x = self.panel_width + random.uniform(1.0, 2.5)
            self.y = random.uniform(-1.0, self.panel_height + 1.0)
            angle = math.pi - random.uniform(-math.pi * 0.1, math.pi * 0.1)
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)
        self.strength = 0.0
        self.highlighted = False
        self.cooldown = 0.0
        self.last_ping = None
        self.is_red = random.random() < 0.2

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.highlighted:
            fade_rate = 0.18  # ~5 s to fade so blips linger until the next sweep
            self.strength = max(0.0, self.strength - dt * fade_rate)
            if self.strength <= 0.02:
                self.highlighted = False
                self.last_ping = None
        if self.y < -3.0 or self.x < -3.0 or self.x > self.panel_width + 3.0:
            self.reset()


class RadarEffect:
    def __init__(self) -> None:
        self.center_x = PANEL_WIDTH / 2.0 - 0.5
        self.center_y = PANEL_HEIGHT + 2.5
        self.sweep_angle = 0.0
        self.sweep_speed = math.radians(70.0)
        self.targets = [RadarTarget(PANEL_WIDTH, PANEL_HEIGHT) for _ in range(4)]
        self.max_radius = max(
            math.hypot((x + 0.5) - self.center_x, self.center_y - (y + 0.5))
            for y in range(PANEL_HEIGHT)
            for x in range(PANEL_WIDTH)
        )

    def _angle(self, dx: float, dy: float) -> float:
        angle = math.atan2(dy, dx)
        if angle < 0.0:
            angle += 2.0 * math.pi
        return angle

    def frame(self, dt: float, elapsed: float) -> List[Tuple[int, int, int]]:
        self.sweep_angle = (self.sweep_angle + self.sweep_speed * dt) % (2.0 * math.pi)
        beam_width = math.radians(8.0)
        trail_factor = 4.0
        base_pixels = [[0, 0, 0] for _ in range(PANEL_WIDTH * PANEL_HEIGHT)]

        for y in range(PANEL_HEIGHT):
            for x in range(PANEL_WIDTH):
                cx = (x + 0.5) - self.center_x
                cy = self.center_y - (y + 0.5)
                radius = math.hypot(cx, cy)
                if radius == 0:
                    continue

                pixel_angle = self._angle(cx, cy)
                diff = ((pixel_angle - self.sweep_angle + math.pi) % (2 * math.pi)) - math.pi
                beam = math.exp(-((diff / beam_width) ** 2) * trail_factor)
                falloff = max(0.0, 1.0 - radius / (self.max_radius + 1.0))
                intensity = (beam * falloff) ** 1.5
                if intensity > 0.01:
                    idx = serpentine_index(x, y)
                    base_pixels[idx][1] = min(255, base_pixels[idx][1] + int(200 * intensity))
                    base_pixels[idx][2] = min(255, base_pixels[idx][2] + int(60 * intensity))

        trigger_width = math.radians(6.0)
        for target in self.targets:
            target.update(dt)
            dx = target.x - self.center_x
            dy = self.center_y - target.y
            target_angle = self._angle(dx, dy)
            diff = ((target_angle - self.sweep_angle + math.pi) % (2 * math.pi)) - math.pi
            if abs(diff) < trigger_width:
                target.strength = 1.0
                target.highlighted = True
                target.last_ping = (target.x, target.y)

            if target.last_ping:
                tx = int(target.last_ping[0])
                ty = int(target.last_ping[1])
                if 0 <= tx < PANEL_WIDTH and 0 <= ty < PANEL_HEIGHT:
                    idx = serpentine_index(tx, ty)
                    strength = min(1.0, target.strength)
                    if target.is_red:
                        base_pixels[idx][0] = min(255, base_pixels[idx][0] + int(230 * strength))
                        base_pixels[idx][1] = min(255, base_pixels[idx][1] + int(30 * strength))
                        base_pixels[idx][2] = min(255, base_pixels[idx][2] + int(25 * strength))
                    else:
                        base_pixels[idx][0] = min(255, base_pixels[idx][0] + int(40 * strength))
                        base_pixels[idx][1] = min(255, base_pixels[idx][1] + int(210 * strength))
                        base_pixels[idx][2] = min(255, base_pixels[idx][2] + int(60 * strength))

        return [tuple(pixel) for pixel in base_pixels]


class Mouse:
    def __init__(self) -> None:
        self.direction = random.choice(DIRECTIONS)
        self.x = random.randint(0, PANEL_WIDTH - 1)
        self.y = random.randint(0, PANEL_HEIGHT - 1)
        self.respawn_timer = 0.0
        self.visible = True
        self.color = (255, 210, 150)
        self.tail: List[Tuple[int, int, float]] = []

    def update(self, dt: float) -> None:
        self._fade_tail(dt)
        if self.respawn_timer > 0.0:
            self.respawn_timer = max(0.0, self.respawn_timer - dt)
            if self.respawn_timer == 0.0:
                self.spawn_from_edge()
            return

        dx, dy = self.direction
        next_x = self.x + dx
        next_y = self.y + dy
        turned = False

        if not self._in_bounds(next_x, next_y):
            turned = self._turn_at_wall()
            if not turned:
                self._add_tail_segment(self.x, self.y)
                self.x = next_x
                self.y = next_y
                self.respawn_timer = random.uniform(0.4, 1.0)
                self.visible = False
                return
            dx, dy = self.direction
            next_x = self.x + dx
            next_y = self.y + dy

        if not turned:
            self._turn_while_sliding()
            self._random_turn()

        prev_x, prev_y = self.x, self.y
        dx, dy = self.direction
        self.x += dx
        self.y += dy
        self._remove_tail_at(self.x, self.y)
        self._add_tail_segment(prev_x, prev_y)

    def _turn_at_wall(self) -> bool:
        if random.random() >= HIT_TURN_CHANCE:
            return False
        candidates = [
            d for d in LEFT_RIGHT_TURNS[self.direction]
            if self._in_bounds(self.x + d[0], self.y + d[1])
        ]
        if not candidates:
            return False
        self.direction = random.choice(candidates)
        return True

    def _turn_while_sliding(self) -> None:
        dx, dy = self.direction
        if dx == 0:
            if self.x == 0:
                away = (1, 0)
            elif self.x == PANEL_WIDTH - 1:
                away = (-1, 0)
            else:
                return
        else:
            if self.y == 0:
                away = (0, 1)
            elif self.y == PANEL_HEIGHT - 1:
                away = (0, -1)
            else:
                return
        if (
            random.random() < WALL_SLIDE_TURN_CHANCE
            and self._in_bounds(self.x + away[0], self.y + away[1])
        ):
            self.direction = away

    def _random_turn(self) -> None:
        if random.random() >= RANDOM_TURN_CHANCE:
            return
        reverse = (-self.direction[0], -self.direction[1])
        options = [
            d for d in DIRECTIONS
            if d != self.direction
            and d != reverse
            and self._in_bounds(self.x + d[0], self.y + d[1])
        ]
        if options:
            self.direction = random.choice(options)

    @staticmethod
    def _in_bounds(x: int, y: int) -> bool:
        return 0 <= x < PANEL_WIDTH and 0 <= y < PANEL_HEIGHT

    def _fade_tail(self, dt: float) -> None:
        if not self.tail:
            return
        decay = math.exp(-TAIL_FADE_RATE * dt)
        self.tail = [
            (tx, ty, strength * decay)
            for tx, ty, strength in self.tail
            if strength * decay > TAIL_MIN_STRENGTH
        ]

    def _add_tail_segment(self, x: int, y: int) -> None:
        if not self._in_bounds(x, y):
            return
        self._remove_tail_at(x, y)
        self.tail.append((x, y, 1.0))
        if len(self.tail) > TAIL_LENGTH_LIMIT:
            self.tail.pop(0)

    def _remove_tail_at(self, x: int, y: int) -> None:
        if not self.tail:
            return
        self.tail = [seg for seg in self.tail if not (seg[0] == x and seg[1] == y)]

    def spawn_from_edge(self) -> None:
        edge = random.choice(["left", "right", "top", "bottom"])
        if edge == "left":
            self.x = -1
            self.y = random.randint(0, PANEL_HEIGHT - 1)
            self.direction = (1, 0)
        elif edge == "right":
            self.x = PANEL_WIDTH
            self.y = random.randint(0, PANEL_HEIGHT - 1)
            self.direction = (-1, 0)
        elif edge == "top":
            self.x = random.randint(0, PANEL_WIDTH - 1)
            self.y = -1
            self.direction = (0, 1)
        else:
            self.x = random.randint(0, PANEL_WIDTH - 1)
            self.y = PANEL_HEIGHT
            self.direction = (0, -1)
        self.visible = True


class MouseChaseEffect:
    def __init__(self) -> None:
        self.mice = [Mouse()]

    def frame(self, dt: float, elapsed: float) -> List[Tuple[int, int, int]]:
        pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)

        for mouse in self.mice:
            mouse.update(dt)

            for tx, ty, strength in mouse.tail:
                if 0 <= tx < PANEL_WIDTH and 0 <= ty < PANEL_HEIGHT:
                    idx = serpentine_index(tx, ty)
                    scale = strength ** 2
                    tail_color = (
                        min(255, int(mouse.color[0] * scale)),
                        min(255, int(mouse.color[1] * scale)),
                        min(255, int(mouse.color[2] * scale)),
                    )
                    pixels[idx] = tail_color

            if not mouse.visible:
                continue
            ix = int(mouse.x)
            iy = int(mouse.y)
            if 0 <= ix < PANEL_WIDTH and 0 <= iy < PANEL_HEIGHT:
                idx = serpentine_index(ix, iy)
                pixels[idx] = mouse.color

        return pixels


class PDP11Effect:
    def __init__(self) -> None:
        self.speed = 4.51
        self.color = (255, 4, 0)
        self.dim_color = (6, 0, 0)
        self.fade_rate = 11
        self.row_pixels = [
            [(0.0, 0.0, 0.0) for _ in range(PANEL_WIDTH)]
            for _ in range(PANEL_HEIGHT)
        ]
        self.row_states = [self._spawn_row(y, randomize_phase=True) for y in range(PANEL_HEIGHT)]

    def _band_direction(self, y: int) -> int:
        if PANEL_HEIGHT <= 2:
            return -1

        top_rows = max(1, round(PANEL_HEIGHT * 0.4))
        bottom_rows = max(1, round(PANEL_HEIGHT * 0.2))
        if top_rows + bottom_rows >= PANEL_HEIGHT:
            top_rows = 1
            bottom_rows = 1

        middle_start = top_rows
        middle_end = PANEL_HEIGHT - bottom_rows

        if y < middle_start:
            return -1
        if y < middle_end:
            return 1
        return -1

    def _spawn_row(self, y: int, randomize_phase: bool = False) -> dict:
        direction = self._band_direction(y)
        count = random.randint(2, 3)
        spacing = PANEL_WIDTH / count
        particles = []
        speed_scale = random.uniform(0.82, 1.18)

        for i in range(count):
            base = i * spacing
            offset = random.uniform(0.0, max(0.2, spacing - 0.15)) if randomize_phase else 0.0
            position = base + offset
            if direction < 0:
                position = (PANEL_WIDTH - 1) - position
            particles.append(position)

        return {
            "direction": direction,
            "particles": particles,
            "speed_scale": speed_scale,
        }

    def frame(self, dt: float, elapsed: float) -> List[Tuple[int, int, int]]:
        decay = math.exp(-self.fade_rate * dt)

        for y in range(PANEL_HEIGHT):
            state = self.row_states[y]
            direction = state["direction"]
            speed = self.speed * state["speed_scale"]
            updated_particles = []
            faded_row = []

            for r, g, b in self.row_pixels[y]:
                faded_row.append((r * decay, g * decay, b * decay))
            self.row_pixels[y] = faded_row

            for position in state["particles"]:
                position += direction * speed * dt
                if direction < 0 and position < 0.0:
                    position += PANEL_WIDTH
                elif direction > 0 and position >= PANEL_WIDTH:
                    position -= PANEL_WIDTH
                updated_particles.append(position)

                x = int(round(position)) % PANEL_WIDTH
                distance = abs(x - position)
                wrap_distance = PANEL_WIDTH - distance
                distance = min(distance, wrap_distance)
                bulb = max(0.0, 1.0 - (distance / 0.75))
                intensity = bulb * bulb * (3.0 - 2.0 * bulb)
                current = self.row_pixels[y][x]
                self.row_pixels[y][x] = (
                    min(255.0, current[0] + (self.dim_color[0] + (self.color[0] - self.dim_color[0]) * intensity)),
                    min(255.0, current[1] + (self.dim_color[1] + (self.color[1] - self.dim_color[1]) * intensity)),
                    min(255.0, current[2] + (self.dim_color[2] + (self.color[2] - self.dim_color[2]) * intensity)),
                )

            state["particles"] = updated_particles

        pixels = [(0, 0, 0)] * (PANEL_WIDTH * PANEL_HEIGHT)
        for y in range(PANEL_HEIGHT):
            for x in range(PANEL_WIDTH):
                idx = serpentine_index(x, y)
                r, g, b = self.row_pixels[y][x]
                pixels[idx] = (int(r), int(g), int(b))

        return pixels


EFFECTS = {
    "radar": (RadarEffect, 0.03),
    "heatwave": (HeatWaveEffect, 0.04),
    "mouse": (MouseChaseEffect, 0.05),
    "pdp-11": (PDP11Effect, 0.05),
}
DEMO_DURATION_SECONDS = 30.0


def run_effect(effect, frame_interval: float, duration: Optional[float] = None) -> None:
    client = DdpClient(PanelConfig(frame_interval=frame_interval))
    effect_start = time.perf_counter()
    last = effect_start
    try:
        while True:
            now = time.perf_counter()
            dt = now - last
            elapsed = now - effect_start
            last = now
            frame = effect.frame(dt, elapsed)
            client.send(frame)
            elapsed_after_send = time.perf_counter() - effect_start
            if duration is not None and elapsed_after_send >= duration:
                break
            spent = time.perf_counter() - now
            sleep_time = max(0.0, frame_interval - spent)
            time.sleep(sleep_time)
    finally:
        client.close()


def run_demo() -> None:
    effect_keys = list(EFFECTS.keys())
    if not effect_keys:
        return
    current = random.choice(effect_keys)
    while True:
        factory, interval = EFFECTS[current]
        run_effect(factory(), interval, duration=DEMO_DURATION_SECONDS)
        next_choices = [key for key in effect_keys if key != current]
        current = random.choice(next_choices) if next_choices else current


def main() -> None:
    parser = argparse.ArgumentParser(description="LED wall effects.")
    parser.add_argument(
        "--effect",
        choices=list(EFFECTS.keys()),
        default="pdp-11",
        help="Which animation to play (default: pdp-11).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=f"Cycle through all effects, switching every {DEMO_DURATION_SECONDS} seconds.",
    )
    args = parser.parse_args()

    try:
        if args.demo:
            run_demo()
        else:
            factory, frame_interval = EFFECTS[args.effect]
            run_effect(factory(), frame_interval)
    except KeyboardInterrupt:
        print("Stopping effects demo.")


if __name__ == "__main__":
    main()
