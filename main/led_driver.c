#include <math.h>
#include "led_driver.h"
#include "led_strip.h"

#define RMT_RESOLUTION_HZ (10 * 1000 * 1000)

static led_strip_handle_t s_strip;
static size_t s_led_count;

static uint8_t to_u8(float v) {
    if (v < 0.0f) {
        v = 0.0f;
    } else if (v > 1.0f) {
        v = 1.0f;
    }
    return (uint8_t)lroundf(v * 255.0f);
}

esp_err_t led_driver_init(uint32_t gpio_num, size_t led_count) {
    if (led_count == 0) {
        return ESP_ERR_INVALID_SIZE;
    }

    led_strip_config_t strip_config = {
        .strip_gpio_num = (int)gpio_num,
        .max_leds = (int)led_count,
    };

    led_strip_rmt_config_t rmt_config = {
        .resolution_hz = RMT_RESOLUTION_HZ,
    };

    esp_err_t err = led_strip_new_rmt_device(&strip_config, &rmt_config, &s_strip);
    if (err != ESP_OK) {
        s_strip = NULL;
        s_led_count = 0;
        return err;
    }

    s_led_count = led_count;
    return ESP_OK;
}

size_t led_driver_count(void) {
    return s_led_count;
}

void led_driver_render(const rgb_f *colors, size_t count) {
    if (!s_strip || !colors) {
        return;
    }

    if (count > s_led_count) {
        count = s_led_count;
    }

    for (size_t i = 0; i < count; ++i) {
        const rgb_f *c = &colors[i];
        uint8_t r = to_u8(c->r);
        uint8_t g = to_u8(c->g);
        uint8_t b = to_u8(c->b);
        ESP_ERROR_CHECK(led_strip_set_pixel(s_strip, i, g, r, b));
    }

    ESP_ERROR_CHECK(led_strip_refresh(s_strip));
}
