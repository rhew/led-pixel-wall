# LED Pixel Wall

Control a wall of pixels. Tested with:

  - TinyS3 ESP32-S3 microcontroller
  - WS2811 LEDs

---

## IDF code for "breathing" LEDs

### Configure

Use the following in `main/led-pixel-wall.c` to configure:

    #define LED_STRIP_GPIO      3       // GPIO for WS2811 data
    #define LED_COUNT           50      // Number of LEDs
    #define MAX_BRIGHTNESS     0.5
    #define MAX_FADING_LEDS     15
    #define DELAY_MS            50

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

---

## WLED

No WLED version supports the TinyS3 as of Oct 27, 2025. See WLED.md.
