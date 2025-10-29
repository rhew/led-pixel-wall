#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "segment.h"
#include "effect_registry.h"

typedef struct {
    const segment_desc_t *desc;
    const effect_descriptor_t *effect;
    void *state;
} segment_runtime_t;

static segment_runtime_t *s_segments;
static size_t s_segment_count;

esp_err_t segment_init(const segment_desc_t *segments, size_t segment_count) {
    if (!segments || segment_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t total_leds = effects_led_count();
    bool *used = calloc(total_leds, sizeof(bool));
    if (!used) {
        return ESP_ERR_NO_MEM;
    }

    segment_runtime_t *runtime = calloc(segment_count, sizeof(segment_runtime_t));
    if (!runtime) {
        free(used);
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = ESP_OK;
    for (size_t i = 0; i < segment_count; ++i) {
        const segment_desc_t *desc = &segments[i];
        const effect_descriptor_t *effect = effect_registry_lookup((effect_type_t)desc->effect_id);
        if (!effect) {
            err = ESP_ERR_NOT_SUPPORTED;
            break;
        }

        for (size_t j = 0; j < desc->count; ++j) {
            uint16_t index = desc->indices[j];
            if (index >= total_leds || used[index]) {
                err = ESP_ERR_INVALID_STATE;
                break;
            }
            used[index] = true;
        }
        if (err != ESP_OK) {
            break;
        }

        void *state = NULL;
        err = effect->create(&state, desc->indices, desc->count, desc->effect_params);
        if (err != ESP_OK) {
            break;
        }

        runtime[i].desc = desc;
        runtime[i].effect = effect;
        runtime[i].state = state;
    }

    free(used);

    if (err != ESP_OK) {
        for (size_t i = 0; i < segment_count; ++i) {
            if (runtime[i].effect && runtime[i].state) {
                runtime[i].effect->destroy(runtime[i].state);
            }
        }
        free(runtime);
        return err;
    }

    s_segments = runtime;
    s_segment_count = segment_count;
    return ESP_OK;
}

void segment_shutdown(void) {
    if (!s_segments) {
        return;
    }
    for (size_t i = 0; i < s_segment_count; ++i) {
        if (s_segments[i].effect && s_segments[i].state) {
            s_segments[i].effect->destroy(s_segments[i].state);
        }
    }
    free(s_segments);
    s_segments = NULL;
    s_segment_count = 0;
}

void segment_tick(uint32_t step_ms) {
    if (!s_segments) {
        return;
    }
    for (size_t i = 0; i < s_segment_count; ++i) {
        s_segments[i].effect->tick(s_segments[i].state, step_ms);
    }
}
