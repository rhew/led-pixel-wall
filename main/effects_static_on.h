#ifndef LED_PIXEL_WALL_EFFECTS_STATIC_ON_H
#define LED_PIXEL_WALL_EFFECTS_STATIC_ON_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effects.h"

typedef struct effects_static_on_state effects_static_on_state_t;

typedef struct {
    rgb_f color;
    uint32_t fade_ms;
} effects_static_on_params_t;

esp_err_t effects_static_on_create(effects_static_on_state_t **out_state,
                                   const uint16_t *indices,
                                   size_t led_count,
                                   const effects_static_on_params_t *params);
void effects_static_on_destroy(effects_static_on_state_t *state);
void effects_static_on_tick(effects_static_on_state_t *state, uint32_t step_ms);

#endif
