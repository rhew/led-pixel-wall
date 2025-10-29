#ifndef LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H
#define LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct effects_random_breathe_state effects_random_breathe_state_t;

typedef struct {
    size_t max_active;
    uint32_t fade_in_ms;
    uint32_t hold_ms;
    uint32_t fade_out_ms;
    float max_brightness;
} effects_random_breathe_params_t;

esp_err_t effects_random_breathe_create(effects_random_breathe_state_t **out_state,
                                        const uint16_t *indices,
                                        size_t led_count,
                                        const effects_random_breathe_params_t *params);
void effects_random_breathe_destroy(effects_random_breathe_state_t *state);
void effects_random_breathe_tick(effects_random_breathe_state_t *state, uint32_t step_ms);

#endif // LED_PIXEL_WALL_EFFECTS_RANDOM_BREATHE_H
