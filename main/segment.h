#ifndef LED_PIXEL_WALL_SEGMENT_H
#define LED_PIXEL_WALL_SEGMENT_H

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "effect_registry.h"

typedef enum {
    SEGMENT_EFFECT_RANDOM_BREATHE = EFFECT_TYPE_RANDOM_BREATHE,
    SEGMENT_EFFECT_FAST_BLINK = EFFECT_TYPE_FAST_BLINK,
    SEGMENT_EFFECT_CYLON = EFFECT_TYPE_CYLON,
    SEGMENT_EFFECT_STATIC_ON = EFFECT_TYPE_STATIC_ON,
} segment_effect_id_t;

typedef struct {
    const char *name;
    const uint16_t *indices;
    size_t count;
    segment_effect_id_t effect_id;
    const void *effect_params;
} segment_desc_t;

esp_err_t segment_init(const segment_desc_t *segments, size_t segment_count);
void segment_shutdown(void);
void segment_tick(uint32_t step_ms);

#endif
