#include <string.h>
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_log.h"

#define TAG "XBOX_BT"

static uint8_t iocap = ESP_BT_IO_CAP_IO;  // Set IO capability for secure pairing

static void bt_gap_callback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param) {
    switch (event) {
        case ESP_BT_GAP_DISC_RES_EVT: {  // Device found
            ESP_LOGI(TAG, "Device found: %d properties", param->disc_res.num_prop);

            esp_bd_addr_t device_mac;
            bool has_mac = false;

            for (int i = 0; i < param->disc_res.num_prop; i++) {
                if (param->disc_res.prop[i].type == ESP_BT_GAP_DEV_PROP_BDNAME) {
                    ESP_LOGI(TAG, "Device name: %.*s",
                             param->disc_res.prop[i].len,
                             (char *)param->disc_res.prop[i].val);
                }
            }

            // Copy MAC address from discovery result
            memcpy(device_mac, param->disc_res.bda, sizeof(esp_bd_addr_t));
            has_mac = true;

            ESP_LOGI(TAG, "MAC Address: %02X:%02X:%02X:%02X:%02X:%02X",
                     device_mac[0], device_mac[1], device_mac[2],
                     device_mac[3], device_mac[4], device_mac[5]);

            // Example check for a specific MAC prefix (adjust as needed)
            const uint8_t xbox_mac_prefix[3] = {0x00, 0x1F, 0xE3};  // Example Xbox prefix
            if (has_mac && memcmp(device_mac, xbox_mac_prefix, 3) == 0) {
                ESP_LOGI(TAG, "🎮 Xbox Controller Found! Attempting to set security params...");

                // Set security parameters before pairing
                esp_err_t err = esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(uint8_t));
                if (err == ESP_OK) {
                    ESP_LOGI(TAG, "🔒 Security parameters set, waiting for pairing request...");
                } else {
                    ESP_LOGE(TAG, "❌ Failed to set security parameters: %s", esp_err_to_name(err));
                }
            }
            break;
        }

        case ESP_BT_GAP_AUTH_CMPL_EVT: {  // Pairing result
            if (param->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS) {
                ESP_LOGI(TAG, "✅ Successfully paired with: %s", param->auth_cmpl.device_name);
            } else {
                ESP_LOGE(TAG, "❌ Pairing failed with error: %d", param->auth_cmpl.stat);
            }
            break;
        }

        case ESP_BT_GAP_PIN_REQ_EVT: {  // Handle PIN request
            uint8_t pin_code[] = {'1', '2', '3', '4'};  // Default 4-digit PIN
            ESP_LOGI(TAG, "🔑 PIN requested. Sending: %s", pin_code);
            esp_bt_gap_pin_reply(param->pin_req.bda, true, sizeof(pin_code), pin_code);

            break;
        }

        default:
            ESP_LOGI(TAG, "⚠️ Unhandled Bluetooth event: %d", event);
            break;
    }
}

// Initialize Bluetooth and start discovery
void app_main(void) {
    ESP_LOGI(TAG, "Initializing Bluetooth...");

    // Enable Bluetooth Classic mode
    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_BLE));
    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT));

    // Enable Bluetooth Host
    ESP_ERROR_CHECK(esp_bluedroid_init());
    ESP_ERROR_CHECK(esp_bluedroid_enable());

    // Register GAP callback for handling discovery & pairing
    ESP_ERROR_CHECK(esp_bt_gap_register_callback(bt_gap_callback));

    // Start scanning for devices
    ESP_ERROR_CHECK(esp_bt_gap_start_discovery(ESP_BT_INQ_MODE_GENERAL_INQUIRY, 10, 0));

    ESP_LOGI(TAG, "Scanning for Xbox controllers...");
}

