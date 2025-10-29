#ifndef LED_PIXEL_WALL_EFFECTS_CYLON_H
#define LED_PIXEL_WALL_EFFECTS_CYLON_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effects.h"

typedef struct effects_cylon_state effects_cylon_state_t;

typedef struct {
    uint32_t fade_ms;
    uint32_t dwell_ms;
    rgb_f color;
} effects_cylon_params_t;

esp_err_t effects_cylon_create(effects_cylon_state_t **out_state,
                               const uint16_t *indices,
                               size_t led_count,
                               const effects_cylon_params_t *params);
void effects_cylon_destroy(effects_cylon_state_t *state);
void effects_cylon_tick(effects_cylon_state_t *state, uint32_t step_ms);

#endif
