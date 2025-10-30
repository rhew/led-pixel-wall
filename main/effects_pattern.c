#include <stddef.h>
#include <stdlib.h>
#include "effects_pattern.h"

struct effects_pattern_state {
    const uint16_t *indices;
    size_t led_count;
    const rgb_f *colors;
    const uint32_t *durations_ms;
    size_t step_count;
    uint32_t fade_ms;
    size_t current_step;
    uint32_t elapsed_ms;
};

static void apply_step(struct effects_pattern_state *state) {
    if (!state || state->step_count == 0) {
        return;
    }

    rgb_f color = state->colors[state->current_step];
    for (size_t i = 0; i < state->led_count; ++i) {
        effects_drive_to(state->indices[i], color, state->fade_ms);
    }
}

esp_err_t effects_pattern_create(effects_pattern_state_t **out_state,
                                 const uint16_t *indices,
                                 size_t led_count,
                                 const effects_pattern_params_t *params) {
    if (!out_state || !indices || !params || led_count == 0 || params->step_count == 0 ||
        !params->colors || !params->durations_ms) {
        return ESP_ERR_INVALID_ARG;
    }

    struct effects_pattern_state *state = calloc(1, sizeof(*state));
    if (!state) {
        return ESP_ERR_NO_MEM;
    }

    state->indices = indices;
    state->led_count = led_count;
    state->colors = params->colors;
    state->durations_ms = params->durations_ms;
    state->step_count = params->step_count;
    state->fade_ms = params->fade_ms;
    state->current_step = 0;
    state->elapsed_ms = 0;

    apply_step(state);

    *out_state = state;
    return ESP_OK;
}

void effects_pattern_destroy(effects_pattern_state_t *state) {
    free(state);
}

void effects_pattern_tick(effects_pattern_state_t *state, uint32_t step_ms) {
    if (!state || state->step_count == 0) {
        return;
    }

    state->elapsed_ms += step_ms;

    size_t guard = 0;
    while (guard < state->step_count) {
        uint32_t duration = state->durations_ms[state->current_step];
        bool advance = false;

        if (duration == 0) {
            advance = true;
        } else if (state->elapsed_ms >= duration) {
            state->elapsed_ms -= duration;
            advance = true;
        }

        if (!advance) {
            break;
        }

        state->current_step = (state->current_step + 1) % state->step_count;
        apply_step(state);
        guard++;
    }
}
