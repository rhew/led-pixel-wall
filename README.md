# LED Pixel Wall

Control a wall of pixels. Tested with:

    - TinyS3 ESP32-S3 microcontroller
    - WS2811 LEDs
    - LED panel with a 10×10 serpentine layout starting at the bottom-left corner

Components:

    - `main/app.c`: ESP32-S3 firmware that listens for DDP frames and drives a WS2811 strip
    - `client-examples/render_png.py`: client for rendering PNG/APNG images to the DDP server
    - `client-examples/weather.py`: NOAA weather display client and Docker packaging
    - `client-examples/system_status.py`: local CPU and memory status client
    - `client-examples/trail_status.py`: TriangleMTB/Trailforks trail status client


Why not WLED?

No WLED version supports the TinyS3 as of Oct 27, 2025. See WLED.md.

---

## DDP server firmware for the LED wall

### Configure

Use the following in `main/app.c` to configure the GPIO pin for WS2811 data:

    #define APP_LED_GPIO 3

### Prepare

    idf_tools.py install-python-env
    source ~/.local/lib/esp/esp-idf/export.sh
    idf.py set-target esp32s3
    idf.py reconfigure

Once:

    idf.py add-dependency "espressif/led_strip"

### Build and run

    idf.py build
    idf.py -p /dev/ttyACM0 erase-flash
    idf.py -p /dev/ttyACM0 flash
    idf.py -p /dev/ttyACM0 monitor

    # or all together:
    idf.py -p /dev/ttyACM0 build flash monitor

### Reset saved Wi-Fi over USB

Connect the controller over USB and erase the `nvs` partition:

    python3 $IDF_PATH/components/partition_table/parttool.py --port /dev/ttyACM0 --partition-table-file build/partition_table/partition-table.bin erase_partition --partition-name nvs

This clears saved Wi-Fi credentials and controller config while leaving the firmware installed. Reboot the controller; it should start the `LED-Wall-Setup` provisioning network.

---

## Weather client (Docker)

The root `Dockerfile` packages the NOAA weather client in `client-examples/weather.py`.

1. Build the image from the repo root:
   ```
   docker build -t led-wall-weather .
   ```
2. Run it with access to your LAN (the container needs to send UDP packets to the DDP server). Replace the IP/port with your ESP-32 board values:
   ```
   docker run --rm --network host led-wall-weather --controller-ip 192.168.86.32 --controller-port 4048
   ```
3. Add `--test-backgrounds` to cycle every animation:
   ```
   docker run --rm --network host led-wall-weather --test-backgrounds
   ```

---

## Trail status client

`client-examples/trail_status.py` renders TriangleMTB trail status to the wall using the TriangleMTB page plus Trailforks status widgets/pages.

It requires `cloudscraper`. Run:

```
client-examples/venv/bin/python client-examples/trail_status.py
```

---

## System status client

`client-examples/system_status.py` renders local CPU usage and memory usage to the LED wall.

Run:

```
python3 client-examples/system_status.py
```
