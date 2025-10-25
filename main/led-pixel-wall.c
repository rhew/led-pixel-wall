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
#define MAX_BRIGHTNESS     0.5
#define MAX_FADING_LEDS     15
#define DELAY_MS            50

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

// Structure for fading LEDs
typedef struct {
    int index;
    uint8_t r, g, b;
    float brightness;
    bool increasing;
} FadingLED;

FadingLED fading_leds[MAX_FADING_LEDS];
bool led_state[LED_COUNT] = {false};

// Initialize fading LEDs
void init_fading_leds() {
    for (int i = 0; i < MAX_FADING_LEDS; i++) {
        fading_leds[i].index = -1;
        fading_leds[i].brightness = 0;
        fading_leds[i].increasing = true;
    }
    for (int i = 0; i < LED_COUNT; i++) {
        led_state[i] = false;
    }
}

// Update fading effect
void update_fading_leds() {
    for (int i = 0; i < MAX_FADING_LEDS; i++) {
        if (fading_leds[i].index != -1) {
            if (fading_leds[i].increasing) {
                fading_leds[i].brightness += 0.1;
                if (fading_leds[i].brightness >= MAX_BRIGHTNESS) {
                    fading_leds[i].brightness = MAX_BRIGHTNESS;
                    fading_leds[i].increasing = false;
                }
            } else {
                fading_leds[i].brightness -= 0.1;
                if (fading_leds[i].brightness <= 0) {
                    fading_leds[i].brightness = 0;
                    led_state[fading_leds[i].index] = false;
                    fading_leds[i].index = -1;
                }
            }
            led_strip_set_pixel(led_strip, fading_leds[i].index,
                                fading_leds[i].r * fading_leds[i].brightness,
                                fading_leds[i].g * fading_leds[i].brightness,
                                fading_leds[i].b * fading_leds[i].brightness);
        }
    }
}

// Select a random LED to fade
void select_fading_led() {
    for (int i = 0; i < MAX_FADING_LEDS; i++) {
        if (fading_leds[i].index == -1) {
            int index;
            do {
                index = rand() % LED_COUNT;
            } while (led_state[index]);
            fading_leds[i].index = index;
            get_random_color(&fading_leds[i].r, &fading_leds[i].g, &fading_leds[i].b);
            fading_leds[i].brightness = 0;
            fading_leds[i].increasing = true;
            led_state[fading_leds[i].index] = true;
            break;
        }
    }
}

/**
 * @brief Main LED update task
 */
static void led_task(void *arg) {
    srand(time(NULL));  // Seed random number generator

    init_fading_leds();

    while (1) {
        select_fading_led();
        update_fading_leds();
        ESP_ERROR_CHECK(led_strip_refresh(led_strip));
        vTaskDelay(pdMS_TO_TICKS(DELAY_MS));
    }

}

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
