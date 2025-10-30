#include "effect_registry.h"
#include "effects_cylon.h"
#include "effects_fast_blink.h"
#include "effects_pattern.h"
#include "effects_random_breathe.h"
#include "effects_static_on.h"

static esp_err_t create_random(void **state,
                               const uint16_t *indices,
                               size_t led_count,
                               const void *params) {
    return effects_random_breathe_create((effects_random_breathe_state_t **)state,
                                         indices,
                                         led_count,
                                         (const effects_random_breathe_params_t *)params);
}

static void destroy_random(void *state) {
    effects_random_breathe_destroy((effects_random_breathe_state_t *)state);
}

static void tick_random(void *state, uint32_t step_ms) {
    effects_random_breathe_tick((effects_random_breathe_state_t *)state, step_ms);
}

static esp_err_t create_fast(void **state,
                             const uint16_t *indices,
                             size_t led_count,
                             const void *params) {
    return effects_fast_blink_create((effects_fast_blink_state_t **)state,
                                     indices,
                                     led_count,
                                     (const effects_fast_blink_params_t *)params);
}

static void destroy_fast(void *state) {
    effects_fast_blink_destroy((effects_fast_blink_state_t *)state);
}

static void tick_fast(void *state, uint32_t step_ms) {
    effects_fast_blink_tick((effects_fast_blink_state_t *)state, step_ms);
}

static esp_err_t create_cylon(void **state,
                              const uint16_t *indices,
                              size_t led_count,
                              const void *params) {
    return effects_cylon_create((effects_cylon_state_t **)state,
                                indices,
                                led_count,
                                (const effects_cylon_params_t *)params);
}

static void destroy_cylon(void *state) {
    effects_cylon_destroy((effects_cylon_state_t *)state);
}

static void tick_cylon(void *state, uint32_t step_ms) {
    effects_cylon_tick((effects_cylon_state_t *)state, step_ms);
}

static esp_err_t create_static_on(void **state,
                                  const uint16_t *indices,
                                  size_t led_count,
                                  const void *params) {
    return effects_static_on_create((effects_static_on_state_t **)state,
                                    indices,
                                    led_count,
                                    (const effects_static_on_params_t *)params);
}

static void destroy_static_on(void *state) {
    effects_static_on_destroy((effects_static_on_state_t *)state);
}

static void tick_static_on(void *state, uint32_t step_ms) {
    effects_static_on_tick((effects_static_on_state_t *)state, step_ms);
}

static const effect_descriptor_t kDescriptors[] = {
    [EFFECT_TYPE_RANDOM_BREATHE] = {
        .type = EFFECT_TYPE_RANDOM_BREATHE,
        .create = create_random,
        .destroy = destroy_random,
        .tick = tick_random,
    },
    [EFFECT_TYPE_FAST_BLINK] = {
        .type = EFFECT_TYPE_FAST_BLINK,
        .create = create_fast,
        .destroy = destroy_fast,
        .tick = tick_fast,
    },
    [EFFECT_TYPE_CYLON] = {
        .type = EFFECT_TYPE_CYLON,
        .create = create_cylon,
        .destroy = destroy_cylon,
        .tick = tick_cylon,
    },
    [EFFECT_TYPE_PATTERN] = {
        .type = EFFECT_TYPE_PATTERN,
        .create = effects_pattern_create,
        .destroy = effects_pattern_destroy,
        .tick = effects_pattern_tick,
    },
    [EFFECT_TYPE_STATIC_ON] = {
        .type = EFFECT_TYPE_STATIC_ON,
        .create = create_static_on,
        .destroy = destroy_static_on,
        .tick = tick_static_on,
    },
};

const effect_descriptor_t *effect_registry_lookup(effect_type_t type) {
    if (type >= (sizeof(kDescriptors) / sizeof(kDescriptors[0]))) {
        return NULL;
    }
    return &kDescriptors[type];
}
