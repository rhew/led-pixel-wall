#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led_strip.h"
//#include "driver/gpio.h"
#include "esp_log.h"

#define LED_STRIP_GPIO      3       // GPIO for WS2811 data
#define LED_COUNT           50      // Number of LEDs
#define NUM_RANDOM_LEDS     10      // Number of LEDs to change per second
#define BRIGHTNESS          127     // 50% Brightness (0-255)

// 10 MHz clock = 0.1 µs per tick (since 1 / 10 MHz = 0.1 µs per tick).
// This allows fine-grained control over the 0.4 µs, 0.85 µs, and 1.25 µs
// pulse widths. Dividing 10 MHz into 800 kHz signal works cleanly using
// integer math. This value ensures precise waveform generation for WS2811
// without jitter.
#define RMT_RESOLUTION_HZ   10 * 1000 * 1000

static led_strip_handle_t led_strip;

/**
 * @brief Generate a random RGB color
 */
static void get_random_color(uint8_t *r, uint8_t *g, uint8_t *b) {
    *r = rand() % 256;
    *g = rand() % 256;
    *b = rand() % 256;
}

/**
 * @brief Main LED update task
 */
static void led_task(void *arg) {
    srand(time(NULL));  // Seed random number generator

    // Set all LEDs to white
    for (int i = 0; i < LED_COUNT; i++) {
        led_strip_set_pixel(led_strip, i, BRIGHTNESS, BRIGHTNESS, BRIGHTNESS);
    }
    led_strip_refresh(led_strip);

    while (1) {
        // Select and update 10 random LEDs
        for (int i = 0; i < NUM_RANDOM_LEDS; i++) {
            int index = rand() % LED_COUNT;
            uint8_t r, g, b;
            get_random_color(&r, &g, &b);
            led_strip_set_pixel(led_strip, index, r, g, b);
        }

        ESP_LOGI("LED", "Writing LED data...");
        ESP_ERROR_CHECK(led_strip_refresh(led_strip));
        ESP_LOGI("LED", "LED data written.");

        vTaskDelay(pdMS_TO_TICKS(1000)); // Wait 1 second
    }
}

// static void manual(void) {
//     gpio_reset_pin(GPIO_NUM_3);
//     gpio_set_direction(GPIO_NUM_3, GPIO_MODE_OUTPUT);
// 
//     while (1) {
//         gpio_set_level(GPIO_NUM_3, 1);
//         vTaskDelay(pdMS_TO_TICKS(500));
//         gpio_set_level(GPIO_NUM_3, 0);
//         vTaskDelay(pdMS_TO_TICKS(500));
//     }
// }

/**
 * @brief ESP32-S3 Main Function
 */
void app_main(void) {
    // manual();
    // LED Strip Configuration
    led_strip_config_t strip_config = {
        .strip_gpio_num = LED_STRIP_GPIO,
        .max_leds = LED_COUNT,
    };
    led_strip_rmt_config_t rmt_config = {
        .resolution_hz = RMT_RESOLUTION_HZ,
    };

    // Install LED strip driver
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &led_strip));

    // Start LED task
    xTaskCreate(led_task, "led_task", 4096, NULL, 5, NULL);
}
