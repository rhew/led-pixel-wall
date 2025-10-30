#ifndef LED_PIXEL_WALL_EFFECTS_PATTERN_H
#define LED_PIXEL_WALL_EFFECTS_PATTERN_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effects.h"

typedef struct effects_pattern_state effects_pattern_state_t;

typedef struct {
    const rgb_f *colors;
    const uint32_t *durations_ms;
    size_t step_count;
    uint32_t fade_ms;
} effects_pattern_params_t;

esp_err_t effects_pattern_create(effects_pattern_state_t **out_state,
                                 const uint16_t *indices,
                                 size_t led_count,
                                 const effects_pattern_params_t *params);
void effects_pattern_destroy(effects_pattern_state_t *state);
void effects_pattern_tick(effects_pattern_state_t *state, uint32_t step_ms);

#endif
