#include "ddp_server.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led_driver.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"

#define TAG "ddp_server"

#define DDP_HEADER_SIZE 10
#define RECV_TIMEOUT_MS 200
#define STREAM_IDLE_TIMEOUT_MS 3000
#define STATS_INTERVAL_MS 5000

typedef struct {
    ddp_server_config_t cfg;
    TaskHandle_t task;
    int sock;
    uint8_t *frame_buffer;
    uint8_t *rx_buffer;
    size_t frame_bytes;
    bool running;
    bool stop_requested;
    // sequence tracking
    bool seq_initialized;
    bool seq_tracking;
    uint8_t last_sequence;
    uint8_t expected_sequence;
    uint32_t drop_count;
    uint32_t duplicate_count;
    uint32_t processed_count;
    TickType_t last_frame_tick;
    TickType_t last_stats_tick;
    bool stream_active;
    char active_peer[48];
} ddp_state_t;

static ddp_state_t s_ddp;

static void reset_state(ddp_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->sock = -1;
}

static bool sequence_accept(ddp_state_t *state, uint8_t sequence) {
    if (!state->seq_initialized) {
        state->seq_initialized = true;
        state->seq_tracking = (sequence != 0);
        state->last_sequence = sequence;
        state->expected_sequence = (uint8_t)(sequence + 1);
        return true;
    }

    if (!state->seq_tracking) {
        if (sequence != state->last_sequence) {
            state->seq_tracking = true;
        }
        state->last_sequence = sequence;
        state->expected_sequence = (uint8_t)(sequence + 1);
        return true;
    }

    if (sequence == state->last_sequence) {
        state->duplicate_count++;
        return false;
    }

    if (sequence != state->expected_sequence) {
        state->drop_count++;
        state->last_sequence = sequence;
        state->expected_sequence = (uint8_t)(sequence + 1);
        return false;
    }

    state->last_sequence = sequence;
    state->expected_sequence = (uint8_t)(sequence + 1);
    return true;
}

static void log_stats_if_needed(ddp_state_t *state, TickType_t now_ticks) {
    TickType_t interval_ticks = pdMS_TO_TICKS(STATS_INTERVAL_MS);
    if (interval_ticks == 0) {
        interval_ticks = 1;
    }
    if ((now_ticks - state->last_stats_tick) < interval_ticks) {
        return;
    }
    state->last_stats_tick = now_ticks;
    if (state->processed_count == 0 && state->drop_count == 0 && state->duplicate_count == 0) {
        return;
    }
    ESP_LOGI(TAG,
             "Stats: processed=%" PRIu32 ", drops=%" PRIu32 ", duplicates=%" PRIu32 ", last_seq=%u",
             state->processed_count,
             state->drop_count,
             state->duplicate_count,
             state->last_sequence);
    state->drop_count = 0;
    state->duplicate_count = 0;
    state->processed_count = 0;
}

static void check_idle(ddp_state_t *state, TickType_t now_ticks) {
    if (!state->stream_active) {
        return;
    }
    TickType_t timeout_ticks = pdMS_TO_TICKS(STREAM_IDLE_TIMEOUT_MS);
    if (timeout_ticks == 0) {
        timeout_ticks = 1;
    }
    if ((now_ticks - state->last_frame_tick) >= timeout_ticks) {
        ESP_LOGI(TAG, "DDP stream idle");
        state->stream_active = false;
        state->active_peer[0] = '\0';
    }
}

