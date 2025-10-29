#include <stdlib.h>
#include "effects_cylon.h"

struct effects_cylon_state {
    const uint16_t *indices;
    size_t led_count;
    uint32_t fade_ms;
    uint32_t dwell_ms;
    rgb_f color;
    size_t current;
    int direction; // +1 forward, -1 backward
    uint32_t elapsed;
};

esp_err_t effects_cylon_create(effects_cylon_state_t **out_state,
                               const uint16_t *indices,
                               size_t led_count,
                               const effects_cylon_params_t *params) {
    if (!out_state || !indices || !params || led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    effects_cylon_state_t *state = calloc(1, sizeof(*state));
    if (!state) {
        return ESP_ERR_NO_MEM;
    }

    state->indices = indices;
    state->led_count = led_count;
    state->fade_ms = params->fade_ms;
    state->dwell_ms = params->dwell_ms;
    state->color = params->color;
    state->current = 0;
    state->direction = 1;
    state->elapsed = 0;

    *out_state = state;
    return ESP_OK;
}

void effects_cylon_destroy(effects_cylon_state_t *state) {
    free(state);
}

static void set_led(effects_cylon_state_t *state, size_t offset, rgb_f color, uint32_t fade) {
    if (offset >= state->led_count) {
        return;
    }
    effects_drive_to(state->indices[offset], color, fade);
}

void effects_cylon_tick(effects_cylon_state_t *state, uint32_t step_ms) {
    if (!state) {
        return;
    }

    state->elapsed += step_ms;
    if (state->elapsed < state->dwell_ms) {
        return;
    }

    state->elapsed = 0;

    // Turn off current LED
    set_led(state, state->current, (rgb_f){0, 0, 0}, state->fade_ms);

    // Move position
    if (state->direction > 0) {
        if (state->current + 1 >= state->led_count) {
            state->direction = -1;
            state->current = state->led_count - 2;
        } else {
            state->current++;
        }
    } else {
        if (state->current == 0) {
            state->direction = 1;
            state->current = 1;
        } else {
            state->current--;
        }
    }

    // Light new LED
    set_led(state, state->current, state->color, state->fade_ms);
}
