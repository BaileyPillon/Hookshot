/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "devtools.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
_Static_assert(sizeof(float) == sizeof(uint32_t), "developer wire format requires binary32 floats");
_Static_assert(FLT_RADIX == 2 && FLT_MANT_DIG == 24 && FLT_MAX_EXP == 128,
               "developer wire format requires IEEE-754 binary32 floats");

static int enabled, dispatching, have_sample;
static size_t observer_count;
static uint64_t sequence, next_emit;
static HosDevSampleV1 latest;
static HosDevEmitFn emitter;
static void *emitter_user;
static struct { char id[64]; void *user; HosDevSampleFn fn; } observers[HOS_DEV_MAX_OBSERVERS];

int hos_dev_init(int on, HosDevEmitFn emit, void *user) {
    if (dispatching) return HOS_DEV_BUSY;
    enabled = on == 1;
    have_sample = 0;
    observer_count = 0;
    sequence = next_emit = 0;
    memset(&latest, 0, sizeof latest);
    memset(observers, 0, sizeof observers);
    emitter = emit;
    emitter_user = user;
    return HOS_DEV_OK;
}
int hos_dev_enabled(void) { return enabled; }
uint32_t hos_dev_capabilities(void) { return enabled ? HOS_DEV_CAP_PLAYER_SAMPLE : 0; }

