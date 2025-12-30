#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "wifi_provisioning.h"

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "controller_config.h"

#define TAG "wifi_prov"

ESP_EVENT_DEFINE_BASE(WIFI_PROV_INTERNAL_EVENT);

#define WIFI_PROV_INTERNAL_EVENT_START_STA 1

#define WIFI_NAMESPACE "wifi"
#define WIFI_KEY_SSID   "ssid"
#define WIFI_KEY_PASS   "pass"
#define WIFI_KEY_FORCE  "force24"

#define WIFI_AP_SSID    "LED-Wall-Setup"
#define WIFI_AP_CHANNEL 1
#define WIFI_ERR_TIMEOUT_US (2000000)

#define MAX(a, b) ((a) > (b) ? (a) : (b))

typedef struct {
    bool has_creds;
    bool force_24g;
    char ssid[33];
    char pass[65];
    bool attempting_sta;
    bool sta_connected;
    esp_timer_handle_t error_timer;
    esp_timer_handle_t connect_timer;
    httpd_handle_t httpd;
    char portal_message[128];
    bool portal_message_valid;
} wifi_state_t;

static wifi_state_t s_state;
static esp_netif_t *s_ap_netif;
static esp_netif_t *s_sta_netif;
static bool s_wifi_initialized;
static const char *kDefaultPortalMessage = "Enter your Wi-Fi credentials.";
static wifi_provisioning_status_cb_t s_status_cb;
static void *s_status_ctx;
static controller_config_t s_controller_cfg;

static const char *status_name(wifi_provisioning_status_t status) {
    switch (status) {
    case WIFI_PROVISIONING_STATUS_PORTAL:
        return "portal";
    case WIFI_PROVISIONING_STATUS_CONNECTING:
        return "connecting";
    case WIFI_PROVISIONING_STATUS_CONNECTED:
        return "connected";
    case WIFI_PROVISIONING_STATUS_ERROR:
        return "error";
    default:
        return "unknown";
    }
}

static void notify_status(wifi_provisioning_status_t status, const char *message) {
    if (message && message[0] != '\0') {
        ESP_LOGI(TAG, "Status -> %s: %s", status_name(status), message);
    } else {
        ESP_LOGI(TAG, "Status -> %s", status_name(status));
    }
    if (s_status_cb) {
        s_status_cb(status, message, s_status_ctx);
    }
}

static esp_err_t start_softap(bool show_portal_status);
static esp_err_t start_station(void);
static void stop_http_server(void);
static esp_err_t start_http_server(void);
static void begin_error_feedback(void);
static void error_timer_callback(void *arg);
static void connect_timeout_callback(void *arg);
static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data);
static void ip_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data);
static void internal_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data);
static void wifi_load_credentials(void);
static esp_err_t wifi_save_credentials(const char *ssid, const char *pass, bool force24);
static bool lock_to_24g_bssid(const char *ssid, uint8_t out_bssid[6], uint8_t *out_channel);
static esp_err_t send_portal_page(httpd_req_t *req, const char *message);
static esp_err_t handle_root_get(httpd_req_t *req);
static esp_err_t handle_submit_post(httpd_req_t *req);
static esp_err_t handle_submit_get(httpd_req_t *req);
static esp_err_t handle_alias_get(httpd_req_t *req);
static void set_portal_message(const char *message);
static void wifi_clear_credentials(void);

static void url_decode(char *s) {
    char *src = s;
    char *dst = s;
    while (*src) {
        if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else if (*src == '%' && isxdigit((unsigned char)src[1]) && isxdigit((unsigned char)src[2])) {
            char hex[3] = {src[1], src[2], '\0'};
            *dst++ = (char)strtol(hex, NULL, 16);
            src += 3;
        } else {
            *dst++ = *src++;
        }
    }
    *dst = '\0';
}

