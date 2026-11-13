"""Co-op is opt-in: execute the actual bridge with a fake guest and absent DLL.

Also check the lifter refuses another build/instruction stream. Networking and
actor synchronization have their own tests in the pinned co-op module.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import coop_hooks
import coop_puppet_guard


def check_lift():
    words = {coop_hooks.MAIN + off: coop_hooks.MOV_X0_X20 for off, _, _ in coop_hooks.FRAME_SITES}
    words.update({coop_hooks.MAIN + off + 4: word for off, word, _ in coop_hooks.FRAME_SITES})
    words.update({coop_hooks.MAIN + coop_hooks.HOLD_CALL + 4 * i: w for i, w in enumerate(coop_hooks.HOLD_WORDS)})
    words.update({coop_puppet_guard.MAIN + off: word for off, word in coop_puppet_guard.WORDS})
    image = SimpleNamespace(word=lambda pc: words.get(pc, 0))
    lifter = SimpleNamespace(after={})
    assert coop_hooks.install(lifter, image, "different-game") == 0 and not lifter.after
    assert coop_hooks.install(lifter, image, coop_hooks.BUILD_ID) == 3
    assert "hos_coop_active()" in lifter.after[coop_puppet_guard.MAIN + coop_puppet_guard.SITE]
    for pc in list(words)[:6]:
        old = words[pc]
        words[pc] = old ^ 1
        refused = SimpleNamespace(after={})
        assert coop_hooks.install(refused, image, coop_hooks.BUILD_ID) == 0 and not refused.after
        words[pc] = old


HEAD = r'''
#include <stdint.h>
#include <stdlib.h>
#include <windows.h>
typedef struct { uint64_t x[32], vreg[32][2]; } Ctx;
typedef void (*A64Fn)(Ctx*);
A64Fn a64_lookup(uint64_t p) {return NULL;}
void recomp_store64(Ctx *c, uint64_t p, uint64_t v) {abort();}
void hos_log(const char *s, ...) {}
uint8_t *hos_guest_base(void) {abort();}
int hos_mem_region(uint64_t p, uint64_t n) {return 0;}
void hos_mark_written(const void *p, uint64_t n) {abort();}
const char hos_main_build_id[] = "fake-game";
volatile uint64_t hos_coop_pad;
int probes;
DWORD fake_module(HMODULE m, LPWSTR p, DWORD n) {++probes; return 0;}
#define GetModuleFileNameW fake_module
'''
TAIL = r'''
int main(void) {
 const char *off[] = {"", "0", "false", "no", "2", "true", "1extra"};
 for (unsigned i=0; i<sizeof off/sizeof off[0]; ++i) {
  _putenv_s("HOS_COOP",off[i]); state=0; probes=0;
  hos_coop_frame(NULL,0); hos_coop_frame(NULL,0);
  if (state!=3 || probes || hos_coop_active() || hos_coop_hold(0,42)!=42) return 2;
  if (hos_coop_key(32,0) || hos_coop_char(65) || hos_coop_mouse(0,0,0) || hos_coop_keys_taken()) return 3;
  hos_coop_present();
 }
 _putenv_s("HOS_COOP","1"); state=0; probes=0;
 hos_coop_frame(NULL,0);
 if (probes!=1 || state!=3 || hos_coop_active()) return 4;
 puts("co-op: off preserves input and guest state; exact opt-in probes for module, absence fails closed");
 return 0;
}
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    check_lift()
    if os.name == "nt":
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = (ROOT / "host/coop_bridge.c").read_text().replace('#include "hos.h"', HEAD)
            (folder / "fixture.c").write_text(source + TAIL)
            exe = folder / "fixture.exe"
            subprocess.run([args.cxx, "-x", "c", "-std=c11", "-I" + str(ROOT / "host"), str(folder / "fixture.c"), "-luser32", "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
