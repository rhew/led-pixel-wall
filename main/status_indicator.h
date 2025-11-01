#ifndef LED_PIXEL_WALL_STATUS_INDICATOR_H
#define LED_PIXEL_WALL_STATUS_INDICATOR_H

#include <stddef.h>
#include "esp_err.h"

typedef enum {
    STATUS_INDICATOR_MODE_OFF = 0,
    STATUS_INDICATOR_MODE_PORTAL,
    STATUS_INDICATOR_MODE_CONNECTING,
    STATUS_INDICATOR_MODE_SUCCESS,
    STATUS_INDICATOR_MODE_ERROR,
} status_indicator_mode_t;

esp_err_t status_indicator_init(size_t led_index);
void status_indicator_set_mode(status_indicator_mode_t mode);
status_indicator_mode_t status_indicator_get_mode(void);

#endif // LED_PIXEL_WALL_STATUS_INDICATOR_H
