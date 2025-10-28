// wifi-test.c
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_netif.h"
#include "esp_http_server.h"

static const char *TAG = "prov";

/* ---------------- NVS helpers ---------------- */
static esp_err_t save_wifi_nvs(const char *ssid, const char *pass, bool force24) {
    nvs_handle_t h; esp_err_t err;
    if ((err = nvs_open("wifi", NVS_READWRITE, &h)) != ESP_OK) return err;
    if ((err = nvs_set_str(h, "ssid", ssid)) != ESP_OK) { nvs_close(h); return err; }
    if ((err = nvs_set_str(h, "pass", pass)) != ESP_OK) { nvs_close(h); return err; }
    uint8_t f = force24 ? 1 : 0;
    if ((err = nvs_set_u8(h, "force24", f)) != ESP_OK) { nvs_close(h); return err; }
    if ((err = nvs_commit(h)) != ESP_OK) { nvs_close(h); return err; }
    nvs_close(h); return ESP_OK;
}

static bool load_wifi_nvs(char *ssid, size_t ssid_len, char *pass, size_t pass_len, bool *force24) {
    nvs_handle_t h;
    if (nvs_open("wifi", NVS_READONLY, &h) != ESP_OK) return false;
    size_t a = ssid_len, b = pass_len;
    esp_err_t e1 = nvs_get_str(h, "ssid", ssid, &a);
    esp_err_t e2 = nvs_get_str(h, "pass", pass, &b);
    uint8_t f = 0; nvs_get_u8(h, "force24", &f); // default 0 if missing
    if (force24) *force24 = (f != 0);
    nvs_close(h);
    return (e1 == ESP_OK && e2 == ESP_OK);
}

/* ---------------- SoftAP ---------------- */
static void start_ap(void){
    esp_netif_create_default_wifi_ap();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t ap = { .ap = {
        .ssid="LedPixelWall-Setup", .channel=1, .password="12345678",
        .max_connection=4, .authmode=WIFI_AUTH_WPA_WPA2_PSK } };
    if (strlen((char*)ap.ap.password) < 8) ap.ap.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "SoftAP up http://192.168.4.1  SSID:%s", ap.ap.ssid);
}

/* ---------------- STA (with optional 2.4 lock) ---------------- */
static bool find_24g_bssid_after_start(const char *want_ssid, uint8_t out_bssid[6], uint8_t *out_chan){
    wifi_scan_config_t sc = { .ssid=(uint8_t*)want_ssid, .scan_type=WIFI_SCAN_TYPE_ACTIVE };
    ESP_ERROR_CHECK(esp_wifi_scan_start(&sc, true));
    uint16_t n=0; ESP_ERROR_CHECK(esp_wifi_scan_get_ap_num(&n));
    wifi_ap_record_t *aps = calloc(n?n:1, sizeof(*aps)); if(!aps) return false;
    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_records(&n, aps));
    int best=-127; bool ok=false;
    for (int i=0;i<n;i++){
        if (aps[i].primary <= 13 && strcmp((char*)aps[i].ssid, want_ssid)==0){
            if (aps[i].rssi > best){ best=aps[i].rssi; memcpy(out_bssid, aps[i].bssid, 6); *out_chan=aps[i].primary; ok=true; }
        }
    }
    free(aps); return ok;
}

static void on_wifi_disc(void *arg, esp_event_base_t b, int32_t id, void *data){
    wifi_event_sta_disconnected_t *e = data;
    ESP_LOGW(TAG, "DISCONNECTED reason=%d (retrying)", e->reason);
    esp_wifi_connect();
}
static void on_got_ip(void *arg, esp_event_base_t base, int32_t id, void *data){
    const ip_event_got_ip_t *e = (ip_event_got_ip_t*)data;
    ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&e->ip_info.ip));
}

static void start_sta(const char *ssid, const char *pass, bool force24){
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start()); // must start before scan

    wifi_config_t sta = {0};
    strncpy((char*)sta.sta.ssid, ssid, sizeof(sta.sta.ssid)-1);
    strncpy((char*)sta.sta.password, pass, sizeof(sta.sta.password)-1);
    sta.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    sta.sta.pmf_cfg.capable = true; sta.sta.pmf_cfg.required = false;
    sta.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    sta.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;

    if (force24) {
        uint8_t bssid[6]; uint8_t chan=0;
        if (find_24g_bssid_after_start(ssid, bssid, &chan)) {
            memcpy(sta.sta.bssid, bssid, 6);
            sta.sta.bssid_set = true;
            ESP_LOGI(TAG, "Force 2.4 GHz: BSSID %02x:%02x:%02x:%02x:%02x:%02x ch %u",
                     bssid[0],bssid[1],bssid[2],bssid[3],bssid[4],bssid[5], chan);
        } else {
            ESP_LOGW(TAG, "Force 2.4 enabled but no 2.4 AP found; connecting normally");
        }
    }

    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_connect());
    ESP_LOGI(TAG, "Connecting to SSID:\"%s\" (force24=%d) ...", ssid, (int)force24);
}