static esp_err_t wifi_safe_stop(void) {
    esp_err_t err = esp_wifi_stop();
    if (err == ESP_ERR_WIFI_NOT_INIT || err == ESP_ERR_WIFI_NOT_STARTED) {
        return ESP_OK;
    }
    return err;
}

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
    if (base != WIFI_EVENT) {
        return;
    }

    switch (event_id) {
    case WIFI_EVENT_STA_START:
        ESP_LOGI(TAG, "STA start -> connecting");
        esp_wifi_connect();
        break;
    case WIFI_EVENT_STA_DISCONNECTED: {
        wifi_event_sta_disconnected_t *disc = (wifi_event_sta_disconnected_t *)data;
        ESP_LOGW(TAG, "STA disconnected (reason=%d)", disc ? disc->reason : -1);
        s_state.sta_connected = false;
        if (s_state.attempting_sta) {
            s_state.attempting_sta = false;
            set_portal_message("Connection failed. Check your SSID or password and try again.");
            wifi_clear_credentials();
            begin_error_feedback();
            start_softap(false);
        } else if (s_state.has_creds) {
            ESP_LOGI(TAG, "Reconnecting to Wi-Fi");
            notify_status(WIFI_PROVISIONING_STATUS_CONNECTING, NULL);
            esp_wifi_connect();
        }
        break;
    }
    default:
        break;
    }
}

static void ip_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
    if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGI(TAG, "Got IP");
        s_state.attempting_sta = false;
        s_state.sta_connected = true;
        stop_http_server();
        notify_status(WIFI_PROVISIONING_STATUS_CONNECTED, NULL);
        if (s_state.connect_timer) {
            esp_timer_stop(s_state.connect_timer);
        }
        s_state.portal_message_valid = false;
    }
}

static void wifi_load_credentials(void) {
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(WIFI_NAMESPACE, NVS_READONLY, &nvs);
    if (err != ESP_OK) {
        ESP_LOGI(TAG, "No stored credentials");
        s_state.has_creds = false;
        return;
    }

    size_t ssid_len = sizeof(s_state.ssid);
    size_t pass_len = sizeof(s_state.pass);
    err = nvs_get_str(nvs, WIFI_KEY_SSID, s_state.ssid, &ssid_len);
    if (err == ESP_OK) {
        err = nvs_get_str(nvs, WIFI_KEY_PASS, s_state.pass, &pass_len);
    }
    if (err == ESP_OK) {
        uint8_t force = 0;
        nvs_get_u8(nvs, WIFI_KEY_FORCE, &force);
        s_state.force_24g = (force != 0);
        s_state.has_creds = true;
        ESP_LOGI(TAG, "Loaded credentials for SSID '%s' (force24=%d)", s_state.ssid, s_state.force_24g);
        s_state.portal_message_valid = false;
    } else {
        s_state.has_creds = false;
        set_portal_message(kDefaultPortalMessage);
    }
    nvs_close(nvs);
}

static esp_err_t wifi_save_credentials(const char *ssid, const char *pass, bool force24) {
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(WIFI_NAMESPACE, NVS_READWRITE, &nvs);
    if (err != ESP_OK) {
        return err;
    }
    ESP_ERROR_CHECK(nvs_set_str(nvs, WIFI_KEY_SSID, ssid));
    ESP_ERROR_CHECK(nvs_set_str(nvs, WIFI_KEY_PASS, pass));
    ESP_ERROR_CHECK(nvs_set_u8(nvs, WIFI_KEY_FORCE, force24 ? 1 : 0));
    err = nvs_commit(nvs);
    nvs_close(nvs);
    if (err == ESP_OK) {
        strncpy(s_state.ssid, ssid, sizeof(s_state.ssid));
        strncpy(s_state.pass, pass, sizeof(s_state.pass));
        s_state.force_24g = force24;
        s_state.has_creds = true;
        s_state.portal_message_valid = false;
        ESP_LOGI(TAG, "Stored credentials for SSID '%s' (force24=%s)", s_state.ssid, s_state.force_24g ? "yes" : "no");
    }
    return err;
}

