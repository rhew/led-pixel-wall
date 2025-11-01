#include "led_driver.h"

#include <stdint.h>
#include "esp_err.h"
#include "esp_log.h"
#include "led_strip.h"

#define TAG "led_driver"
#define RMT_RESOLUTION_HZ (10 * 1000 * 1000)

static led_strip_handle_t s_strip;
static size_t s_led_count;
static uint32_t s_gpio_pin = UINT32_MAX;

static esp_err_t configure_strip(size_t led_count) {
    if (led_count == 0) {
        return ESP_ERR_INVALID_SIZE;
    }
    if (s_gpio_pin == UINT32_MAX) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_strip) {
        led_strip_del(s_strip);
        s_strip = NULL;
    }

    led_strip_config_t strip_config = {
        .strip_gpio_num = (int)s_gpio_pin,
        .max_leds = (int)led_count,
    };

    led_strip_rmt_config_t rmt_config = {
        .resolution_hz = RMT_RESOLUTION_HZ,
    };

    esp_err_t err = led_strip_new_rmt_device(&strip_config, &rmt_config, &s_strip);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure LED strip: %s", esp_err_to_name(err));
        s_strip = NULL;
        s_led_count = 0;
        return err;
    }

    s_led_count = led_count;
    esp_err_t clear_err = led_strip_clear(s_strip);
    if (clear_err == ESP_OK) {
        led_strip_refresh(s_strip);
    }
    ESP_LOGI(TAG, "Strip configured on GPIO %u for %u LEDs",
             (unsigned int)s_gpio_pin,
             (unsigned int)led_count);
    return ESP_OK;
}

esp_err_t led_driver_init(uint32_t gpio_num, size_t led_count) {
    s_gpio_pin = gpio_num;
    return configure_strip(led_count);
}

esp_err_t led_driver_set_pixel_count(size_t led_count) {
    return configure_strip(led_count);
}

size_t led_driver_count(void) {
    return s_led_count;
}

void led_driver_render_rgb(const uint8_t *rgb, size_t pixel_count) {
    if (!s_strip || !rgb) {
        return;
    }

    if (pixel_count > s_led_count) {
        pixel_count = s_led_count;
    }

    for (size_t i = 0; i < pixel_count; ++i) {
        size_t base = i * 3;
        uint8_t r = rgb[base];
        uint8_t g = rgb[base + 1];
        uint8_t b = rgb[base + 2];
        ESP_ERROR_CHECK(led_strip_set_pixel(s_strip, i, g, r, b));
    }

    ESP_ERROR_CHECK(led_strip_refresh(s_strip));
}

esp_err_t led_driver_set_pixel(size_t index, uint8_t r, uint8_t g, uint8_t b) {
    if (!s_strip || index >= s_led_count) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t err = led_strip_set_pixel(s_strip, (int)index, g, r, b);
    if (err != ESP_OK) {
        return err;
    }
    return led_strip_refresh(s_strip);
}
