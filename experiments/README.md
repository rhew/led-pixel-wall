# Experiments

Scratch prototypes that previously replaced or supplemented the main LED wall firmware. These files are not part of the default build; copy them into `main/` when you need to revive or iterate on the experiments.

## `wifi-test.c`
- SoftAP provisioning flow (`LedPixelWall-Setup`) with a captive portal at `http://192.168.4.1`.
- Captures SSID, password, and an optional “force 2.4 GHz” toggle, storing results in NVS (`wifi` namespace).
- Reconfigures the radio into STA mode and attempts to connect using the saved credentials.
- Dependencies: `esp_wifi`, `esp_event`, `esp_netif`, `nvs_flash`, `esp_http_server`.

## `bluetooth-test.c`
- Prototype for Bluetooth functionality (not integrated with the production firmware).
- Document behavior, dependencies, and outcomes here when expanding the experiment.