static int valid_text(const char *s, size_t cap) {
    const unsigned char *p = (const unsigned char *)s;
    const unsigned char *end = (const unsigned char *)memchr(s, 0, cap);
    if (!end) return 0;
    while (p < end) {
        uint32_t cp = *p++;
        if (cp < 128) continue;
        int n;
        uint32_t minimum;
        if (cp >= 0xc2 && cp <= 0xdf) n = 1, cp &= 31, minimum = 0x80;
        else if (cp >= 0xe0 && cp <= 0xef) n = 2, cp &= 15, minimum = 0x800;
        else if (cp >= 0xf0 && cp <= 0xf4) n = 3, cp &= 7, minimum = 0x10000;
        else return 0;
        if (end - p < n) return 0;
        while (n--) { if ((*p & 0xc0) != 0x80) return 0; cp = (cp << 6) | (*p++ & 63); }
        if (cp < minimum || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return 0;
    }
    return 1;
}
static int sample_valid(const HosDevSampleV1 *s) {
    return s && s->struct_size >= sizeof *s && s->abi_version == HOS_DEV_ABI_V1 &&
        valid_text(s->game_build_id, sizeof s->game_build_id) &&
        valid_text(s->runtime_build, sizeof s->runtime_build) && valid_text(s->scene, sizeof s->scene) &&
        isfinite(s->position[0]) && isfinite(s->position[1]) && isfinite(s->position[2]);
}
int hos_dev_register_observer(const HosDevObserverV1 *o) {
    if (!enabled) return HOS_DEV_DISABLED;
    if (dispatching) return HOS_DEV_BUSY;
    if (!o || o->struct_size < sizeof *o) return HOS_DEV_INVALID;
    if (o->abi_version != HOS_DEV_ABI_V1 || (o->required_capabilities & ~HOS_DEV_CAP_PLAYER_SAMPLE))
        return HOS_DEV_ABI_MISMATCH;
    if (!o->id || !o->on_player_sample || o->id[0] < 'a' || o->id[0] > 'z') return HOS_DEV_INVALID;
    size_t n = 0;
    while (n < 64 && o->id[n]) {
        const char c = o->id[n++];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.'))
            return HOS_DEV_INVALID;
    }
    if (!n || n == 64) return HOS_DEV_INVALID;
    for (size_t i = 0; i < observer_count; i++)
        if (!strcmp(observers[i].id, o->id)) return HOS_DEV_DUPLICATE;
    if (observer_count == HOS_DEV_MAX_OBSERVERS) return HOS_DEV_CAPACITY;
    memcpy(observers[observer_count].id, o->id, n + 1);
    observers[observer_count].user = o->user;
    observers[observer_count++].fn = o->on_player_sample;
    return HOS_DEV_OK;
}
int hos_dev_read_sample(HosDevSampleV1 *out) {
    if (!enabled) return HOS_DEV_DISABLED;
    if (!out || out->struct_size < sizeof *out) return HOS_DEV_INVALID;
    if (out->abi_version != HOS_DEV_ABI_V1) return HOS_DEV_ABI_MISMATCH;
    if (!have_sample) return HOS_DEV_NO_SAMPLE;
    *out = latest;
    return HOS_DEV_OK;
}

/* Append a JSON string without allocating; never publish a partial JSON record. */
static int json_string(char *out, size_t cap, size_t *used, const char *s) {
    if (*used + 2 >= cap) return 0;
    out[(*used)++] = '"';
    for (; *s; s++) {
        const unsigned char c = (unsigned char)*s;
        if (c < 32) {
            if (*used + 6 >= cap) return 0;
            snprintf(out + *used, cap - *used, "\\u%04x", c);
            *used += 6;
        } else {
            if (*used + 2 >= cap) return 0;
            if (c == '"' || c == '\\') out[(*used)++] = '\\';
            out[(*used)++] = (char)c;
        }
    }
    out[(*used)++] = '"';
    out[*used] = 0;
    return 1;
}
int hos_dev_sample_json(const HosDevSampleV1 *s, char *out, size_t cap) {
    if (!out || !cap) return HOS_DEV_INVALID;
    out[0] = 0;
    if (!sample_valid(s)) return HOS_DEV_INVALID;
    uint32_t bits[3];
    memcpy(bits, s->position, sizeof bits);
    int n = snprintf(out, cap,
        "{\"schema\":1,\"kind\":\"player-observation\",\"sequence\":%llu,\"monotonic_ns\":%llu,"
        "\"program_id\":\"%016llx\",\"position_bits\":[%u,%u,%u],\"game_build_id\":",
        (unsigned long long)s->sequence, (unsigned long long)s->monotonic_ns,
        (unsigned long long)s->program_id, bits[0], bits[1], bits[2]);
    size_t used = n > 0 ? (size_t)n : cap;
    const char *names[] = {",\"runtime_build\":", ",\"scene\":"};
    const char *values[] = {s->game_build_id, s->runtime_build, s->scene};
    if (used >= cap || !json_string(out, cap, &used, values[0])) goto overflow;
    for (int i = 0; i < 2; i++) {
        const size_t k = strlen(names[i]);
        if (used + k >= cap) goto overflow;
        memcpy(out + used, names[i], k + 1);
        used += k;
        if (!json_string(out, cap, &used, values[i + 1])) goto overflow;
    }
    if (used + 1 >= cap) goto overflow;
    out[used++] = '}';
    out[used] = 0;
    return HOS_DEV_OK;
overflow:
    out[0] = 0;
    return HOS_DEV_CAPACITY;
}

int hos_dev_publish_sample(const HosDevSampleV1 *s) {
    if (!enabled) return HOS_DEV_DISABLED;
    if (dispatching) return HOS_DEV_BUSY;
    if (!sample_valid(s)) return HOS_DEV_INVALID;
    latest = *s;
    latest.struct_size = sizeof latest;
    latest.sequence = ++sequence;
    have_sample = 1;
    dispatching = 1;
    for (size_t i = 0; i < observer_count; i++) {
        /* Each observer gets a copy: accidentally writing its const view cannot corrupt the next observer's sample. */
        HosDevSampleV1 copy = latest;
        observers[i].fn(observers[i].user, &copy);
    }
    if (emitter && (!next_emit || s->monotonic_ns >= next_emit)) {
        char json[HOS_DEV_JSON_CAPACITY];
        if (hos_dev_sample_json(&latest, json, sizeof json) == HOS_DEV_OK) emitter(emitter_user, json);
        next_emit = s->monotonic_ns > UINT64_MAX - 500000000ULL ? UINT64_MAX : s->monotonic_ns + 500000000ULL;
    }
    dispatching = 0;
    return HOS_DEV_OK;
}