static void ddp_task(void *ctx) {
    ddp_state_t *state = (ddp_state_t *)ctx;
    const size_t rx_capacity = DDP_HEADER_SIZE + state->frame_bytes;
    struct sockaddr_in source_addr = {0};
    socklen_t socklen = sizeof(source_addr);

    struct timeval tv = {
        .tv_sec = RECV_TIMEOUT_MS / 1000,
        .tv_usec = (RECV_TIMEOUT_MS % 1000) * 1000,
    };
    setsockopt(state->sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    ESP_LOGI(TAG, "DDP listener waiting on port %u", state->cfg.port);
    state->running = true;
    while (!state->stop_requested) {
        ssize_t received = recvfrom(state->sock,
                                    state->rx_buffer,
                                    rx_capacity,
                                    0,
                                    (struct sockaddr *)&source_addr,
                                    &socklen);
        TickType_t now_ticks = xTaskGetTickCount();
        if (received < 0) {
            if (errno == EWOULDBLOCK || errno == EAGAIN) {
                check_idle(state, now_ticks);
                log_stats_if_needed(state, now_ticks);
                continue;
            }
            ESP_LOGW(TAG, "recvfrom error: %d", errno);
            check_idle(state, now_ticks);
            log_stats_if_needed(state, now_ticks);
            continue;
        }

        if (received < DDP_HEADER_SIZE) {
            ESP_LOGW(TAG, "Packet too small (%d)", (int)received);
            continue;
        }

        const uint8_t *data = state->rx_buffer;
        uint8_t flags_version = data[0];
        uint8_t sequence = data[1];
        uint8_t data_type = data[2];
        uint16_t offset = (uint16_t)((data[3] << 8) | data[4]);
        uint16_t data_len = (uint16_t)((data[5] << 8) | data[6]);
        uint16_t data_id = (uint16_t)((data[7] << 8) | data[8]);
        (void)data_id; // currently unused

        uint8_t flags = (flags_version & 0xF0);
        uint8_t version = (flags_version & 0x0F);

        if (version != 0x1) {
            ESP_LOGW(TAG, "Unsupported version %u", version);
            continue;
        }
        if ((flags & 0x40) == 0 || (flags & (uint8_t)~0x40) != 0) {
            ESP_LOGW(TAG, "Unsupported flag combination 0x%02x", flags);
            continue;
        }
        if (data_type != 0x01) {
            ESP_LOGW(TAG, "Unsupported data type 0x%02x", data_type);
            continue;
        }
        if ((data_len % 3) != 0) {
            ESP_LOGW(TAG, "Non RGB-aligned payload (%u bytes)", data_len);
            continue;
        }
        if (offset + data_len > state->frame_bytes) {
            ESP_LOGW(TAG, "Payload out of range (offset=%u len=%u frame=%u)",
                     offset,
                     data_len,
                     (unsigned int)state->frame_bytes);
            continue;
        }

        if (!sequence_accept(state, sequence)) {
            continue;
        }

        memcpy(&state->frame_buffer[offset], &data[DDP_HEADER_SIZE], data_len);

        size_t led_count = data_len / 3;
        (void)led_count;
        led_driver_render_rgb(state->frame_buffer, state->cfg.led_count);
        state->processed_count++;
        state->last_frame_tick = now_ticks;

        if (!state->stream_active) {
            char addr_buf[32];
            inet_ntoa_r(source_addr.sin_addr, addr_buf, sizeof(addr_buf));
            snprintf(state->active_peer, sizeof(state->active_peer), "%s:%u", addr_buf, ntohs(source_addr.sin_port));
            ESP_LOGI(TAG, "DDP stream active from %s", state->active_peer);
            state->stream_active = true;
        }

        log_stats_if_needed(state, now_ticks);
    }

    ESP_LOGI(TAG, "DDP listener stopping");
    state->running = false;
    state->task = NULL;
    vTaskDelete(NULL);
}

esp_err_t ddp_server_start(const ddp_server_config_t *config) {
    if (!config || config->led_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_ddp.running) {
        return ESP_ERR_INVALID_STATE;
    }

    reset_state(&s_ddp);
    s_ddp.cfg = *config;
    s_ddp.frame_bytes = config->led_count * 3;
    s_ddp.frame_buffer = (uint8_t *)calloc(1, s_ddp.frame_bytes);
    if (!s_ddp.frame_buffer) {
        ESP_LOGE(TAG, "Failed to allocate frame buffer");
        reset_state(&s_ddp);
        return ESP_ERR_NO_MEM;
    }
    s_ddp.rx_buffer = (uint8_t *)malloc(DDP_HEADER_SIZE + s_ddp.frame_bytes);
    if (!s_ddp.rx_buffer) {
        ESP_LOGE(TAG, "Failed to allocate receive buffer");
        free(s_ddp.frame_buffer);
        reset_state(&s_ddp);
        return ESP_ERR_NO_MEM;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        free(s_ddp.rx_buffer);
        free(s_ddp.frame_buffer);
        reset_state(&s_ddp);
        return ESP_FAIL;
    }

    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in listen_addr = {
        .sin_family = AF_INET,
        .sin_port = htons(config->port),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };

    if (bind(sock, (struct sockaddr *)&listen_addr, sizeof(listen_addr)) < 0) {
        ESP_LOGE(TAG, "Socket bind failed: errno %d", errno);
        close(sock);
        free(s_ddp.rx_buffer);
        free(s_ddp.frame_buffer);
        reset_state(&s_ddp);
        return ESP_FAIL;
    }

    s_ddp.sock = sock;
    s_ddp.stop_requested = false;
    s_ddp.running = true;

    BaseType_t ok = xTaskCreate(ddp_task, "ddp_listener", 4096, &s_ddp, 5, &s_ddp.task);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to create DDP task");
        shutdown(sock, SHUT_RDWR);
        close(sock);
        free(s_ddp.rx_buffer);
        free(s_ddp.frame_buffer);
        reset_state(&s_ddp);
        return ESP_ERR_NO_MEM;
    }

    return ESP_OK;
}

void ddp_server_stop(void) {
    if (!s_ddp.running) {
        return;
    }
    s_ddp.stop_requested = true;
    if (s_ddp.sock >= 0) {
        shutdown(s_ddp.sock, SHUT_RDWR);
        close(s_ddp.sock);
        s_ddp.sock = -1;
    }
    while (s_ddp.task != NULL) {
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    free(s_ddp.rx_buffer);
    free(s_ddp.frame_buffer);
    reset_state(&s_ddp);
}

bool ddp_server_is_running(void) {
    return s_ddp.running;
}
