#include <stdlib.h>
#include <string.h>
#include "effects.h"

typedef struct {
    rgb_f start;
    rgb_f target;
    rgb_f current;
    uint32_t elapsed_ms;
    uint32_t total_ms;
    bool active;
} transition_slot_t;

static transition_slot_t *s_transitions;
static size_t s_led_count;

static float clamp01(float v) {
    if (v < 0.0f) {
        return 0.0f;
    }
    if (v > 1.0f) {
        return 1.0f;
    }
    return v;
}

static rgb_f lerp(const rgb_f *a, const rgb_f *b, float t) {
    rgb_f out = {
        .r = a->r + (b->r - a->r) * t,
        .g = a->g + (b->g - a->g) * t,
        .b = a->b + (b->b - a->b) * t,
    };
    out.r = clamp01(out.r);
    out.g = clamp01(out.g);
    out.b = clamp01(out.b);
    return out;
}

esp_err_t effects_init(size_t led_count) {
    if (led_count == 0) {
        return ESP_ERR_INVALID_SIZE;
    }
    if (s_transitions != NULL) {
        free(s_transitions);
        s_transitions = NULL;
        s_led_count = 0;
    }

    s_transitions = calloc(led_count, sizeof(transition_slot_t));
    if (!s_transitions) {
        return ESP_ERR_NO_MEM;
    }

    s_led_count = led_count;
    return ESP_OK;
}

void effects_deinit(void) {
    free(s_transitions);
    s_transitions = NULL;
    s_led_count = 0;
}

size_t effects_led_count(void) {
    return s_led_count;
}

void effects_step(uint32_t step_ms) {
    if (!s_transitions) {
        return;
    }

    for (size_t i = 0; i < s_led_count; ++i) {
        transition_slot_t *slot = &s_transitions[i];
        if (!slot->active) {
            slot->current = slot->target;
            continue;
        }

        if (slot->total_ms == 0) {
            slot->current = slot->target;
            slot->active = false;
            continue;
        }

        uint32_t next_elapsed = slot->elapsed_ms + step_ms;
        if (next_elapsed >= slot->total_ms) {
            next_elapsed = slot->total_ms;
            slot->active = false;
        }

        float t = (float)next_elapsed / (float)slot->total_ms;
        slot->current = lerp(&slot->start, &slot->target, t);
        slot->elapsed_ms = next_elapsed;
    }
}

void effects_drive_to(size_t index, rgb_f target, uint32_t duration_ms) {
    if (!s_transitions || index >= s_led_count) {
        return;
    }

    transition_slot_t *slot = &s_transitions[index];
    slot->start = slot->current;
    slot->target.r = clamp01(target.r);
    slot->target.g = clamp01(target.g);
    slot->target.b = clamp01(target.b);
    slot->elapsed_ms = 0;
    slot->total_ms = duration_ms;
    slot->active = duration_ms > 0;

    if (!slot->active) {
        slot->current = slot->target;
    }
}

bool effects_transition_active(size_t index) {
    if (!s_transitions || index >= s_led_count) {
        return false;
    }
    return s_transitions[index].active;
}

rgb_f effects_current_color(size_t index) {
    if (!s_transitions || index >= s_led_count) {
        return (rgb_f){0, 0, 0};
    }
    return s_transitions[index].current;
}
