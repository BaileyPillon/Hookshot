/* SPDX-License-Identifier: GPL-3.0-or-later
   Source-linked restore coordinator, not a game-specific capture/restore backend.
   Zero-initialize the controller. Serialize every call on the backend's owning
   thread. File reads/decompression, immutable staging and save backups happen on
   a worker before begin; no callback here may block or perform file I/O.
   tick runs only while the backend holds the reported subsystem barriers until
   tick returns. A past observation or the player-update lock is not a barrier. */
#ifndef HOS_CHECKPOINT_H
#define HOS_CHECKPOINT_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum HosCheckpointResult {
    HOS_CP_OK = 0, HOS_CP_PENDING = 1, HOS_CP_UNAVAILABLE = -1, HOS_CP_INVALID = -2,
    HOS_CP_BUSY = -3, HOS_CP_STALE = -4, HOS_CP_TIMEOUT = -5,
    HOS_CP_PROVIDER_ERROR = -6, HOS_CP_ROLLBACK_FAILED = -7, HOS_CP_CANCELLED = -8
};
enum HosCheckpointMode { HOS_CP_PORTABLE = 1, HOS_CP_EXACT = 2 };
enum HosCheckpointState {
    HOS_CP_IDLE, HOS_CP_WAIT_SAFE, HOS_CP_WAIT_RELOAD, HOS_CP_ROLLING_BACK, HOS_CP_COMMITTED,
    HOS_CP_FAILED, HOS_CP_RECOVERY_REQUIRED
};
enum HosCheckpointSafety {
    HOS_CP_FRAME_START = 1u << 0, HOS_CP_WORKERS_PARKED = 1u << 1,
    HOS_CP_IO_IDLE = 1u << 2, HOS_CP_SAVE_BOUND = 1u << 3,
    HOS_CP_GPU_DRAINED = 1u << 4, HOS_CP_AUDIO_IDLE = 1u << 5,
    HOS_CP_THREADS_MATCH = 1u << 6
};
#define HOS_CP_PORTABLE_SAFETY (HOS_CP_FRAME_START | HOS_CP_WORKERS_PARKED | HOS_CP_IO_IDLE | HOS_CP_SAVE_BOUND)
#define HOS_CP_EXACT_SAFETY (HOS_CP_PORTABLE_SAFETY | HOS_CP_GPU_DRAINED | HOS_CP_AUDIO_IDLE | HOS_CP_THREADS_MATCH)
#define HOS_CP_BUSY_NS 500000000ULL
#define HOS_CP_RELOAD_NS 30000000000ULL

typedef struct HosCheckpointTicket {
    uint64_t request_id, session_id;
    uint32_t mode;
    unsigned char save_binding[32]; /* SHA-256 of the validated profile/save-data/slot identity */
} HosCheckpointTicket;

typedef struct HosCheckpointBoundary {
    uint64_t session_id, scene_generation;
    uint32_t safe;
    unsigned char save_binding[32];
} HosCheckpointBoundary;

typedef struct HosCheckpointBackend {
    void *user;
    uint32_t capabilities; /* HOS_CP_PORTABLE | HOS_CP_EXACT; zero means unavailable */
    int (*probe)(void *, HosCheckpointBoundary *); /* OK or PENDING, fresh runtime evidence */
    /* Recheck prepared payload, full identity, anchors and signatures under the held boundary. */
    int (*revalidate)(void *, const HosCheckpointTicket *, const HosCheckpointBoundary *);
    int (*backup)(void *); /* owned rollback capture, no mutations; native save backup already staged */
    /* Always request a fresh scene generation, even for the current scene. Sync old HUD before flags. */
    int (*begin_portable)(void *);
    int (*poll_reload)(void *); /* PENDING or OK only when the target scene/age is fully ready */
    int (*finish_portable)(void *); /* native physics/pose/health setters, after fresh scene */
    int (*apply_exact)(void *); /* all validation complete before any guest memory is touched */
    int (*invalidate_exact)(void *); /* write tracking, textures, GPU/audio resources */
    int (*rollback)(void *); /* start restoring original progress/scene/resources: OK or PENDING */
    int (*poll_rollback)(void *); /* revalidate baseline, OK only after recovery is complete */
    void (*discard)(void *); /* release prepared buffers after success or a clean failure */
} HosCheckpointBackend;

typedef struct HosCheckpoint {
    HosCheckpointBackend backend;
    HosCheckpointTicket ticket;
    uint64_t started, last_tick, old_generation, last_request;
    uint32_t state, blocked; /* missing safety bits, retained on timeout for diagnostics */
    int result, inside, mutated, failure_result;
} HosCheckpoint;

int hos_checkpoint_init(HosCheckpoint *, const HosCheckpointBackend *);
int hos_checkpoint_begin(HosCheckpoint *, const HosCheckpointTicket *, uint64_t now_ns);
int hos_checkpoint_tick(HosCheckpoint *, uint64_t now_ns);
/* Cancellation is supported before mutation only. Never imply an in-flight load was undone. */
int hos_checkpoint_cancel(HosCheckpoint *);
int hos_checkpoint_reset(HosCheckpoint *);
/* RECOVERY_REQUIRED retains the backend's rollback data and refuses reset/new work.
   The owner must resolve recovery or shut down safely; it must never silently
   fall back to portable after a failed exact write or target another save slot. */
#ifdef __cplusplus
}
#endif
#endif
