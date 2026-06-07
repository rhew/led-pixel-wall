#!/usr/bin/env python3
"""Minimal DDP client that paints the LED Pixel Wall solid red."""

from wallclient import DdpClient, PanelConfig

LED_COUNT = 100


def main() -> None:
    solid_blue = [(0xFF, 0x00, 0x00)] * LED_COUNT
    config = PanelConfig()
    client = DdpClient(config)
    try:
        client.sequence = 2
        client.send(solid_blue)
    finally:
        client.close()
    print(f"Sent {LED_COUNT * 3 + 10} bytes to {config.controller_ip}:{config.controller_port}")


if __name__ == "__main__":
    main()
