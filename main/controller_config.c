#include "controller_config.h"

#include "esp_log.h"
#include "nvs.h"

#define TAG "ctrl_cfg"

#define CONFIG_NAMESPACE "controller"
#define KEY_LED_COUNT "led_count"
#define KEY_DDP_PORT "ddp_port"

#define DEFAULT_LED_COUNT 50
#define DEFAULT_DDP_PORT 4048

void controller_config_get_defaults(controller_config_t *out) {
    if (!out) {
        return;
    }
    out->led_count = DEFAULT_LED_COUNT;
    out->ddp_port = DEFAULT_DDP_PORT;
    out->has_values = false;
}

esp_err_t controller_config_load(controller_config_t *out) {
    if (!out) {
        return ESP_ERR_INVALID_ARG;
    }
    controller_config_get_defaults(out);

    nvs_handle_t handle;
    esp_err_t err = nvs_open(CONFIG_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        if (err != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGW(TAG, "Failed to open config namespace: %s", esp_err_to_name(err));
            return err;
        }
        return ESP_OK;
    }

    uint16_t led_count = 0;
    uint16_t ddp_port = 0;
    bool have_led = false;
    bool have_port = false;

    err = nvs_get_u16(handle, KEY_LED_COUNT, &led_count);
    if (err == ESP_OK) {
        have_led = true;
    } else if (err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to read led_count: %s", esp_err_to_name(err));
    }

    err = nvs_get_u16(handle, KEY_DDP_PORT, &ddp_port);
    if (err == ESP_OK) {
        have_port = true;
    } else if (err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to read ddp_port: %s", esp_err_to_name(err));
    }

    nvs_close(handle);

    if (have_led) {
        out->led_count = led_count;
    }
    if (have_port) {
        out->ddp_port = ddp_port;
    }
    out->has_values = have_led && have_port;
    return ESP_OK;
}

esp_err_t controller_config_save(const controller_config_t *cfg) {
    if (!cfg) {
        return ESP_ERR_INVALID_ARG;
    }
    nvs_handle_t handle;
    esp_err_t err = nvs_open(CONFIG_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open config namespace for write: %s", esp_err_to_name(err));
        return err;
    }

    esp_err_t led_err = nvs_set_u16(handle, KEY_LED_COUNT, cfg->led_count);
    if (led_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to write led_count: %s", esp_err_to_name(led_err));
        nvs_close(handle);
        return led_err;
    }

    esp_err_t port_err = nvs_set_u16(handle, KEY_DDP_PORT, cfg->ddp_port);
    if (port_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to write ddp_port: %s", esp_err_to_name(port_err));
        nvs_close(handle);
        return port_err;
    }
    err = nvs_commit(handle);
    nvs_close(handle);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Stored config (led_count=%u, ddp_port=%u)", cfg->led_count, cfg->ddp_port);
    } else {
        ESP_LOGE(TAG, "Failed to commit config: %s", esp_err_to_name(err));
    }
    return err;
}
