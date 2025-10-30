#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "segment.h"
#include "effect_registry.h"

typedef struct {
    const segment_desc_t *desc;
    const effect_descriptor_t *effect;
    void *state;
    segment_effect_id_t effect_id;
} segment_runtime_t;

static segment_runtime_t *s_segments;
static size_t s_segment_count;
static SemaphoreHandle_t s_segment_mutex;

static void segment_lock(void) {
    if (s_segment_mutex) {
        xSemaphoreTake(s_segment_mutex, portMAX_DELAY);
    }
}

static void segment_unlock(void) {
    if (s_segment_mutex) {
        xSemaphoreGive(s_segment_mutex);
    }
}

static esp_err_t segment_apply_effect(segment_runtime_t *segment,
                                      segment_effect_id_t effect_id,
                                      const void *effect_params) {
    if (!segment) {
        return ESP_ERR_INVALID_ARG;
    }

    const effect_descriptor_t *descriptor = effect_registry_lookup((effect_type_t)effect_id);
    if (!descriptor) {
        return ESP_ERR_NOT_SUPPORTED;
    }

    void *state = NULL;
    esp_err_t err = descriptor->create(&state,
                                       segment->desc->indices,
                                       segment->desc->count,
                                       effect_params);
    if (err != ESP_OK) {
        return err;
    }

    if (segment->effect && segment->state) {
        segment->effect->destroy(segment->state);
    }

    segment->effect = descriptor;
    segment->state = state;
    segment->effect_id = effect_id;
    return ESP_OK;
}

esp_err_t segment_init(const segment_desc_t *segments, size_t segment_count) {
    if (!segments || segment_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_segment_mutex) {
        s_segment_mutex = xSemaphoreCreateMutex();
        if (!s_segment_mutex) {
            return ESP_ERR_NO_MEM;
        }
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

        runtime[i].desc = desc;
        runtime[i].effect = NULL;
        runtime[i].state = NULL;
        runtime[i].effect_id = desc->effect_id;

        err = segment_apply_effect(&runtime[i], desc->effect_id, desc->effect_params);
        if (err != ESP_OK) {
            break;
        }
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

    segment_lock();
    s_segments = runtime;
    s_segment_count = segment_count;
    segment_unlock();
    return ESP_OK;
}

void segment_shutdown(void) {
    if (!s_segment_mutex) {
        return;
    }

    segment_lock();
    if (!s_segments) {
        segment_unlock();
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
    segment_unlock();

    vSemaphoreDelete(s_segment_mutex);
    s_segment_mutex = NULL;
}

void segment_tick(uint32_t step_ms) {
    if (!s_segment_mutex) {
        return;
    }
    segment_lock();
    if (!s_segments) {
        segment_unlock();
        return;
    }
    for (size_t i = 0; i < s_segment_count; ++i) {
        s_segments[i].effect->tick(s_segments[i].state, step_ms);
    }
    segment_unlock();
}

esp_err_t segment_set_effect(const char *name,
                             segment_effect_id_t effect_id,
                             const void *effect_params) {
    if (!name || !s_segment_mutex) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t result = ESP_ERR_NOT_FOUND;
    segment_lock();
    if (!s_segments) {
        segment_unlock();
        return ESP_ERR_INVALID_STATE;
    }

    for (size_t i = 0; i < s_segment_count; ++i) {
        if (s_segments[i].desc && s_segments[i].desc->name &&
            strcmp(s_segments[i].desc->name, name) == 0) {
            result = segment_apply_effect(&s_segments[i], effect_id, effect_params);
            break;
        }
    }

    segment_unlock();
    return result;
}
