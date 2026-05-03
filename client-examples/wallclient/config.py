from dataclasses import dataclass


@dataclass(frozen=True)
class PanelConfig:
    width: int = 10
    height: int = 10
    controller_ip: str = "192.168.86.28"
    controller_port: int = 4048
    frame_interval: float = 0.1
