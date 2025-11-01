#ifndef LED_PIXEL_WALL_LED_DRIVER_H
#define LED_PIXEL_WALL_LED_DRIVER_H

#include <stddef.h>
#include "esp_err.h"

esp_err_t led_driver_init(uint32_t gpio_num, size_t led_count);
esp_err_t led_driver_set_pixel_count(size_t led_count);
size_t led_driver_count(void);
void led_driver_render_rgb(const uint8_t *rgb, size_t pixel_count);
esp_err_t led_driver_set_pixel(size_t index, uint8_t r, uint8_t g, uint8_t b);

#endif // LED_PIXEL_WALL_LED_DRIVER_H
