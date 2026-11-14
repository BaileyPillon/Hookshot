/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "devtools.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int example_observer_register(void);
static int emits, calls;
static HosDevObserverV1 observer;
static void emit(void *user, const char *json) {
    assert(user == &emits);
    ++emits;
    puts(json);
}
static void attempted_mutation(void *user, const HosDevSampleV1 *sample) {
    (void)user;
    assert(hos_dev_publish_sample(sample) == HOS_DEV_BUSY);
    assert(hos_dev_init(0, NULL, NULL) == HOS_DEV_BUSY);
    assert(hos_dev_register_observer(&observer) == HOS_DEV_BUSY);
    ((HosDevSampleV1 *)sample)->position[0] = 999;
}
static void observe(void *user, const HosDevSampleV1 *sample) {
    assert(user == &calls);
    assert(sample->position[0] == 1.25f);
    HosDevSampleV1 read = {0};
    read.struct_size = sizeof read;
    read.abi_version = HOS_DEV_ABI_V1;
    assert(hos_dev_read_sample(&read) == HOS_DEV_OK);
    assert(read.position[0] == 1.25f && read.sequence == sample->sequence);
    ++calls;
}
int main(void) {
    HosDevSampleV1 sample = {0}, read = {0};
    sample.struct_size = sizeof sample;
    sample.abi_version = HOS_DEV_ABI_V1;
    sample.monotonic_ns = 1000000000;
    sample.program_id = 0x0400486024dec000ULL;
    strcpy(sample.game_build_id, "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    strcpy(sample.runtime_build, "fixture-only");
    strcpy(sample.scene, "Kokiri_\xe6\xb5\x8b\xe8\xaf\x95\"\\\n");
    sample.position[0] = 1.25f;
    sample.position[1] = -2.5f;
    sample.position[2] = 0;
    assert(hos_dev_init(0, emit, &emits) == HOS_DEV_OK);
    assert(!hos_dev_enabled() && !hos_dev_capabilities());
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_DISABLED && !emits);
    assert(hos_dev_init(1, emit, &emits) == HOS_DEV_OK);
    read.struct_size = sizeof read;
    read.abi_version = HOS_DEV_ABI_V1;
    assert(hos_dev_read_sample(&read) == HOS_DEV_NO_SAMPLE);
    observer = (HosDevObserverV1){sizeof observer, HOS_DEV_ABI_V1, HOS_DEV_CAP_PLAYER_SAMPLE,
                                "test.observer", &calls, observe};
    HosDevObserverV1 invalid = observer;
    invalid.abi_version++;
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_ABI_MISMATCH);
    invalid = observer;
    invalid.required_capabilities = 2;
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_ABI_MISMATCH);
    invalid = observer;
    invalid.struct_size = 1;
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_INVALID);
    invalid = observer;
    invalid.id = "../bad";
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_INVALID);
    invalid = observer;
    invalid.id = "test.mutator";
    invalid.on_player_sample = attempted_mutation;
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_OK);
    assert(hos_dev_register_observer(&observer) == HOS_DEV_OK);
    assert(hos_dev_register_observer(&observer) == HOS_DEV_DUPLICATE);
    assert(example_observer_register() == HOS_DEV_OK);
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_OK && emits == 1 && calls == 1);
    sample.monotonic_ns += 100;
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_OK && emits == 1 && calls == 2);
    sample.monotonic_ns += 500000000;
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_OK && emits == 2 && calls == 3);
    char small[8] = "filled", json[HOS_DEV_JSON_CAPACITY];
    assert(hos_dev_sample_json(&sample, small, sizeof small) == HOS_DEV_CAPACITY && !small[0]);
    sample.position[0] = NAN;
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_INVALID && calls == 3);
    sample.position[0] = 1.25f;
    memset(sample.scene, 'a', sizeof sample.scene);
    assert(hos_dev_sample_json(&sample, json, sizeof json) == HOS_DEV_INVALID && !json[0]);
    strcpy(sample.scene, "\xc0\x80");
    assert(hos_dev_publish_sample(&sample) == HOS_DEV_INVALID);
    assert(hos_dev_init(1, NULL, NULL) == HOS_DEV_OK);
    char id[64];
    invalid = observer;
    invalid.id = id;
    for (int i = 0; i < HOS_DEV_MAX_OBSERVERS; i++) {
        snprintf(id, sizeof id, "observer-%d", i);
        assert(hos_dev_register_observer(&invalid) == HOS_DEV_OK);
    }
    strcpy(id, "overflow");
    assert(hos_dev_register_observer(&invalid) == HOS_DEV_CAPACITY);
    assert(hos_dev_init(0, NULL, NULL) == HOS_DEV_OK);
    assert(hos_dev_read_sample(&read) == HOS_DEV_DISABLED);
    return 0;
}
