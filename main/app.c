#include "controller_config.h"
#include "ddp_server.h"
#include "led_driver.h"
#include "wifi_provisioning.h"

#include "esp_err.h"
#include "esp_log.h"

#define APP_LED_GPIO 3

static const char *TAG = "app";

static controller_config_t s_config;

static void stop_ddp_if_running(void) {
    if (ddp_server_is_running()) {
        ESP_LOGI(TAG, "Stopping DDP server");
        ddp_server_stop();
    }
}

static void start_ddp_with_current_config(void) {
    controller_config_t latest;
    controller_config_get_defaults(&latest);
    esp_err_t cfg_err = controller_config_load(&latest);
    if (cfg_err != ESP_OK) {
        ESP_LOGW(TAG, "Using defaults; failed to reload controller config: %s",
                 esp_err_to_name(cfg_err));
    }

    if (latest.led_count == 0) {
        latest.led_count = s_config.led_count ? s_config.led_count : 50;
    }

    bool led_count_changed = (latest.led_count != s_config.led_count);
    bool port_changed = (latest.ddp_port != s_config.ddp_port);

    if (ddp_server_is_running() && (led_count_changed || port_changed)) {
        stop_ddp_if_running();
    }

    if (led_count_changed) {
        ESP_LOGI(TAG, "Reconfiguring LED driver for %u LEDs",
                 (unsigned int)latest.led_count);
        esp_err_t err = led_driver_set_pixel_count(latest.led_count);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to reconfigure LED driver: %s", esp_err_to_name(err));
            return;
        }
    }

    s_config = latest;

    if (!ddp_server_is_running()) {
        ddp_server_config_t ddp_cfg = {
            .port = s_config.ddp_port,
            .led_count = s_config.led_count,
        };
        esp_err_t err = ddp_server_start(&ddp_cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to start DDP server: %s", esp_err_to_name(err));
        } else {
            ESP_LOGI(TAG, "DDP server listening on port %u for %u LEDs",
                     (unsigned int)s_config.ddp_port,
                     (unsigned int)s_config.led_count);
        }
    }
}

static void provisioning_status_cb(wifi_provisioning_status_t status,
                                   const char *message,
                                   void *user_ctx) {
    (void)message;
    (void)user_ctx;
    switch (status) {
    case WIFI_PROVISIONING_STATUS_CONNECTED:
        ESP_LOGI(TAG, "Wi-Fi connected; enabling DDP");
        start_ddp_with_current_config();
        break;
    case WIFI_PROVISIONING_STATUS_PORTAL:
        ESP_LOGI(TAG, "Provisioning portal active");
        stop_ddp_if_running();
        break;
    case WIFI_PROVISIONING_STATUS_CONNECTING:
        ESP_LOGI(TAG, "Wi-Fi connecting");
        stop_ddp_if_running();
        break;
    case WIFI_PROVISIONING_STATUS_ERROR:
        ESP_LOGW(TAG, "Provisioning error; DDP paused");
        stop_ddp_if_running();
        break;
    default:
        break;
    }
}

void app_main(void) {
    controller_config_get_defaults(&s_config);
    esp_err_t cfg_err = controller_config_load(&s_config);
    if (cfg_err != ESP_OK) {
        ESP_LOGW(TAG, "Using default controller config: %s", esp_err_to_name(cfg_err));
    }
    if (s_config.led_count == 0) {
        s_config.led_count = 50;
    }
    if (s_config.ddp_port == 0) {
        s_config.ddp_port = 4048;
    }

    ESP_ERROR_CHECK(led_driver_init(APP_LED_GPIO, s_config.led_count));

    wifi_provisioning_config_t wifi_cfg = {
        .status_cb = provisioning_status_cb,
        .user_ctx = NULL,
    };
    ESP_ERROR_CHECK(wifi_provisioning_start(&wifi_cfg));
}
