#ifndef LED_PIXEL_WALL_EFFECT_REGISTRY_H
#define LED_PIXEL_WALL_EFFECT_REGISTRY_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effects.h"

typedef enum {
    EFFECT_TYPE_RANDOM_BREATHE,
    EFFECT_TYPE_FAST_BLINK,
    EFFECT_TYPE_CYLON,
    EFFECT_TYPE_PATTERN,
    EFFECT_TYPE_STATIC_ON,
} effect_type_t;

typedef esp_err_t (*effect_create_fn)(void **state,
                                      const uint16_t *indices,
                                      size_t led_count,
                                      const void *params);
typedef void (*effect_destroy_fn)(void *state);
typedef void (*effect_tick_fn)(void *state, uint32_t step_ms);

typedef struct {
    effect_type_t type;
    effect_create_fn create;
    effect_destroy_fn destroy;
    effect_tick_fn tick;
} effect_descriptor_t;

const effect_descriptor_t *effect_registry_lookup(effect_type_t type);

#endif