static esp_err_t start_softap(bool show_portal_status) {
    ESP_LOGI(TAG, "Starting SoftAP (show_portal_status=%s)", show_portal_status ? "yes" : "no");
    wifi_safe_stop();
    s_state.attempting_sta = false;
    if (s_state.connect_timer) {
        esp_timer_stop(s_state.connect_timer);
    }

    wifi_config_t ap_config = {0};
    strncpy((char *)ap_config.ap.ssid, WIFI_AP_SSID, sizeof(ap_config.ap.ssid));
    ap_config.ap.channel = WIFI_AP_CHANNEL;
    ap_config.ap.max_connection = 4;
    ap_config.ap.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    stop_http_server();
    start_http_server();

    if (show_portal_status) {
        if (!s_state.portal_message_valid) {
            set_portal_message(kDefaultPortalMessage);
        }
        const char *msg = s_state.portal_message_valid ? s_state.portal_message : kDefaultPortalMessage;
        notify_status(WIFI_PROVISIONING_STATUS_PORTAL, msg);
    }
    return ESP_OK;
}

static bool lock_to_24g_bssid(const char *ssid, uint8_t out_bssid[6], uint8_t *out_channel) {
    wifi_scan_config_t scan_cfg = {
        .ssid = (uint8_t *)ssid,
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
    };
    if (esp_wifi_scan_start(&scan_cfg, true) != ESP_OK) {
        return false;
    }

    uint16_t ap_count = 0;
    if (esp_wifi_scan_get_ap_num(&ap_count) != ESP_OK || ap_count == 0) {
        return false;
    }

    wifi_ap_record_t *records = calloc(ap_count, sizeof(wifi_ap_record_t));
    if (!records) {
        return false;
    }

    bool found = false;
    if (esp_wifi_scan_get_ap_records(&ap_count, records) == ESP_OK) {
        int best_rssi = -127;
        for (uint16_t i = 0; i < ap_count; ++i) {
            if (strcmp((const char *)records[i].ssid, ssid) == 0 && records[i].primary <= 13) {
                if (records[i].rssi > best_rssi) {
                    best_rssi = records[i].rssi;
                    memcpy(out_bssid, records[i].bssid, 6);
                    *out_channel = records[i].primary;
                    found = true;
                }
            }
        }
    }

    free(records);
    return found;
}

static esp_err_t start_station(void) {
    ESP_LOGI(TAG, "Starting STA for SSID '%s'", s_state.ssid);
    ESP_LOGI(TAG, "Force 2.4 GHz lock %s", s_state.force_24g ? "requested" : "not requested");
    s_state.attempting_sta = true;

    char msg[128];
    snprintf(msg, sizeof(msg), "Connecting to '%s'...", s_state.ssid);
    set_portal_message(msg);
    ESP_LOGI(TAG, "%s", msg);
    const char *status_msg = s_state.portal_message_valid ? s_state.portal_message : msg;
    notify_status(WIFI_PROVISIONING_STATUS_CONNECTING, status_msg);

    stop_http_server();
    ESP_LOGI(TAG, "HTTP server stopped; transitioning to station");
    wifi_safe_stop();
    ESP_LOGI(TAG, "Wi-Fi stopped; configuring station");

    wifi_config_t sta_cfg = {0};
    strncpy((char *)sta_cfg.sta.ssid, s_state.ssid, sizeof(sta_cfg.sta.ssid));
    strncpy((char *)sta_cfg.sta.password, s_state.pass, sizeof(sta_cfg.sta.password));
    sta_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    sta_cfg.sta.pmf_cfg.capable = true;
    sta_cfg.sta.pmf_cfg.required = false;
    sta_cfg.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    sta_cfg.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;

    if (s_state.force_24g) {
        uint8_t bssid[6];
        uint8_t channel = 0;
        if (lock_to_24g_bssid(s_state.ssid, bssid, &channel)) {
            memcpy(sta_cfg.sta.bssid, bssid, sizeof(bssid));
            sta_cfg.sta.bssid_set = true;
            sta_cfg.sta.channel = channel;
            ESP_LOGI(TAG, "Locking to 2.4 GHz BSSID %02x:%02x:%02x:%02x:%02x:%02x on channel %u",
                     bssid[0], bssid[1], bssid[2], bssid[3], bssid[4], bssid[5], channel);
        } else {
            ESP_LOGW(TAG, "2.4 GHz lock requested, but no matching AP found; continuing without lock");
        }
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "Station mode configured; waiting for WIFI_EVENT_STA_START");

    if (s_state.connect_timer) {
        esp_timer_stop(s_state.connect_timer);
        esp_timer_start_once(s_state.connect_timer, 15000000); // 15 seconds
    }

    return ESP_OK;
}

