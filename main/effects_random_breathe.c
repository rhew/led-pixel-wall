#include <math.h>
#include <stdbool.h>
#include <stdlib.h>
#include "effects_random_breathe.h"
#include "effects.h"

typedef enum {
    SLOT_INACTIVE = 0,
    SLOT_FADING_IN,
    SLOT_HOLDING,
    SLOT_FADING_OUT,
} slot_phase_t;

typedef struct {
    slot_phase_t phase;
    uint32_t hold_remaining_ms;
    rgb_f color;
} slot_t;

struct effects_random_breathe_state {
    const uint16_t *indices;
    size_t led_count;
    size_t max_active;
    uint32_t fade_in_ms;
    uint32_t hold_ms;
    uint32_t fade_out_ms;
    float max_brightness;
    slot_t *slots;
};

static float clamp01(float v) {
    if (v < 0.0f) {
        return 0.0f;
    }
    if (v > 1.0f) {
        return 1.0f;
    }
    return v;
}

static rgb_f hsv_to_rgb(float h, float s, float v) {
    float hh = fmodf(fabsf(h), 1.0f) * 6.0f;
    float c = v * s;
    float x = c * (1.0f - fabsf(fmodf(hh, 2.0f) - 1.0f));
    float m = v - c;

    rgb_f rgb = {m, m, m};
    if (hh < 1.0f) {
        rgb.r += c;
        rgb.g += x;
    } else if (hh < 2.0f) {
        rgb.r += x;
        rgb.g += c;
    } else if (hh < 3.0f) {
        rgb.g += c;
        rgb.b += x;
    } else if (hh < 4.0f) {
        rgb.g += x;
        rgb.b += c;
    } else if (hh < 5.0f) {
        rgb.r += x;
        rgb.b += c;
    } else {
        rgb.r += c;
        rgb.b += x;
    }

    rgb.r = clamp01(rgb.r);
    rgb.g = clamp01(rgb.g);
    rgb.b = clamp01(rgb.b);
    return rgb;
}

static rgb_f random_color(float max_brightness) {
    if (max_brightness <= 0.0f) {
        return (rgb_f){0, 0, 0};
    }
    float hue = (float)(rand() % 1000) / 1000.0f;
    return hsv_to_rgb(hue, 1.0f, clamp01(max_brightness));
}

esp_err_t effects_random_breathe_create(effects_random_breathe_state_t **out_state,
                                        const uint16_t *indices,
                                        size_t led_count,
                                        const effects_random_breathe_params_t *params) {
    if (!out_state || !indices || !params || led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    effects_random_breathe_state_t *state = calloc(1, sizeof(*state));
    if (!state) {
        return ESP_ERR_NO_MEM;
    }

    state->slots = calloc(led_count, sizeof(slot_t));
    if (!state->slots) {
        free(state);
        return ESP_ERR_NO_MEM;
    }

    state->indices = indices;
    state->led_count = led_count;
    state->max_active = params->max_active > led_count ? led_count : params->max_active;
    state->fade_in_ms = params->fade_in_ms;
    state->hold_ms = params->hold_ms;
    state->fade_out_ms = params->fade_out_ms;
    state->max_brightness = params->max_brightness;

    *out_state = state;
    return ESP_OK;
}

void effects_random_breathe_destroy(effects_random_breathe_state_t *state) {
    if (!state) {
        return;
    }
    free(state->slots);
    free(state);
}

static size_t active_slots(const effects_random_breathe_state_t *state) {
    size_t count = 0;
    for (size_t i = 0; i < state->led_count; ++i) {
        if (state->slots[i].phase != SLOT_INACTIVE) {
            count++;
        }
    }
    return count;
}

static void update_hold_slots(effects_random_breathe_state_t *state, uint32_t step_ms) {
    for (size_t i = 0; i < state->led_count; ++i) {
        slot_t *slot = &state->slots[i];
        if (slot->phase != SLOT_HOLDING) {
            continue;
        }
        if (slot->hold_remaining_ms > step_ms) {
            slot->hold_remaining_ms -= step_ms;
        } else {
            slot->hold_remaining_ms = 0;
            slot->phase = SLOT_FADING_OUT;
            effects_drive_to(state->indices[i], (rgb_f){0, 0, 0}, state->fade_out_ms);
        }
    }
}

static void sync_with_transitions(effects_random_breathe_state_t *state) {
    for (size_t i = 0; i < state->led_count; ++i) {
        slot_t *slot = &state->slots[i];
        bool active = effects_transition_active(state->indices[i]);

        switch (slot->phase) {
        case SLOT_FADING_IN:
            if (!active) {
                slot->phase = SLOT_HOLDING;
                slot->hold_remaining_ms = state->hold_ms;
            }
            break;
        case SLOT_FADING_OUT:
            if (!active) {
                slot->phase = SLOT_INACTIVE;
            }
            break;
        default:
            break;
        }
    }
}

static void spawn_new_slots(effects_random_breathe_state_t *state) {
    if (state->max_active == 0) {
        return;
    }

    if (active_slots(state) >= state->max_active) {
        return;
    }

    size_t attempts = 0;
    size_t max_attempts = state->led_count;
    while (attempts < max_attempts) {
        size_t index = (size_t)(rand() % state->led_count);
        slot_t *slot = &state->slots[index];
        if (slot->phase == SLOT_INACTIVE) {
            slot->color = random_color(state->max_brightness);
            slot->phase = SLOT_FADING_IN;
            slot->hold_remaining_ms = state->hold_ms;
            effects_drive_to(state->indices[index], slot->color, state->fade_in_ms);
            break;
        }
        attempts++;
    }
}

void effects_random_breathe_tick(effects_random_breathe_state_t *state, uint32_t step_ms) {
    if (!state || state->led_count == 0) {
        return;
    }

    update_hold_slots(state, step_ms);
    sync_with_transitions(state);
    spawn_new_slots(state);
}
