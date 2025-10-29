#include <stdbool.h>
#include <stdlib.h>
#include "effects_static_on.h"

struct effects_static_on_state {
    const uint16_t *indices;
    size_t led_count;
    rgb_f color;
    uint32_t fade_ms;
    bool initialized;
};

esp_err_t effects_static_on_create(effects_static_on_state_t **out_state,
                                   const uint16_t *indices,
                                   size_t led_count,
                                   const effects_static_on_params_t *params) {
    if (!out_state || !indices || !params || led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    effects_static_on_state_t *state = calloc(1, sizeof(*state));
    if (!state) {
        return ESP_ERR_NO_MEM;
    }

    state->indices = indices;
    state->led_count = led_count;
    state->color = params->color;
    state->fade_ms = params->fade_ms;
    state->initialized = false;

    *out_state = state;
    return ESP_OK;
}

void effects_static_on_destroy(effects_static_on_state_t *state) {
    free(state);
}

static void apply_color(const effects_static_on_state_t *state) {
    for (size_t i = 0; i < state->led_count; ++i) {
        effects_drive_to(state->indices[i], state->color, state->fade_ms);
    }
}

void effects_static_on_tick(effects_static_on_state_t *state, uint32_t step_ms) {
    (void)step_ms;
    if (!state) {
        return;
    }
    if (!state->initialized) {
        apply_color(state);
        state->initialized = true;
    }
}
