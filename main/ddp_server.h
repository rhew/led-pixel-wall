#ifndef LED_PIXEL_WALL_DDP_SERVER_H
#define LED_PIXEL_WALL_DDP_SERVER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    uint16_t port;
    size_t led_count;
} ddp_server_config_t;

esp_err_t ddp_server_start(const ddp_server_config_t *config);
void ddp_server_stop(void);
bool ddp_server_is_running(void);

#endif // LED_PIXEL_WALL_DDP_SERVER_H
