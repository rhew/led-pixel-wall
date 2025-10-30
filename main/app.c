#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "effects.h"
#include "effects_cylon.h"
#include "effects_pattern.h"
#include "effects_random_breathe.h"
#include "effects_static_on.h"
#include "led_driver.h"
#include "segment.h"
#include "wifi_provisioning.h"
#include "esp_log.h"

#define APP_LED_GPIO        3
#define APP_LED_COUNT       50
#define APP_FRAME_MS        50
#define APP_MAX_ACTIVE_LEDS 8
#define APP_FADE_IN_MS      600
#define APP_HOLD_MS         400
#define APP_FADE_OUT_MS     600
#define APP_MAX_BRIGHTNESS  0.5f
#define APP_STATUS_LED_COUNT 5
#define APP_STATUS_START_INDEX 0
#define APP_CYLON_SEGMENT_COUNT 10
#define APP_CYLON_START_INDEX 20

#define APP_RANDOM_SEGMENT_COUNT (APP_LED_COUNT - APP_STATUS_LED_COUNT - APP_CYLON_SEGMENT_COUNT)

static const char *TAG = "app";

#define STATUS_SEGMENT_NAME  "status"
#define CYLON_SEGMENT_NAME   "accent-cylon"
#define AMBIENT_SEGMENT_NAME "ambient"

static const uint16_t kStatusIndices[APP_STATUS_LED_COUNT] = {
    APP_STATUS_START_INDEX + 0,
    APP_STATUS_START_INDEX + 1,
    APP_STATUS_START_INDEX + 2,
    APP_STATUS_START_INDEX + 3,
    APP_STATUS_START_INDEX + 4,
};

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

static uint16_t gRandomIndices[APP_RANDOM_SEGMENT_COUNT];
static segment_desc_t gSegments[3];
static const effects_random_breathe_params_t kRandomParams = {
    .max_active = APP_MAX_ACTIVE_LEDS,
    .fade_in_ms = APP_FADE_IN_MS,
    .hold_ms = APP_HOLD_MS,
    .fade_out_ms = APP_FADE_OUT_MS,
    .max_brightness = APP_MAX_BRIGHTNESS,
};

static const effects_cylon_params_t kAccentCylonParams = {
    .fade_ms = 450,
    .dwell_ms = 120,
    .color = {.r = 1.0f, .g = 0.0f, .b = 0.0f},
};

static const effects_cylon_params_t kStatusConnectingParams = {
    .fade_ms = 120,
    .dwell_ms = 150,
    .color = {.r = 0.0f, .g = 0.0f, .b = 1.0f},
};

static const rgb_f kStatusPortalColors[] = {
    {.r = 0.0f, .g = 0.0f, .b = 1.0f},
    {.r = 0.0f, .g = 0.0f, .b = 0.0f},
};

static const uint32_t kStatusPortalDurations[] = {600, 600};

static const effects_pattern_params_t kStatusPortalPattern = {
    .colors = kStatusPortalColors,
    .durations_ms = kStatusPortalDurations,
    .step_count = 2,
    .fade_ms = 600,
};

static const rgb_f kStatusErrorColors[] = {
    {.r = 1.0f, .g = 0.0f, .b = 0.0f},
    {.r = 0.0f, .g = 0.0f, .b = 0.0f},
    {.r = 1.0f, .g = 0.0f, .b = 0.0f},
    {.r = 0.0f, .g = 0.0f, .b = 0.0f},
};

static const uint32_t kStatusErrorDurations[] = {180, 180, 180, 700};

static const effects_pattern_params_t kStatusErrorPattern = {
    .colors = kStatusErrorColors,
    .durations_ms = kStatusErrorDurations,
    .step_count = 4,
    .fade_ms = 0,
};

static const effects_static_on_params_t kStatusConnectedParams = {
    .color = {.r = 0.0f, .g = 1.0f, .b = 0.0f},
    .fade_ms = 300,
};

static void build_segments(void) {
    size_t out = 0;
    for (uint16_t i = 0; i < APP_LED_COUNT; ++i) {
        bool is_reserved = false;
        if (i < APP_STATUS_LED_COUNT) {
            is_reserved = true;
        } else if (i >= APP_CYLON_START_INDEX &&
                   i < APP_CYLON_START_INDEX + APP_CYLON_SEGMENT_COUNT) {
            is_reserved = true;
        }
        if (is_reserved) {
            continue;
        }
        if (out < APP_RANDOM_SEGMENT_COUNT) {
            gRandomIndices[out++] = i;
        }
    }
    assert(out == APP_RANDOM_SEGMENT_COUNT);

    gSegments[0] = (segment_desc_t){
        .name = STATUS_SEGMENT_NAME,
        .indices = kStatusIndices,
        .count = APP_STATUS_LED_COUNT,
        .effect_id = SEGMENT_EFFECT_PATTERN,
        .effect_params = &kStatusPortalPattern,
    };
    gSegments[1] = (segment_desc_t){
        .name = CYLON_SEGMENT_NAME,
        .indices = kCylonIndices,
        .count = APP_CYLON_SEGMENT_COUNT,
        .effect_id = SEGMENT_EFFECT_CYLON,
        .effect_params = &kAccentCylonParams,
    };
    gSegments[2] = (segment_desc_t){
        .name = AMBIENT_SEGMENT_NAME,
        .indices = gRandomIndices,
        .count = APP_RANDOM_SEGMENT_COUNT,
        .effect_id = SEGMENT_EFFECT_RANDOM_BREATHE,
        .effect_params = &kRandomParams,
    };
}

static void handle_provisioning_status(wifi_provisioning_status_t status,
                                       const char *message,
                                       void *user_ctx) {
    (void)message;
    (void)user_ctx;

    const void *params = NULL;
    segment_effect_id_t effect = SEGMENT_EFFECT_PATTERN;

    switch (status) {
    case WIFI_PROVISIONING_STATUS_PORTAL:
        effect = SEGMENT_EFFECT_PATTERN;
        params = &kStatusPortalPattern;
        break;
    case WIFI_PROVISIONING_STATUS_CONNECTING:
        effect = SEGMENT_EFFECT_CYLON;
        params = &kStatusConnectingParams;
        break;
    case WIFI_PROVISIONING_STATUS_CONNECTED:
        effect = SEGMENT_EFFECT_STATIC_ON;
        params = &kStatusConnectedParams;
        break;
    case WIFI_PROVISIONING_STATUS_ERROR:
        effect = SEGMENT_EFFECT_PATTERN;
        params = &kStatusErrorPattern;
        break;
    default:
        return;
    }

    esp_err_t err = segment_set_effect(STATUS_SEGMENT_NAME, effect, params);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to update status segment (%d): %s",
                 (int)effect, esp_err_to_name(err));
    }
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

    const wifi_provisioning_config_t wifi_cfg = {
        .status_cb = handle_provisioning_status,
        .user_ctx = NULL,
    };
    ESP_ERROR_CHECK(wifi_provisioning_start(&wifi_cfg));

    srand((unsigned int)time(NULL));

    xTaskCreate(render_task, "render_task", 4096, NULL, 5, NULL);
}