static void error_timer_callback(void *arg) {
    (void)arg;
    const char *msg = s_state.portal_message_valid ? s_state.portal_message : kDefaultPortalMessage;
    notify_status(WIFI_PROVISIONING_STATUS_PORTAL, msg);
}

static void connect_timeout_callback(void *arg) {
    (void)arg;
    if (!s_state.attempting_sta) {
        return;
    }
    ESP_LOGW(TAG, "Connection attempt timed out");
    s_state.attempting_sta = false;
    set_portal_message("Connection timed out. Check your network details and try again.");
    wifi_clear_credentials();
    begin_error_feedback();
    start_softap(false);
}

static void begin_error_feedback(void) {
    const char *msg = s_state.portal_message_valid ? s_state.portal_message : NULL;
    if (s_state.error_timer) {
        esp_timer_stop(s_state.error_timer);
        esp_timer_start_once(s_state.error_timer, WIFI_ERR_TIMEOUT_US);
    }
    if (s_state.connect_timer) {
        esp_timer_stop(s_state.connect_timer);
    }
    notify_status(WIFI_PROVISIONING_STATUS_ERROR, msg);
}

static esp_err_t send_portal_page(httpd_req_t *req, const char *message) {
    const char *msg = message ? message : "";
    const char *force_checked = s_state.force_24g ? " checked" : "";
    const char *html_fmt =
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>LED Wall Setup</title>"
        "<style>body{font-family:sans-serif;margin:2rem auto;max-width:30rem;line-height:1.5;}"
        "label{display:block;margin-top:1rem;}button{margin-top:1.5rem;padding:0.6rem 1.4rem;}"
        "input[type=text],input[type=password],input[type=number]{width:100%;padding:0.5rem;}"
        ".hint{font-size:0.9rem;color:#555;margin-top:0.5rem;}"
        "</style></head><body><h1>Network & Display</h1><p>%s</p><form method=\"post\" action=\"/submit\">"
        "<label>SSID<input name=\"ssid\" type=\"text\" required></label>"
        "<label>Password<input name=\"pass\" type=\"password\"></label>"
        "<label><input type=\"checkbox\" name=\"force\"%s> Force 2.4 GHz</label>"
        "<label>LED Count<input name=\"led_count\" type=\"number\" min=\"1\" max=\"4096\" value=\"%u\" required>"
        "<div class=\"hint\">Total RGB pixels connected to this controller.</div></label>"
        "<label>DDP Port<input name=\"ddp_port\" type=\"number\" min=\"1\" max=\"65535\" value=\"%u\" required>"
        "<div class=\"hint\">UDP port used by the DDP streamer (WLED defaults to 4048).</div></label>"
        "<button type=\"submit\">Save & Connect</button></form></body></html>";

    int needed = snprintf(NULL,
                          0,
                          html_fmt,
                          msg,
                          force_checked,
                          (unsigned int)s_controller_cfg.led_count,
                          (unsigned int)s_controller_cfg.ddp_port);
    if (needed < 0) {
        return httpd_resp_send_err(req,
                                   HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "Failed to render portal page");
    }

    size_t buffer_size = (size_t)needed + 1;
    char *buffer = malloc(buffer_size);
    if (!buffer) {
        return httpd_resp_send_err(req,
                                   HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "Out of memory");
    }

    int written = snprintf(buffer,
                           buffer_size,
                           html_fmt,
                           msg,
                           force_checked,
                           (unsigned int)s_controller_cfg.led_count,
                           (unsigned int)s_controller_cfg.ddp_port);
    if (written < 0 || (size_t)written >= buffer_size) {
        free(buffer);
        return httpd_resp_send_err(req,
                                   HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "Failed to render portal page");
    }
    httpd_resp_set_type(req, "text/html");
    esp_err_t resp = httpd_resp_send(req, buffer, HTTPD_RESP_USE_STRLEN);
    free(buffer);
    return resp;
}

