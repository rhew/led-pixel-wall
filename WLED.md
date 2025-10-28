# WLED

No WLED version supports the TinyS3 as of Oct 27, 2025.

  - OPI variant's don't work
  - QSPI for 4M doesn't work
  - Moonmodules variants don't work

## Install `esptool`

    python3 -mvenv venv
    source venv/bin/activate
    pip install esptool

## Install WLED

1. Get S3 8MB qspi bin file. If 8MB doesn't exist, choose 4MB e.g. `WLED_0.15.1_ESP32-S3_4M_qspi.bin` from https://github.com/wled/WLED/releases
2. Flash:
    source venv/bin/activate
    esptool --chip esp32s3 --port /dev/ttyACM0 erase_flash
    esptool --chip esp32s3 --port /dev/ttyACM0 write_flash -z 0x0 WLED_0.15.1_ESP32-S3_4M_qspi.bin
3. Reset () and join WLED-AP, http://4.3.2.1 to configure
