#ifndef LED_PIXEL_WALL_CONTROLLER_CONFIG_H
#define LED_PIXEL_WALL_CONTROLLER_CONFIG_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    uint16_t led_count;
    uint16_t ddp_port;
    bool has_values;
} controller_config_t;

void controller_config_get_defaults(controller_config_t *out);
esp_err_t controller_config_load(controller_config_t *out);
esp_err_t controller_config_save(const controller_config_t *cfg);

#endif // LED_PIXEL_WALL_CONTROLLER_CONFIG_H
