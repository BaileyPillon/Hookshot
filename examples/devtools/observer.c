/* SPDX-License-Identifier: GPL-3.0-or-later
   Compile this into a developer build and call example_observer_register() after
   hos_dev_init(), before guest threads start. No DLL autoloading is implemented. */
#include "devtools.h"
#include <stdint.h>

static uint64_t samples_seen;
static void on_player(void *user, const HosDevSampleV1 *sample) {
    uint64_t *count = (uint64_t *)user;
    (void)sample; /* A future challenge mod can observe scene/position transitions here. */
    ++*count;
}
int example_observer_register(void) {
    const HosDevObserverV1 observer = {
        sizeof observer, HOS_DEV_ABI_V1, HOS_DEV_CAP_PLAYER_SAMPLE,
        "example.sample-counter", &samples_seen, on_player
    };
    return hos_dev_register_observer(&observer);
}
