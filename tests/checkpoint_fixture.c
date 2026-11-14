/* SPDX-License-Identifier: GPL-3.0-or-later
   Synthetic backend: tests the production coordinator without a game or a GPU. */
#include "checkpoint.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct Fake {
    HosCheckpoint controller;
    HosCheckpointBackend backend;
    HosCheckpointTicket ticket;
    HosCheckpointBoundary boundary;
    int progress, original, backup_count, portable_count, exact_count, invalidate_count;
    int finish_count, rollback_count, discard_count, probe_result, revalidate_result;
    int backup_result, apply_result, reload_result, finish_result, invalidate_result, rollback_result, recovery_result;
} Fake;

static int probe(void *user, HosCheckpointBoundary *out) {
    Fake *f = user;
    *out = f->boundary;
    assert(hos_checkpoint_tick(&f->controller, 0) == HOS_CP_BUSY);
    assert(hos_checkpoint_begin(&f->controller, &f->ticket, 0) == HOS_CP_BUSY);
    assert(hos_checkpoint_cancel(&f->controller) == HOS_CP_BUSY);
    assert(hos_checkpoint_reset(&f->controller) == HOS_CP_BUSY);
    assert(hos_checkpoint_init(&f->controller, &f->backend) == HOS_CP_BUSY);
    return f->probe_result;
}
static int revalidate(void *user, const HosCheckpointTicket *ticket, const HosCheckpointBoundary *boundary) {
    Fake *f = user;
    assert(ticket->request_id == f->ticket.request_id);
    assert(boundary->session_id == f->ticket.session_id);
    return f->revalidate_result;
}
static int backup(void *user) {
    Fake *f = user;
    ++f->backup_count;
    f->original = f->progress;
    return f->backup_result;
}
static int portable(void *user) {
    Fake *f = user;
    ++f->portable_count;
    f->progress = 7; /* may partially mutate before returning failure */
    return f->apply_result;
}
static int exact(void *user) {
    Fake *f = user;
    ++f->exact_count;
    f->progress = 9;
    return f->apply_result;
}
static int poll_reload(void *user) { return ((Fake *)user)->reload_result; }
static int finish_portable(void *user) {
    Fake *f = user;
    ++f->finish_count;
    return f->finish_result;
}
static int invalidate(void *user) {
    Fake *f = user;
    ++f->invalidate_count;
    return f->invalidate_result;
}
static int rollback(void *user) {
    Fake *f = user;
    ++f->rollback_count;
    if (f->rollback_result == HOS_CP_OK) f->progress = f->original;
    return f->rollback_result;
}
static int poll_rollback(void *user) {
    Fake *f = user;
    if (f->recovery_result == HOS_CP_OK) f->progress = f->original;
    return f->recovery_result;
}
static void discard(void *user) { ++((Fake *)user)->discard_count; }
static void setup(Fake *f, uint32_t mode) {
    memset(f, 0, sizeof *f);
    f->progress = 42;
    f->boundary.session_id = f->ticket.session_id = 1;
    f->boundary.scene_generation = 10;
    f->boundary.safe = HOS_CP_EXACT_SAFETY;
    f->boundary.save_binding[0] = f->ticket.save_binding[0] = 11;
    f->ticket.request_id = 123;
    f->ticket.mode = mode;
    f->backend = (HosCheckpointBackend){f, HOS_CP_PORTABLE | HOS_CP_EXACT, probe, revalidate, backup,
                                       portable, poll_reload, finish_portable, exact, invalidate, rollback, poll_rollback, discard};
    assert(hos_checkpoint_init(&f->controller, &f->backend) == HOS_CP_OK);
}
static void begin(Fake *f) { assert(hos_checkpoint_begin(&f->controller, &f->ticket, 100) == HOS_CP_OK); }