static esp_err_t handle_root_get(httpd_req_t *req) {
    const char *msg = s_state.portal_message_valid ? s_state.portal_message : kDefaultPortalMessage;
    ESP_LOGI(TAG, "HTTP GET %s -> portal", req->uri);
    ESP_LOGD(TAG, "Portal message: %s", msg);
    return send_portal_page(req, msg);
}

static esp_err_t handle_submit_post(httpd_req_t *req) {
    ESP_LOGI(TAG, "HTTP POST %s", req->uri);
    char buf[512];
    int received = httpd_req_recv(req, buf, sizeof(buf) - 1);
    if (received <= 0) {
        ESP_LOGW(TAG, "POST body empty");
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Empty request");
    }
    buf[received] = '\0';

    char ssid[33] = {0};
    char pass[65] = {0};
    char led_count_str[8] = {0};
    char ddp_port_str[8] = {0};
    bool force24 = false;

    char *token = strtok(buf, "&");
    while (token) {
        char *value = strchr(token, '=');
        if (value) {
            *value++ = '\0';
            url_decode(value);
            if (strcmp(token, "ssid") == 0) {
                strncpy(ssid, value, sizeof(ssid) - 1);
            } else if (strcmp(token, "pass") == 0) {
                strncpy(pass, value, sizeof(pass) - 1);
            } else if (strcmp(token, "force") == 0) {
                force24 = true;
            } else if (strcmp(token, "led_count") == 0) {
                strncpy(led_count_str, value, sizeof(led_count_str) - 1);
            } else if (strcmp(token, "ddp_port") == 0) {
                strncpy(ddp_port_str, value, sizeof(ddp_port_str) - 1);
            }
        }
        token = strtok(NULL, "&");
    }

    if (ssid[0] == '\0') {
        ESP_LOGW(TAG, "POST missing SSID");
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "SSID is required");
    }

    char *endptr = NULL;
    long led_count = strtol(led_count_str, &endptr, 10);
    if (led_count < 1 || led_count > 4096 || endptr == led_count_str || (endptr && *endptr != '\0')) {
        ESP_LOGW(TAG, "Invalid LED count: %s", led_count_str);
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "LED count must be between 1 and 4096.");
    }

    endptr = NULL;
    long ddp_port = strtol(ddp_port_str, &endptr, 10);
    if (ddp_port < 1 || ddp_port > 65535 || endptr == ddp_port_str || (endptr && *endptr != '\0')) {
        ESP_LOGW(TAG, "Invalid DDP port: %s", ddp_port_str);
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "DDP port must be between 1 and 65535.");
    }

    ESP_LOGI(TAG, "Credentials received for SSID '%s' (force24=%s)", ssid, force24 ? "yes" : "no");

    controller_config_t new_cfg = {
        .led_count = (uint16_t)led_count,
        .ddp_port = (uint16_t)ddp_port,
        .has_values = true,
    };
    esp_err_t cfg_err = controller_config_save(&new_cfg);
    if (cfg_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save controller config: %s", esp_err_to_name(cfg_err));
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to store controller config");
    }
    s_controller_cfg = new_cfg;

    esp_err_t err = wifi_save_credentials(ssid, pass, force24);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save credentials: %s", esp_err_to_name(err));
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to store credentials");
    }

    char page[768];
    snprintf(page, sizeof(page),
             "<!doctype html><html><head><meta charset=\"utf-8\">"
             "<meta http-equiv=\"refresh\" content=\"5;url=/\">"
             "<title>Connecting...</title>"
             "<style>body{font-family:sans-serif;margin:2rem auto;max-width:28rem;line-height:1.4;}"
             "p{margin-top:1rem;}</style></head><body><h1>Connecting...</h1>"
             "<p>Attempting to join '<strong>%s</strong>'. Watch the status LEDs: sweeping blue means connecting, solid green means success, double red blink means retry.</p>"
             "<p>If you remain on this page, refresh after a few seconds to return to the portal.</p></body></html>",
             ssid);

    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, page, HTTPD_RESP_USE_STRLEN);

    ESP_LOGI(TAG, "Provisioning response sent; scheduling STA attempt");
    esp_err_t post_err = esp_event_post(WIFI_PROV_INTERNAL_EVENT,
                                        WIFI_PROV_INTERNAL_EVENT_START_STA,
                                        NULL,
                                        0,
                                        portMAX_DELAY);
    if (post_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to schedule STA start: %s", esp_err_to_name(post_err));
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to start connection");
    }
    ESP_LOGI(TAG, "STA start scheduled");
    return ESP_OK;
}

