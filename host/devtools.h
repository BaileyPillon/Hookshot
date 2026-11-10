/* SPDX-License-Identifier: GPL-3.0-or-later
   Experimental, opt-in observer SDK. Calls are serialized by the player-update hook.
   No guest pointers, memory writes, DLL loader or restore API are exposed. */
#ifndef HOS_DEVTOOLS_H
#define HOS_DEVTOOLS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define HOS_DEV_ABI_V1 1u
#define HOS_DEV_CAP_PLAYER_SAMPLE 1u
#define HOS_DEV_MAX_OBSERVERS 8
#define HOS_DEV_JSON_CAPACITY 960
#define HOS_DEV_LOG_PREFIX "devtools-v1 "

enum HosDevResult {
    HOS_DEV_OK = 0, HOS_DEV_DISABLED = -1, HOS_DEV_INVALID = -2,
    HOS_DEV_ABI_MISMATCH = -3, HOS_DEV_CAPACITY = -4,
    HOS_DEV_DUPLICATE = -5, HOS_DEV_BUSY = -6, HOS_DEV_NO_SAMPLE = -7
};

typedef struct HosDevSampleV1 {
    uint32_t struct_size, abi_version;
    uint64_t sequence, monotonic_ns, program_id;
    char game_build_id[65];     /* NSO build ID: up to 32 bytes, without trailing zero bytes */
    char runtime_build[96];
    char scene[80];
    float position[3];
} HosDevSampleV1;

typedef void (*HosDevSampleFn)(void *user, const HosDevSampleV1 *sample);
typedef void (*HosDevEmitFn)(void *user, const char *json);

typedef struct HosDevObserverV1 {
    uint32_t struct_size, abi_version, required_capabilities;
    const char *id;                 /* copied at registration; [a-z][a-z0-9_.-]{0,62} */
    void *user;                    /* owned by the caller for the runtime's lifetime */
    HosDevSampleFn on_player_sample;
} HosDevObserverV1;

/* Initialize once before guest threads start. Disabled means no sampling or emission.
   Registration, inspection and publication must share the caller's serialization.
   Re-entrant mutation/initialization from an observer is rejected. */
int hos_dev_init(int enabled, HosDevEmitFn emit, void *user);
int hos_dev_enabled(void);
uint32_t hos_dev_capabilities(void);
int hos_dev_register_observer(const HosDevObserverV1 *observer);
int hos_dev_read_sample(HosDevSampleV1 *out);
int hos_dev_publish_sample(const HosDevSampleV1 *sample);
/* JSON uses IEEE-754 position_bits integers, avoiding locale-dependent float text.
   Returns a HosDevResult; on error out is empty (when cap > 0). */
int hos_dev_sample_json(const HosDevSampleV1 *sample, char *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
