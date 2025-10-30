#ifndef LED_PIXEL_WALL_WIFI_PROVISIONING_H
#define LED_PIXEL_WALL_WIFI_PROVISIONING_H

#include "esp_err.h"
#include <stddef.h>

typedef enum {
    WIFI_PROVISIONING_STATUS_PORTAL,
    WIFI_PROVISIONING_STATUS_CONNECTING,
    WIFI_PROVISIONING_STATUS_CONNECTED,
    WIFI_PROVISIONING_STATUS_ERROR,
} wifi_provisioning_status_t;

typedef void (*wifi_provisioning_status_cb_t)(wifi_provisioning_status_t status,
                                              const char *message,
                                              void *user_ctx);

typedef struct {
    wifi_provisioning_status_cb_t status_cb;
    void *user_ctx;
} wifi_provisioning_config_t;

esp_err_t wifi_provisioning_start(const wifi_provisioning_config_t *config);

#endif
