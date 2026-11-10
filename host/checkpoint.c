/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "checkpoint.h"
#include <string.h>

static int bound(const unsigned char bytes[32]) {
    unsigned char any = 0;
    for (unsigned i = 0; i < 32; i++) any |= bytes[i];
    return any != 0;
}
static int finish(HosCheckpoint *c, int result) {
    c->result = result;
    c->state = result == HOS_CP_OK ? HOS_CP_COMMITTED : HOS_CP_FAILED;
    c->backend.discard(c->backend.user);
    return result;
}
static int recovery_required(HosCheckpoint *c) {
    c->state = HOS_CP_RECOVERY_REQUIRED;
    c->result = HOS_CP_ROLLBACK_FAILED;
    return c->result; /* retain rollback/staged data for recovery; no second restore path */
}
static int fail(HosCheckpoint *c, int result, int can_rollback) {
    if (c->state == HOS_CP_ROLLING_BACK) return recovery_required(c);
    if (c->mutated) {
        if (!can_rollback) return recovery_required(c);
        const int rolled_back = c->backend.rollback(c->backend.user);
        if (rolled_back == HOS_CP_PENDING) {
            c->failure_result = result;
            c->started = c->last_tick;
            c->state = HOS_CP_ROLLING_BACK;
            return HOS_CP_PENDING;
        }
        if (rolled_back != HOS_CP_OK) return recovery_required(c);
    }
    return finish(c, result);
}
int hos_checkpoint_init(HosCheckpoint *c, const HosCheckpointBackend *backend) {
    if (!c) return HOS_CP_INVALID;
    if (c->inside || c->state == HOS_CP_WAIT_SAFE || c->state == HOS_CP_WAIT_RELOAD || c->state == HOS_CP_ROLLING_BACK ||
        c->state == HOS_CP_RECOVERY_REQUIRED) return HOS_CP_BUSY;
    const HosCheckpointBackend copy = backend ? *backend : (HosCheckpointBackend){0};
    memset(c, 0, sizeof *c);
    backend = &copy;
    if (!backend->capabilities) return HOS_CP_UNAVAILABLE;
    if ((backend->capabilities & ~(HOS_CP_PORTABLE | HOS_CP_EXACT)) || !backend->probe ||
        !backend->revalidate || !backend->backup || !backend->rollback || !backend->poll_rollback || !backend->discard ||
        ((backend->capabilities & HOS_CP_PORTABLE) &&
         (!backend->begin_portable || !backend->poll_reload || !backend->finish_portable)) ||
        ((backend->capabilities & HOS_CP_EXACT) && (!backend->apply_exact || !backend->invalidate_exact)))
        return HOS_CP_INVALID;
    c->backend = *backend;
    return HOS_CP_OK;
}
int hos_checkpoint_begin(HosCheckpoint *c, const HosCheckpointTicket *ticket, uint64_t now) {
    if (!c || !ticket) return HOS_CP_INVALID;
    if (c->inside || c->state != HOS_CP_IDLE) return HOS_CP_BUSY;
    if (!c->backend.capabilities) return HOS_CP_UNAVAILABLE;
    if ((ticket->mode != HOS_CP_PORTABLE && ticket->mode != HOS_CP_EXACT) ||
        !ticket->request_id || !ticket->session_id || !bound(ticket->save_binding)) return HOS_CP_INVALID;
    if (!(c->backend.capabilities & ticket->mode)) return HOS_CP_UNAVAILABLE;
    if (ticket->request_id <= c->last_request) return HOS_CP_STALE;
    c->ticket = *ticket;
    c->last_request = ticket->request_id;
    c->started = c->last_tick = now;
    c->mutated = 0;
    c->blocked = 0;
    c->state = HOS_CP_WAIT_SAFE;
    c->result = HOS_CP_PENDING;
    return HOS_CP_OK;
}
static int step(HosCheckpoint *c, uint64_t now) {
    if (c->state != HOS_CP_WAIT_SAFE && c->state != HOS_CP_WAIT_RELOAD && c->state != HOS_CP_ROLLING_BACK) return c->result;
    if (now < c->last_tick) return fail(c, HOS_CP_STALE, 0);
    c->last_tick = now;
    HosCheckpointBoundary boundary = {0};
    const int probed = c->backend.probe(c->backend.user, &boundary);
    if (probed != HOS_CP_OK && probed != HOS_CP_PENDING) return fail(c, HOS_CP_PROVIDER_ERROR, 0);
    const uint64_t limit = c->state == HOS_CP_WAIT_SAFE ? HOS_CP_BUSY_NS : HOS_CP_RELOAD_NS;
    const uint32_t needed = c->ticket.mode == HOS_CP_EXACT ? HOS_CP_EXACT_SAFETY : HOS_CP_PORTABLE_SAFETY;
    c->blocked = probed == HOS_CP_OK ? needed & ~boundary.safe : needed;
    const int ready = probed == HOS_CP_OK && (boundary.safe & needed) == needed;
    const int same = boundary.session_id == c->ticket.session_id &&
                     bound(boundary.save_binding) && !memcmp(boundary.save_binding, c->ticket.save_binding, 32);
    if (probed == HOS_CP_OK && !same) return fail(c, HOS_CP_STALE, 0);
    if (now - c->started >= limit) return fail(c, HOS_CP_TIMEOUT, ready && same);
    if (!ready) return HOS_CP_PENDING;
    if (c->state == HOS_CP_ROLLING_BACK) {
        const int recovered = c->backend.poll_rollback(c->backend.user);
        if (recovered == HOS_CP_PENDING) return HOS_CP_PENDING;
        if (recovered != HOS_CP_OK) return recovery_required(c);
        return finish(c, c->failure_result);
    }
    if (c->backend.revalidate(c->backend.user, &c->ticket, &boundary) != HOS_CP_OK)
        return fail(c, HOS_CP_STALE, 0);
    if (c->state == HOS_CP_WAIT_RELOAD) {
        const int loaded = c->backend.poll_reload(c->backend.user);
        if (loaded == HOS_CP_PENDING) return HOS_CP_PENDING;
        if (loaded != HOS_CP_OK) return fail(c, HOS_CP_PROVIDER_ERROR, 1);
        if (boundary.scene_generation <= c->old_generation)
            return HOS_CP_PENDING; /* same scene still needs a real reload, not a timer */
        if (c->backend.finish_portable(c->backend.user) != HOS_CP_OK)
            return fail(c, HOS_CP_PROVIDER_ERROR, 1);
        return finish(c, HOS_CP_OK);
    }
    if (c->ticket.mode == HOS_CP_PORTABLE && !boundary.scene_generation)
        return fail(c, HOS_CP_INVALID, 0);
    if (c->backend.backup(c->backend.user) != HOS_CP_OK) return fail(c, HOS_CP_PROVIDER_ERROR, 0);
    c->mutated = 1; /* even a callback returning failure might already have made a partial write */
    if (c->ticket.mode == HOS_CP_EXACT) {
        if (c->backend.apply_exact(c->backend.user) != HOS_CP_OK ||
            c->backend.invalidate_exact(c->backend.user) != HOS_CP_OK)
            return fail(c, HOS_CP_PROVIDER_ERROR, 1);
        return finish(c, HOS_CP_OK);
    }
    if (c->backend.begin_portable(c->backend.user) != HOS_CP_OK) return fail(c, HOS_CP_PROVIDER_ERROR, 1);
    c->old_generation = boundary.scene_generation;
    c->started = now;
    c->state = HOS_CP_WAIT_RELOAD;
    return HOS_CP_PENDING;
}
int hos_checkpoint_tick(HosCheckpoint *c, uint64_t now) {
    if (!c) return HOS_CP_INVALID;
    if (c->inside) return HOS_CP_BUSY;
    if (!c->backend.capabilities) return HOS_CP_UNAVAILABLE;
    c->inside = 1;
    const int result = step(c, now);
    c->inside = 0;
    return result;
}
int hos_checkpoint_cancel(HosCheckpoint *c) {
    if (!c) return HOS_CP_INVALID;
    if (c->inside || c->state != HOS_CP_WAIT_SAFE || c->mutated) return HOS_CP_BUSY;
    c->inside = 1;
    const int result = finish(c, HOS_CP_CANCELLED);
    c->inside = 0;
    return result;
}
int hos_checkpoint_reset(HosCheckpoint *c) {
    if (!c) return HOS_CP_INVALID;
    if (c->inside || (c->state != HOS_CP_IDLE && c->state != HOS_CP_COMMITTED && c->state != HOS_CP_FAILED))
        return HOS_CP_BUSY;
    c->state = HOS_CP_IDLE;
    c->result = HOS_CP_OK;
    c->mutated = 0;
    c->blocked = 0;
    memset(&c->ticket, 0, sizeof c->ticket);
    return HOS_CP_OK;
}
