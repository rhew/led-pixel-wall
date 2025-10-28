#ifndef LED_PIXEL_WALL_EFFECTS_H
#define LED_PIXEL_WALL_EFFECTS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    float r;
    float g;
    float b;
} rgb_f;

esp_err_t effects_init(size_t led_count);
void effects_deinit(void);
size_t effects_led_count(void);
void effects_step(uint32_t step_ms);
void effects_drive_to(size_t index, rgb_f target, uint32_t duration_ms);
bool effects_transition_active(size_t index);
rgb_f effects_current_color(size_t index);

#endif // LED_PIXEL_WALL_EFFECTS_H
