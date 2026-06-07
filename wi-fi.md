# Wi-Fi Provisioning (Getting Started)

## Initial Setup

1. **Join the setup network**
   - The first LED breathes blue on first boot or after clearing credentials.
   - Connect to the `LED-Wall-Setup` network and browse to `http://192.168.4.1/`.

2. **Enter network details**  
   - Provide your SSID and password for your Wi-Fi network.
   - Submitted credentials are tested first and saved only after the controller gets an IP address.
   - Some dual-band routers, like Google Wi-Fi, do not expose a stable 2.4 GHz join path. Select `Force 2.4 GHz` to lock onto the 2.4 GHz BSSID, then watch the LED status list below. If the LED reports a failure, re-open `http://192.168.4.1/` and retry with another band or router.

**Status LED (LED 0)**

   - **Blue blink**: credential portal open.
   - **Fast blue blink**: device is attempting to connect.
   - **Triple green flash**: credentials accepted; DDP streaming will begin shortly.
   - **Double red blink**: connection failed; the portal stays open so you can retry.

## Normal operation

   - The controller reconnects on future boots using the saved credentials. Connection failures keep those credentials so the controller can retry on the next boot.
   - If newly submitted credentials fail, they are discarded instead of replacing the saved credentials.
   - To clear saved Wi-Fi, connect over USB and erase the `nvs` partition:

     ```
     python3 $IDF_PATH/components/partition_table/parttool.py --port /dev/ttyACM0 --partition-table-file build/partition_table/partition-table.bin erase_partition --partition-name nvs
     ```

     Reboot afterward; the slow blue breathing LED returns to show AP mode is active.
