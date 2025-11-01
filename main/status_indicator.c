#include "status_indicator.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "led_driver.h"

#define TAG "status_led"

typedef struct {
    status_indicator_mode_t mode;
    size_t led_index;
    uint8_t step;
    esp_timer_handle_t timer;
    bool timer_active;
} status_state_t;

static status_state_t s_state;

static void apply_color(uint8_t r, uint8_t g, uint8_t b) {
    esp_err_t err = led_driver_set_pixel(s_state.led_index, r, g, b);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set pixel: %s", esp_err_to_name(err));
    }
}

static void stop_timer(void) {
    if (s_state.timer && s_state.timer_active) {
        esp_timer_stop(s_state.timer);
        s_state.timer_active = false;
    }
}

static void start_timer(uint32_t period_ms) {
    if (!s_state.timer) {
        return;
    }
    stop_timer();
    esp_err_t err = esp_timer_start_periodic(s_state.timer, period_ms * 1000);
    if (err == ESP_OK) {
        s_state.timer_active = true;
    } else {
        ESP_LOGE(TAG, "Failed to start timer: %s", esp_err_to_name(err));
    }
}

static void status_timer_callback(void *arg) {
    (void)arg;
    switch (s_state.mode) {
    case STATUS_INDICATOR_MODE_PORTAL: {
        static const uint8_t kLevels[] = {10, 64, 150, 64};
        uint8_t idx = s_state.step % (sizeof(kLevels) / sizeof(kLevels[0]));
        uint8_t level = kLevels[idx];
        apply_color(0, 0, level);
        s_state.step = (s_state.step + 1) % (sizeof(kLevels) / sizeof(kLevels[0]));
        break;
    }
    case STATUS_INDICATOR_MODE_CONNECTING: {
        static const uint8_t kLevels[] = {0, 120, 0, 120};
        uint8_t idx = s_state.step % (sizeof(kLevels) / sizeof(kLevels[0]));
        uint8_t level = kLevels[idx];
        apply_color(0, 0, level);
        s_state.step = (s_state.step + 1) % (sizeof(kLevels) / sizeof(kLevels[0]));
        break;
    }
    case STATUS_INDICATOR_MODE_SUCCESS: {
        static const uint8_t kFrames[][3] = {
            {0, 120, 0},
            {0, 0, 0},
            {0, 120, 0},
            {0, 0, 0},
            {0, 180, 0},
            {0, 0, 0},
        };
        if (s_state.step < sizeof(kFrames) / sizeof(kFrames[0])) {
            const uint8_t *frame = kFrames[s_state.step];
            apply_color(frame[0], frame[1], frame[2]);
            s_state.step++;
            if (s_state.step >= sizeof(kFrames) / sizeof(kFrames[0])) {
                stop_timer();
                s_state.mode = STATUS_INDICATOR_MODE_OFF;
            }
        }
        break;
    }
    case STATUS_INDICATOR_MODE_ERROR: {
        static const uint8_t kFrames[][3] = {
            {220, 0, 0},
            {0, 0, 0},
            {220, 0, 0},
            {0, 0, 0},
            {0, 0, 0},
            {0, 0, 0},
        };
        uint8_t idx = s_state.step % (sizeof(kFrames) / sizeof(kFrames[0]));
        const uint8_t *frame = kFrames[idx];
        apply_color(frame[0], frame[1], frame[2]);
        s_state.step = (s_state.step + 1) % (sizeof(kFrames) / sizeof(kFrames[0]));
        break;
    }
    case STATUS_INDICATOR_MODE_OFF:
    default:
        apply_color(0, 0, 0);
        stop_timer();
        break;
    }
}

esp_err_t status_indicator_init(size_t led_index) {
    s_state = (status_state_t){
        .mode = STATUS_INDICATOR_MODE_OFF,
        .led_index = led_index,
        .step = 0,
        .timer = NULL,
        .timer_active = false,
    };

    const esp_timer_create_args_t args = {
        .callback = &status_timer_callback,
        .name = "status_led",
    };
    esp_err_t err = esp_timer_create(&args, &s_state.timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create status timer: %s", esp_err_to_name(err));
        return err;
    }
    apply_color(0, 0, 0);
    return ESP_OK;
}

void status_indicator_set_mode(status_indicator_mode_t mode) {
    if (s_state.mode == mode && mode != STATUS_INDICATOR_MODE_SUCCESS) {
        return;
    }
    stop_timer();
    s_state.mode = mode;
    s_state.step = 0;

    switch (mode) {
    case STATUS_INDICATOR_MODE_PORTAL:
        apply_color(0, 0, 16);
        start_timer(150);
        break;
    case STATUS_INDICATOR_MODE_CONNECTING:
        apply_color(0, 0, 120);
        start_timer(80);
        break;
    case STATUS_INDICATOR_MODE_SUCCESS:
        apply_color(0, 0, 0);
        start_timer(120);
        break;
    case STATUS_INDICATOR_MODE_ERROR:
        apply_color(64, 0, 0);
        start_timer(180);
        break;
    case STATUS_INDICATOR_MODE_OFF:
    default:
        apply_color(0, 0, 0);
        break;
    }
}

status_indicator_mode_t status_indicator_get_mode(void) {
    return s_state.mode;
}
