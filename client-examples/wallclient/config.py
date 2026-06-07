import os
from dataclasses import dataclass, field
from pathlib import Path


CLIENT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(CLIENT_ENV_PATH)


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class PanelConfig:
    width: int = field(default_factory=lambda: env_int("LED_WALL_PANEL_WIDTH", 10))
    height: int = field(default_factory=lambda: env_int("LED_WALL_PANEL_HEIGHT", 10))
    controller_ip: str = field(default_factory=lambda: env_str("LED_WALL_CONTROLLER_IP"))
    controller_port: int = field(default_factory=lambda: env_int("LED_WALL_CONTROLLER_PORT", 4048))
    frame_interval: float = field(default_factory=lambda: env_float("LED_WALL_FRAME_INTERVAL", 0.1))
