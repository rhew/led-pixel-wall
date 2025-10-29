#ifndef LED_PIXEL_WALL_EFFECTS_FAST_BLINK_H
#define LED_PIXEL_WALL_EFFECTS_FAST_BLINK_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effects.h"

typedef struct effects_fast_blink_state effects_fast_blink_state_t;

typedef struct {
    uint32_t on_ms;
    uint32_t off_ms;
    rgb_f color_on;
    uint32_t fade_ms;
} effects_fast_blink_params_t;

esp_err_t effects_fast_blink_create(effects_fast_blink_state_t **out_state,
                                    const uint16_t *indices,
                                    size_t led_count,
                                    const effects_fast_blink_params_t *params);
void effects_fast_blink_destroy(effects_fast_blink_state_t *state);
void effects_fast_blink_tick(effects_fast_blink_state_t *state, uint32_t step_ms);

#endif
