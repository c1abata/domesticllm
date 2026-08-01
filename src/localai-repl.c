#include <curl/curl.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>

#include "linenoise.h"
#include "sds.h"

#define DEFAULT_BASE_URL "http://127.0.0.1:8083/v1"
#define HISTORY_FILE ".localai_history"
#define MAX_BASE_URL_LEN 2048
#define MAX_API_KEY_LEN 4096
#define MAX_MODEL_LEN 256
#define MAX_RESPONSE_LEN (16 * 1024 * 1024)

static sds json_escape(const char *p) {
    static const char hex[] = "0123456789abcdef";
    sds out = sdsempty();

    while (*p) {
        unsigned char c = (unsigned char)*p;
        switch (c) {
        case '\\': out = sdscat(out, "\\\\"); break;
        case '"': out = sdscat(out, "\\\""); break;
        case '\n': out = sdscat(out, "\\n"); break;
        case '\r': out = sdscat(out, "\\r"); break;
        case '\t': out = sdscat(out, "\\t"); break;
        default:
            if (c < 0x20) {
                char escaped[6] = {'\\', 'u', '0', '0', hex[c >> 4], hex[c & 0xf]};
                out = sdscatlen(out, escaped, sizeof(escaped));
            } else {
                out = sdscatlen(out, p, 1);
            }
            break;
        }
        p++;
    }
    return out;
}

static int has_unsafe_bytes(const char *value, size_t maxlen) {
    size_t len;

    if (value == NULL || value[0] == '\0') return 1;
    len = strlen(value);
    if (len > maxlen) return 1;
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)value[i];
        if (c <= 0x20 || c == 0x7f) return 1;
    }
    return 0;
}

static int valid_base_url(const char *base) {
    CURLU *url;
    CURLUcode rc;
    char *scheme = NULL;
    char *host = NULL;
    char *part = NULL;
    int valid = 0;

    if (has_unsafe_bytes(base, MAX_BASE_URL_LEN)) return 0;
    url = curl_url();
    if (url == NULL) return 0;
    if (curl_url_set(url, CURLUPART_URL, base, 0) != CURLUE_OK) goto done;
    if (curl_url_get(url, CURLUPART_SCHEME, &scheme, 0) != CURLUE_OK) goto done;
    if (strcasecmp(scheme, "http") != 0 && strcasecmp(scheme, "https") != 0)
        goto done;
    if (curl_url_get(url, CURLUPART_HOST, &host, 0) != CURLUE_OK || host[0] == '\0')
        goto done;

    rc = curl_url_get(url, CURLUPART_USER, &part, 0);
    if (rc == CURLUE_OK) goto done;
    rc = curl_url_get(url, CURLUPART_PASSWORD, &part, 0);
    if (rc == CURLUE_OK) goto done;
    rc = curl_url_get(url, CURLUPART_QUERY, &part, 0);
    if (rc == CURLUE_OK) goto done;
    rc = curl_url_get(url, CURLUPART_FRAGMENT, &part, 0);
    if (rc == CURLUE_OK) goto done;
    valid = 1;

done:
    curl_free(part);
    curl_free(host);
    curl_free(scheme);
    curl_url_cleanup(url);
    return valid;
}

static int valid_api_key(const char *key) {
    if (has_unsafe_bytes(key, MAX_API_KEY_LEN)) return 0;
    return strcmp(key, "CHANGE_ME") != 0 &&
           strcmp(key, "CHANGE_ME_LONG_RANDOM_KEY") != 0;
}

static size_t collect_response(char *data, size_t size, size_t nmemb,
                               void *userdata) {
    sds *response = userdata;
    size_t len;

    if (nmemb != 0 && size > (size_t)-1 / nmemb) return 0;
    len = size * nmemb;
    if (len > MAX_RESPONSE_LEN - sdslen(*response)) return 0;
    *response = sdscatlen(*response, data, len);
    return len;
}

static const char *json_string_value(const char *json, const char *field) {
    const char *p = json;
    size_t field_len = strlen(field);

    while ((p = strstr(p, field)) != NULL) {
        const char *value = p + field_len;
        while (isspace((unsigned char)*value)) value++;
        if (*value++ != ':') {
            p += field_len;
            continue;
        }
        while (isspace((unsigned char)*value)) value++;
        if (*value == '"') return value + 1;
        p += field_len;
    }
    return NULL;
}

static int print_json_string(const char *value) {
    const char *p = value;

    if (p == NULL) return 0;
    while (*p && *p != '"') {
        if (*p != '\\') {
            putchar((unsigned char)*p++);
            continue;
        }
        p++;
        if (*p == '\0') return 0;
        switch (*p) {
        case '"': putchar('"'); break;
        case '\\': putchar('\\'); break;
        case '/': putchar('/'); break;
        case 'b': putchar('\b'); break;
        case 'f': putchar('\f'); break;
        case 'n': putchar('\n'); break;
        case 'r': putchar('\r'); break;
        case 't': putchar('\t'); break;
        default:
            putchar('\\');
            putchar((unsigned char)*p);
            break;
        }
        p++;
    }
    if (*p != '"') return 0;
    putchar('\n');
    return 1;
}