int main(void) {
    Fake f;
    HosCheckpoint disabled = {0};
    assert(hos_checkpoint_init(&disabled, NULL) == HOS_CP_UNAVAILABLE);
    setup(&f, HOS_CP_PORTABLE);
    assert(hos_checkpoint_begin(&disabled, &f.ticket, 0) == HOS_CP_UNAVAILABLE);
    f.backend.rollback = NULL;
    assert(hos_checkpoint_init(&f.controller, &f.backend) == HOS_CP_INVALID);
    setup(&f, HOS_CP_PORTABLE);
    f.ticket.save_binding[0] = 0;
    assert(hos_checkpoint_begin(&f.controller, &f.ticket, 0) == HOS_CP_INVALID);

    /* Every exact barrier matters; a player lock alone cannot authorize a restore. */
    for (unsigned bit = 0; bit < 7; bit++) {
        setup(&f, HOS_CP_EXACT);
        f.boundary.safe &= ~(1u << bit);
        begin(&f);
        assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
        assert(f.controller.blocked == (1u << bit));
        assert(hos_checkpoint_tick(&f.controller, 100 + HOS_CP_BUSY_NS) == HOS_CP_TIMEOUT);
        assert(f.controller.blocked == (1u << bit));
        assert(!f.backup_count && !f.exact_count && f.discard_count == 1 && f.progress == 42);
    }
    setup(&f, HOS_CP_PORTABLE);
    begin(&f);
    f.probe_result = HOS_CP_PENDING;
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    assert(hos_checkpoint_cancel(&f.controller) == HOS_CP_CANCELLED);
    assert(!f.backup_count && f.discard_count == 1);
    assert(hos_checkpoint_reset(&f.controller) == HOS_CP_OK);
    assert(hos_checkpoint_begin(&f.controller, &f.ticket, 102) == HOS_CP_STALE);

    /* A same-name scene must be reloaded: a ready poll with the old generation is insufficient. */
    setup(&f, HOS_CP_PORTABLE);
    f.boundary.safe = HOS_CP_PORTABLE_SAFETY;
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    assert(f.progress == 7 && f.backup_count == 1 && f.portable_count == 1);
    assert(hos_checkpoint_cancel(&f.controller) == HOS_CP_BUSY);
    assert(hos_checkpoint_tick(&f.controller, 102) == HOS_CP_PENDING && !f.finish_count);
    f.boundary.scene_generation++;
    f.reload_result = HOS_CP_PENDING;
    assert(hos_checkpoint_tick(&f.controller, 103) == HOS_CP_PENDING && !f.finish_count);
    f.reload_result = HOS_CP_OK;
    assert(hos_checkpoint_tick(&f.controller, 104) == HOS_CP_OK);
    assert(f.finish_count == 1 && f.discard_count == 1 && !f.rollback_count && !f.exact_count);
    assert(hos_checkpoint_tick(&f.controller, 105) == HOS_CP_OK && f.finish_count == 1);
    assert(hos_checkpoint_begin(&f.controller, &f.ticket, 106) == HOS_CP_BUSY);

    setup(&f, HOS_CP_EXACT);
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_OK);
    assert(f.progress == 9 && f.exact_count == 1 && f.invalidate_count == 1 && !f.portable_count);

    /* Failures after the first mutation roll back; exact never falls through to portable. */
    for (int mode = HOS_CP_PORTABLE; mode <= HOS_CP_EXACT; mode++) {
        setup(&f, (uint32_t)mode);
        f.apply_result = HOS_CP_PROVIDER_ERROR;
        begin(&f);
        assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PROVIDER_ERROR);
        assert(f.progress == 42 && f.rollback_count == 1 && f.discard_count == 1);
        if (mode == HOS_CP_EXACT) assert(!f.portable_count && !f.invalidate_count);
    }
    setup(&f, HOS_CP_PORTABLE);
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    f.boundary.scene_generation++;
    f.finish_result = HOS_CP_PROVIDER_ERROR;
    assert(hos_checkpoint_tick(&f.controller, 102) == HOS_CP_PROVIDER_ERROR);
    assert(f.progress == 42 && f.rollback_count == 1);

    /* Recovery may need another scene transition; do not report success or free its backup early. */
    setup(&f, HOS_CP_PORTABLE);
    f.apply_result = HOS_CP_PROVIDER_ERROR;
    f.rollback_result = f.recovery_result = HOS_CP_PENDING;
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    assert(f.controller.state == HOS_CP_ROLLING_BACK && f.rollback_count == 1 && !f.discard_count);
    assert(hos_checkpoint_tick(&f.controller, 102) == HOS_CP_PENDING && f.rollback_count == 1);
    f.recovery_result = HOS_CP_OK;
    assert(hos_checkpoint_tick(&f.controller, 103) == HOS_CP_PROVIDER_ERROR);
    assert(f.progress == 42 && f.discard_count == 1 && f.rollback_count == 1);

    setup(&f, HOS_CP_PORTABLE);
    f.apply_result = HOS_CP_PROVIDER_ERROR;
    f.rollback_result = f.recovery_result = HOS_CP_PENDING;
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    assert(hos_checkpoint_tick(&f.controller, 101 + HOS_CP_RELOAD_NS) == HOS_CP_ROLLBACK_FAILED);
    assert(f.rollback_count == 1 && !f.discard_count); /* no unbounded rollback restart */

    setup(&f, HOS_CP_PORTABLE);
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
    assert(hos_checkpoint_tick(&f.controller, 101 + HOS_CP_RELOAD_NS) == HOS_CP_TIMEOUT);
    assert(f.progress == 42 && f.rollback_count == 1);

    /* Another live save/session is never a rollback target. Retain evidence instead. */
    for (int different_slot = 0; different_slot < 2; different_slot++) {
        setup(&f, HOS_CP_PORTABLE);
        begin(&f);
        assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_PENDING);
        if (different_slot) f.boundary.save_binding[0]++;
        else f.boundary.session_id++;
        assert(hos_checkpoint_tick(&f.controller, 102) == HOS_CP_ROLLBACK_FAILED);
        assert(f.controller.state == HOS_CP_RECOVERY_REQUIRED && !f.rollback_count && !f.discard_count);
        assert(hos_checkpoint_reset(&f.controller) == HOS_CP_BUSY);
    }
    setup(&f, HOS_CP_EXACT);
    f.invalidate_result = f.rollback_result = HOS_CP_PROVIDER_ERROR;
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_ROLLBACK_FAILED);
    assert(f.controller.state == HOS_CP_RECOVERY_REQUIRED && !f.discard_count && !f.portable_count);
    assert(hos_checkpoint_tick(&f.controller, 102) == HOS_CP_ROLLBACK_FAILED && f.exact_count == 1);

    setup(&f, HOS_CP_PORTABLE);
    f.revalidate_result = HOS_CP_STALE;
    begin(&f);
    assert(hos_checkpoint_tick(&f.controller, 101) == HOS_CP_STALE);
    assert(!f.backup_count && f.progress == 42 && f.discard_count == 1);
    puts("checkpoint coordinator: barriers, deadline, fresh reload, save binding, re-entrancy and rollback passed");
    return 0;
}