static esp_err_t handle_submit_get(httpd_req_t *req) {
    ESP_LOGI(TAG, "HTTP GET %s -> redirect to /", req->uri);
    httpd_resp_set_status(req, "303 See Other");
    httpd_resp_set_hdr(req, "Location", "/");
    return httpd_resp_send(req, NULL, 0);
}

static esp_err_t handle_alias_get(httpd_req_t *req) {
    ESP_LOGI(TAG, "HTTP GET alias %s -> portal", req->uri);
    return handle_root_get(req);
}

static esp_err_t start_http_server(void) {
    if (s_state.httpd) {
        return ESP_OK;
    }

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.lru_purge_enable = true;
    if (config.stack_size < 8192) {
        config.stack_size = 8192;
    }

    esp_err_t err = httpd_start(&s_state.httpd, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "HTTP server started on port %d", config.server_port);

    httpd_uri_t root_get = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = handle_root_get,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(s_state.httpd, &root_get);

    httpd_uri_t submit_post = {
        .uri = "/submit",
        .method = HTTP_POST,
        .handler = handle_submit_post,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(s_state.httpd, &submit_post);

    httpd_uri_t submit_get = {
        .uri = "/submit",
        .method = HTTP_GET,
        .handler = handle_submit_get,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(s_state.httpd, &submit_get);

    const httpd_uri_t portal_aliases[] = {
        {.uri = "/generate_204", .method = HTTP_GET, .handler = handle_alias_get, .user_ctx = NULL},
        {.uri = "/hotspot-detect.html", .method = HTTP_GET, .handler = handle_alias_get, .user_ctx = NULL},
        {.uri = "/ncsi.txt", .method = HTTP_GET, .handler = handle_alias_get, .user_ctx = NULL},
    };
    for (size_t i = 0; i < sizeof(portal_aliases) / sizeof(portal_aliases[0]); ++i) {
        httpd_register_uri_handler(s_state.httpd, &portal_aliases[i]);
    }

    return ESP_OK;
}

static void stop_http_server(void) {
    if (s_state.httpd) {
        ESP_LOGI(TAG, "Stopping HTTP server");
        httpd_stop(s_state.httpd);
        s_state.httpd = NULL;
    }
}

esp_err_t wifi_provisioning_start(const wifi_provisioning_config_t *config) {
    s_status_cb = config ? config->status_cb : NULL;
    s_status_ctx = config ? config->user_ctx : NULL;

    if (!s_wifi_initialized) {
        esp_err_t ret = nvs_flash_init();
        if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
            ESP_ERROR_CHECK(nvs_flash_erase());
            ESP_ERROR_CHECK(nvs_flash_init());
        }
        ESP_ERROR_CHECK(esp_netif_init());
        esp_err_t loop = esp_event_loop_create_default();
        if (loop != ESP_OK && loop != ESP_ERR_INVALID_STATE) {
            ESP_ERROR_CHECK(loop);
        }
        s_sta_netif = esp_netif_create_default_wifi_sta();
        s_ap_netif = esp_netif_create_default_wifi_ap();

        wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
        ESP_ERROR_CHECK(esp_wifi_init(&cfg));
        esp_event_handler_instance_t instance_any_id;
        esp_event_handler_instance_t instance_got_ip;
        esp_event_handler_instance_t instance_internal_start;
        ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL, &instance_any_id));
        ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, ip_event_handler, NULL, &instance_got_ip));
        ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_PROV_INTERNAL_EVENT,
                                                            WIFI_PROV_INTERNAL_EVENT_START_STA,
                                                            internal_event_handler,
                                                            NULL,
                                                            &instance_internal_start));

        const esp_timer_create_args_t timer_args = {
            .callback = &error_timer_callback,
            .name = "wifi_err",
        };
        ESP_ERROR_CHECK(esp_timer_create(&timer_args, &s_state.error_timer));

        const esp_timer_create_args_t connect_args = {
            .callback = &connect_timeout_callback,
            .name = "wifi_conn",
        };
        ESP_ERROR_CHECK(esp_timer_create(&connect_args, &s_state.connect_timer));

        s_wifi_initialized = true;
    }

    if (controller_config_load(&s_controller_cfg) == ESP_OK) {
        ESP_LOGI(TAG, "Controller config: led_count=%u, ddp_port=%u%s",
                 (unsigned int)s_controller_cfg.led_count,
                 (unsigned int)s_controller_cfg.ddp_port,
                 s_controller_cfg.has_values ? "" : " (defaults)");
    }

    wifi_load_credentials();

    if (s_state.has_creds) {
        ESP_LOGI(TAG, "Stored credentials present; starting STA connection");
        return start_station();
    }

    ESP_LOGI(TAG, "No stored credentials; starting provisioning portal");
    return start_softap(true);
}
static void set_portal_message(const char *message) {
    if (message && message[0] != '\0') {
        strncpy(s_state.portal_message, message, sizeof(s_state.portal_message) - 1);
        s_state.portal_message[sizeof(s_state.portal_message) - 1] = '\0';
        s_state.portal_message_valid = true;
        ESP_LOGI(TAG, "Portal message set to: %s", s_state.portal_message);
    } else {
        s_state.portal_message_valid = false;
        ESP_LOGI(TAG, "Portal message cleared");
    }
}

static void wifi_clear_credentials(void) {
    nvs_handle_t nvs;
    if (nvs_open(WIFI_NAMESPACE, NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_erase_key(nvs, WIFI_KEY_SSID);
        nvs_erase_key(nvs, WIFI_KEY_PASS);
        nvs_erase_key(nvs, WIFI_KEY_FORCE);
        nvs_commit(nvs);
        nvs_close(nvs);
    }
    memset(s_state.ssid, 0, sizeof(s_state.ssid));
    memset(s_state.pass, 0, sizeof(s_state.pass));
    s_state.force_24g = false;
    s_state.has_creds = false;
    ESP_LOGI(TAG, "Cleared stored Wi-Fi credentials");
}

static void internal_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
    (void)arg;
    (void)base;
    (void)data;
    if (event_id == WIFI_PROV_INTERNAL_EVENT_START_STA) {
        esp_err_t err = start_station();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "start_station failed: %s", esp_err_to_name(err));
        }
    }
}