static void print_response(const sds response) {
    const char *value = json_string_value(response, "\"content\"");

    if (print_json_string(value)) return;
    value = json_string_value(response, "\"message\"");
    if (print_json_string(value)) return;
    fwrite(response, 1, sdslen(response), stdout);
    if (sdslen(response) == 0 || response[sdslen(response) - 1] != '\n')
        putchar('\n');
}

static void wipe_and_free(sds value) {
    volatile unsigned char *p;
    size_t len;

    if (value == NULL) return;
    p = (volatile unsigned char *)value;
    len = sdslen(value);
    while (len--) *p++ = 0;
    sdsfree(value);
}

static int request_completion(const char *base, const char *key,
                              const sds payload) {
    CURL *curl = NULL;
    CURLcode rc;
    struct curl_slist *headers = NULL;
    struct curl_slist *next;
    sds endpoint = sdsnew(base);
    sds authorization = NULL;
    sds response = sdsempty();
    long status = 0;
    int result = 1;

    while (sdslen(endpoint) > 0 && endpoint[sdslen(endpoint) - 1] == '/')
        sdsrange(endpoint, 0, -2);
    endpoint = sdscat(endpoint, "/chat/completions");
    authorization = sdscatprintf(sdsempty(), "Authorization: Bearer %s", key);

    curl = curl_easy_init();
    if (curl == NULL) {
        fputs("request failed: unable to initialize HTTP transport\n", stderr);
        goto done;
    }
    next = curl_slist_append(headers, "Content-Type: application/json");
    if (next == NULL) goto allocation_error;
    headers = next;
    next = curl_slist_append(headers, authorization);
    if (next == NULL) goto allocation_error;
    headers = next;

    if (curl_easy_setopt(curl, CURLOPT_URL, endpoint) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_POST, 1L) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE,
                         (curl_off_t)sdslen(payload)) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, collect_response) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 15L) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 1800L) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L) != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_PROXY, "") != CURLE_OK ||
        curl_easy_setopt(curl, CURLOPT_USERAGENT, "localai-repl/1") != CURLE_OK) {
        fputs("request failed: unable to configure HTTP transport\n", stderr);
        goto done;
    }

    rc = curl_easy_perform(curl);
    if (rc != CURLE_OK) {
        fprintf(stderr, "request failed: %s\n", curl_easy_strerror(rc));
        goto done;
    }
    if (curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status) != CURLE_OK) {
        fputs("request failed: missing HTTP status\n", stderr);
        goto done;
    }
    if (status < 200 || status >= 300)
        fprintf(stderr, "server returned HTTP %ld\n", status);
    print_response(response);
    result = (status >= 200 && status < 300) ? 0 : 1;
    goto done;

allocation_error:
    fputs("request failed: out of memory\n", stderr);

done:
    curl_slist_free_all(headers);
    if (curl != NULL) curl_easy_cleanup(curl);
    wipe_and_free(authorization);
    sdsfree(response);
    sdsfree(endpoint);
    return result;
}

int main(void) {
    const char *base = getenv("LOCAL_AI_BASE_URL");
    const char *key = getenv("LOCAL_AI_API_KEY");
    const char *model = getenv("LOCAL_AI_REQUEST_MODEL");
    sds escaped_model;
    char *line;

    if (base == NULL || base[0] == '\0') base = DEFAULT_BASE_URL;
    if (model == NULL || model[0] == '\0') model = "ds4flash";
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        fputs("fatal: unable to initialize HTTP transport\n", stderr);
        return 1;
    }
    if (!valid_base_url(base)) {
        fputs("fatal: invalid LOCAL_AI_BASE_URL (http/https without credentials, query or fragment required)\n",
              stderr);
        curl_global_cleanup();
        return 2;
    }
    if (!valid_api_key(key)) {
        fputs("fatal: missing or invalid LOCAL_AI_API_KEY\n", stderr);
        curl_global_cleanup();
        return 2;
    }
    if (has_unsafe_bytes(model, MAX_MODEL_LEN)) {
        fputs("fatal: invalid LOCAL_AI_REQUEST_MODEL\n", stderr);
        curl_global_cleanup();
        return 2;
    }

    umask(0077);
    escaped_model = json_escape(model);
    linenoiseHistoryLoad(HISTORY_FILE);
    printf("localai-repl. /quit to exit. endpoint=%s\n", base);

    while ((line = linenoise("ai> ")) != NULL) {
        sds escaped;
        sds payload;

        if (!strcmp(line, "/quit") || !strcmp(line, "/exit")) {
            free(line);
            break;
        }
        if (line[0] == '\0') {
            free(line);
            continue;
        }
        linenoiseHistoryAdd(line);
        if (linenoiseHistorySave(HISTORY_FILE) == 0)
            chmod(HISTORY_FILE, S_IRUSR | S_IWUSR);
        else
            fputs("warning: unable to save protected history\n", stderr);

        escaped = json_escape(line);
        payload = sdscatprintf(sdsempty(),
            "{\"model\":\"%s\",\"messages\":[{\"role\":\"user\",\"content\":\"%s\"}],\"temperature\":0.15,\"max_tokens\":512}",
            escaped_model, escaped);
        request_completion(base, key, payload);
        sdsfree(escaped);
        sdsfree(payload);
        free(line);
    }
    sdsfree(escaped_model);
    curl_global_cleanup();
    return 0;
}
