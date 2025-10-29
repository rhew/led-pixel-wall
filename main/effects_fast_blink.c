#include <stdbool.h>
#include <stdlib.h>
#include "effects_fast_blink.h"

struct effects_fast_blink_state {
    const uint16_t *indices;
    size_t led_count;
    uint32_t on_ms;
    uint32_t off_ms;
    uint32_t fade_ms;
    rgb_f color_on;
    uint32_t elapsed_ms;
    bool active;
};

esp_err_t effects_fast_blink_create(effects_fast_blink_state_t **out_state,
                                    const uint16_t *indices,
                                    size_t led_count,
                                    const effects_fast_blink_params_t *params) {
    if (!out_state || !indices || !params || led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    effects_fast_blink_state_t *state = calloc(1, sizeof(*state));
    if (!state) {
        return ESP_ERR_NO_MEM;
    }

    state->indices = indices;
    state->led_count = led_count;
    state->on_ms = params->on_ms;
    state->off_ms = params->off_ms;
    state->fade_ms = params->fade_ms;
    state->color_on = params->color_on;
    state->elapsed_ms = 0;
    state->active = false;

    *out_state = state;
    return ESP_OK;
}

void effects_fast_blink_destroy(effects_fast_blink_state_t *state) {
    free(state);
}

static void apply_state(const effects_fast_blink_state_t *state) {
    rgb_f target = state->active ? state->color_on : (rgb_f){0, 0, 0};
    for (size_t i = 0; i < state->led_count; ++i) {
        effects_drive_to(state->indices[i], target, state->fade_ms);
    }
}

void effects_fast_blink_tick(effects_fast_blink_state_t *state, uint32_t step_ms) {
    if (!state) {
        return;
    }

    uint32_t duration = state->active ? state->on_ms : state->off_ms;
    state->elapsed_ms += step_ms;
    bool toggled = false;

    while (state->elapsed_ms >= duration && duration > 0) {
        state->elapsed_ms -= duration;
        state->active = !state->active;
        toggled = true;
        duration = state->active ? state->on_ms : state->off_ms;
    }

    if (toggled) {
        apply_state(state);
    }
}
