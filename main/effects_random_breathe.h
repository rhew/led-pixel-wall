#ifndef LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H
#define LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    size_t led_count;
    size_t max_active;
    uint32_t fade_in_ms;
    uint32_t hold_ms;
    uint32_t fade_out_ms;
    float max_brightness;
} effects_random_breathe_config_t;

esp_err_t effects_random_breathe_init(const effects_random_breathe_config_t *config);
void effects_random_breathe_tick(uint32_t step_ms);

#endif // LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H
