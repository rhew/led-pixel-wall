#ifndef LED_PIXEL_WALL_LED_DRIVER_H
#define LED_PIXEL_WALL_LED_DRIVER_H

#include <stddef.h>
#include "esp_err.h"
#include "effects.h"

esp_err_t led_driver_init(uint32_t gpio_num, size_t led_count);
size_t led_driver_count(void);
void led_driver_render(const rgb_f *colors, size_t count);

#endif // LED_PIXEL_WALL_LED_DRIVER_H
