#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "effects.h"
#include "effects_random_breathe.h"
#include "led_driver.h"

#define APP_LED_GPIO        3
#define APP_LED_COUNT       50
#define APP_FRAME_MS        50
#define APP_MAX_ACTIVE_LEDS 15
#define APP_FADE_IN_MS      600
#define APP_HOLD_MS         400
#define APP_FADE_OUT_MS     600
#define APP_MAX_BRIGHTNESS  0.5f

static void render_task(void *arg) {
    const TickType_t delay_ticks = pdMS_TO_TICKS(APP_FRAME_MS);
    (void)arg;
    static rgb_f frame[APP_LED_COUNT];

    while (true) {
        effects_step(APP_FRAME_MS);
        effects_random_breathe_tick(APP_FRAME_MS);
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

    effects_random_breathe_config_t cfg = {
        .led_count = APP_LED_COUNT,
        .max_active = APP_MAX_ACTIVE_LEDS,
        .fade_in_ms = APP_FADE_IN_MS,
        .hold_ms = APP_HOLD_MS,
        .fade_out_ms = APP_FADE_OUT_MS,
        .max_brightness = APP_MAX_BRIGHTNESS,
    };
    ESP_ERROR_CHECK(effects_random_breathe_init(&cfg));

    srand((unsigned int)time(NULL));

    xTaskCreate(render_task, "render_task", 4096, NULL, 5, NULL);
}