/* ---------------- HTTP server ---------------- */
static esp_err_t root_get(httpd_req_t *req) {
    // Read current flag to show checkbox state
    bool force24 = false;
    char dummy1[2]={0}, dummy2[2]={0};
    load_wifi_nvs(dummy1,sizeof(dummy1), dummy2,sizeof(dummy2), &force24); // ok if missing

    char page[1024];
    snprintf(page, sizeof(page),
        "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<body style='font-family:sans-serif;max-width:520px;margin:3rem auto'>"
        "<h2>LED Wall Wi-Fi Setup</h2>"
        "<form method=POST action=/prov enctype='application/x-www-form-urlencoded'>"
        "SSID<br><input name=ssid required style='width:100%%'><br><br>"
        "Password<br><input name=pass type=password style='width:100%%'><br><br>"
        "<label><input type=checkbox name=force24 value=on %s> Force 2.4&nbsp;GHz (lock to 2.4 BSSID)</label><br><br>"
        "<button type=submit>Save & Connect</button>"
        "</form></body>",
        force24 ? "checked" : ""
    );
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, page, HTTPD_RESP_USE_STRLEN);
}

/* tiny URL decoder (+ and %HH) */
static void urldecode(char *s){ char *o=s,*p=s; while(*p){ if(*p=='+'){*o++=' ';p++;} else if(*p=='%'&&p[1]&&p[2]){int v=0;sscanf(p+1,"%2x",&v);*o++=(char)v;p+=3;} else {*o++=*p++;}} *o=0; }

static esp_err_t prov_post(httpd_req_t *req){
    char buf[512]; int r = httpd_req_recv(req, buf, sizeof(buf)-1);
    if (r<=0){ httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "empty body"); return ESP_OK; }
    buf[r]=0;

    char ssid[33]={0}, pass[65]={0};
    bool force24=false;

    // crude parse
    char *a=strstr(buf,"ssid="), *b=strstr(buf,"pass="), *c=strstr(buf,"force24=on");
    if(!a){ httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "missing ssid"); return ESP_OK; }
    a+=5; char *amp=strchr(a,'&'); int alen=amp?(int)(amp-a):(int)strlen(a); if(alen>32) alen=32; strncpy(ssid,a,alen); ssid[alen]=0;
    if(b){ b+=5; int blen=(int)strlen(b); if(blen>64) blen=64; strncpy(pass,b,blen); pass[blen]=0; }
    if(c) force24 = true;

    urldecode(ssid); urldecode(pass);

    if (save_wifi_nvs(ssid, pass, force24) != ESP_OK){
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "nvs save failed");
        return ESP_OK;
    }

    httpd_resp_set_type(req, "text/html");
    httpd_resp_sendstr(req, "<h3>Saved. Connecting…</h3><p>You can close this page.</p>");

    ESP_LOGI(TAG, "Saved creds: SSID=\"%s\" force24=%d", ssid, (int)force24);

    ESP_ERROR_CHECK(esp_wifi_stop());    // stop AP instance
    ESP_ERROR_CHECK(esp_wifi_deinit());
    start_sta(ssid, pass, force24);
    return ESP_OK;
}

static esp_err_t prov_get(httpd_req_t *r){
    httpd_resp_set_status(r,"303 See Other");
    httpd_resp_set_hdr(r,"Location","/");
    return httpd_resp_sendstr(r,"");
}

static httpd_handle_t start_server(void){
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = 80;
    cfg.lru_purge_enable = true;
    httpd_handle_t hd=NULL;
    if (httpd_start(&hd, &cfg)==ESP_OK){
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/", .method=HTTP_GET, .handler=root_get });
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/prov", .method=HTTP_GET,  .handler=prov_get });
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/prov", .method=HTTP_POST, .handler=prov_post });
        // Captive helpers
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/generate_204", .method=HTTP_GET, .handler=root_get });
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/hotspot-detect.html", .method=HTTP_GET, .handler=root_get });
        httpd_register_uri_handler(hd, &(httpd_uri_t){ .uri="/ncsi.txt", .method=HTTP_GET, .handler=root_get });
    }
    ESP_LOGI(TAG, "HTTP server on http://192.168.4.1/");
    return hd;
}

/* ---------------- app ---------------- */
void app_main(void){
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,  IP_EVENT_STA_GOT_IP,         on_got_ip,  NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, on_wifi_disc,NULL, NULL));

    char ssid[33]={0}, pass[65]={0}; bool force24=false;
    if (load_wifi_nvs(ssid, sizeof(ssid), pass, sizeof(pass), &force24))
        start_sta(ssid, pass, force24);
    else { start_ap(); start_server(); }

    for(;;) vTaskDelay(pdMS_TO_TICKS(1000));
}

