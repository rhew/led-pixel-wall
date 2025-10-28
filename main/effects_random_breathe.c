#include <math.h>
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

static effects_random_breathe_config_t s_cfg;
static slot_t *s_slots;

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

esp_err_t effects_random_breathe_init(const effects_random_breathe_config_t *config) {
    if (!config || config->led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_slots) {
        free(s_slots);
        s_slots = NULL;
    }

    s_slots = calloc(config->led_count, sizeof(slot_t));
    if (!s_slots) {
        return ESP_ERR_NO_MEM;
    }

    s_cfg = *config;
    if (s_cfg.max_active > s_cfg.led_count) {
        s_cfg.max_active = s_cfg.led_count;
    }
    return ESP_OK;
}

static size_t active_slots(void) {
    size_t count = 0;
    for (size_t i = 0; i < s_cfg.led_count; ++i) {
        if (s_slots[i].phase != SLOT_INACTIVE) {
            count++;
        }
    }
    return count;
}

static void update_hold_slots(uint32_t step_ms) {
    for (size_t i = 0; i < s_cfg.led_count; ++i) {
        slot_t *slot = &s_slots[i];
        if (slot->phase != SLOT_HOLDING) {
            continue;
        }
        if (slot->hold_remaining_ms > step_ms) {
            slot->hold_remaining_ms -= step_ms;
        } else {
            slot->hold_remaining_ms = 0;
            slot->phase = SLOT_FADING_OUT;
            effects_drive_to(i, (rgb_f){0, 0, 0}, s_cfg.fade_out_ms);
        }
    }
}

static void sync_with_transitions(void) {
    for (size_t i = 0; i < s_cfg.led_count; ++i) {
        slot_t *slot = &s_slots[i];
        bool active = effects_transition_active(i);

        switch (slot->phase) {
        case SLOT_FADING_IN:
            if (!active) {
                slot->phase = SLOT_HOLDING;
                slot->hold_remaining_ms = s_cfg.hold_ms;
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

static void spawn_new_slots(void) {
    if (s_cfg.max_active == 0) {
        return;
    }

    if (active_slots() >= s_cfg.max_active) {
        return;
    }

    size_t attempts = 0;
    size_t max_attempts = s_cfg.led_count;
    while (attempts < max_attempts) {
        size_t index = (size_t)(rand() % s_cfg.led_count);
        slot_t *slot = &s_slots[index];
        if (slot->phase == SLOT_INACTIVE) {
            slot->color = random_color(s_cfg.max_brightness);
            slot->phase = SLOT_FADING_IN;
            slot->hold_remaining_ms = s_cfg.hold_ms;
            effects_drive_to(index, slot->color, s_cfg.fade_in_ms);
            break;
        }
        attempts++;
    }
}

void effects_random_breathe_tick(uint32_t step_ms) {
    if (!s_slots || s_cfg.led_count == 0) {
        return;
    }

    update_hold_slots(step_ms);
    sync_with_transitions();
    spawn_new_slots();
}
