#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "effects.h"
#include "effects_cylon.h"
#include "effects_random_breathe.h"
#include "effects_static_on.h"
#include "led_driver.h"
#include "segment.h"

#define APP_LED_GPIO        3
#define APP_LED_COUNT       50
#define APP_FRAME_MS        50
#define APP_MAX_ACTIVE_LEDS 8
#define APP_FADE_IN_MS      600
#define APP_HOLD_MS         400
#define APP_FADE_OUT_MS     600
#define APP_MAX_BRIGHTNESS  0.5f
#define APP_STATIC_SEGMENT_COUNT 5
#define APP_STATIC_START_INDEX 0
#define APP_CYLON_SEGMENT_COUNT 10
#define APP_CYLON_START_INDEX 20

#define APP_RANDOM_SEGMENT_COUNT (APP_LED_COUNT - APP_CYLON_SEGMENT_COUNT - APP_STATIC_SEGMENT_COUNT)

static const uint16_t kCylonIndices[APP_CYLON_SEGMENT_COUNT] = {
    APP_CYLON_START_INDEX + 0,
    APP_CYLON_START_INDEX + 1,
    APP_CYLON_START_INDEX + 2,
    APP_CYLON_START_INDEX + 3,
    APP_CYLON_START_INDEX + 4,
    APP_CYLON_START_INDEX + 5,
    APP_CYLON_START_INDEX + 6,
    APP_CYLON_START_INDEX + 7,
    APP_CYLON_START_INDEX + 8,
    APP_CYLON_START_INDEX + 9,
};

static const uint16_t kStaticIndices[APP_STATIC_SEGMENT_COUNT] = {
    APP_STATIC_START_INDEX + 0,
    APP_STATIC_START_INDEX + 1,
    APP_STATIC_START_INDEX + 2,
    APP_STATIC_START_INDEX + 3,
    APP_STATIC_START_INDEX + 4,
};

static uint16_t gRandomIndices[APP_RANDOM_SEGMENT_COUNT];
static segment_desc_t gSegments[3];
static const effects_random_breathe_params_t kRandomParams = {
    .max_active = APP_MAX_ACTIVE_LEDS,
    .fade_in_ms = APP_FADE_IN_MS,
    .hold_ms = APP_HOLD_MS,
    .fade_out_ms = APP_FADE_OUT_MS,
    .max_brightness = APP_MAX_BRIGHTNESS,
};

static const effects_cylon_params_t kCylonParams = {
    .fade_ms = 450,
    .dwell_ms = 120,
    .color = {.r = 0.9f, .g = 0.0f, .b = 0.0f},
};

static const effects_static_on_params_t kStaticParams = {
    .color = {.r = 1.0f, .g = 1.0f, .b = 1.0f},
    .fade_ms = 0,
};

static void build_segments(void) {
    size_t out = 0;
    for (uint16_t i = 0; i < APP_LED_COUNT; ++i) {
        bool is_reserved = false;
        for (size_t j = 0; j < APP_CYLON_SEGMENT_COUNT; ++j) {
            if (kCylonIndices[j] == i) {
                is_reserved = true;
                break;
            }
        }
        if (!is_reserved) {
            for (size_t j = 0; j < APP_STATIC_SEGMENT_COUNT; ++j) {
                if (kStaticIndices[j] == i) {
                    is_reserved = true;
                    break;
                }
            }
        }
        if (!is_reserved) {
            gRandomIndices[out++] = i;
        }
    }
    assert(out == APP_RANDOM_SEGMENT_COUNT);

    gSegments[0] = (segment_desc_t){
        .name = "cylon",
        .indices = kCylonIndices,
        .count = APP_CYLON_SEGMENT_COUNT,
        .effect_id = SEGMENT_EFFECT_CYLON,
        .effect_params = &kCylonParams,
    };
    gSegments[1] = (segment_desc_t){
        .name = "briar-chapel",
        .indices = kStaticIndices,
        .count = APP_STATIC_SEGMENT_COUNT,
        .effect_id = SEGMENT_EFFECT_STATIC_ON,
        .effect_params = &kStaticParams,
    };
    gSegments[2] = (segment_desc_t){
        .name = "ambient",
        .indices = gRandomIndices,
        .count = APP_RANDOM_SEGMENT_COUNT,
        .effect_id = SEGMENT_EFFECT_RANDOM_BREATHE,
        .effect_params = &kRandomParams,
    };
}

static void render_task(void *arg) {
    const TickType_t delay_ticks = pdMS_TO_TICKS(APP_FRAME_MS);
    (void)arg;
    static rgb_f frame[APP_LED_COUNT];

    while (true) {
        segment_tick(APP_FRAME_MS);
        effects_step(APP_FRAME_MS);
        size_t count = led_driver_count();
        if (count > APP_LED_COUNT) {
            count = APP_LED_COUNT;
        }
        for (size_t i = 0; i < count; ++i) {
            frame[i] = effects_current_color(i);
        }
        led_driver_render(frame, count);
        vTaskDelay(delay_ticks);
    }
}

void app_main(void) {
    ESP_ERROR_CHECK(led_driver_init(APP_LED_GPIO, APP_LED_COUNT));
    ESP_ERROR_CHECK(effects_init(APP_LED_COUNT));

    build_segments();

    ESP_ERROR_CHECK(segment_init(gSegments, 3));

    srand((unsigned int)time(NULL));

    xTaskCreate(render_task, "render_task", 4096, NULL, 5, NULL);
}
