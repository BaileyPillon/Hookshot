# Longshot integration validation — 13 November 2026

Branch: `feat/fork-feature-integration`. Upstream base: `4aee23659b9436dab2cd7be1ac07333c06246b7c`
(Hookshot v2.2.0-rc.1). The previous Longshot checkpoint/devtools commits remain in history.

## Verified

| Check | Result | What it proves |
|---|---|---|
| Full `python -I -B tests/run_all.py --jobs 4` | **492 passed, 0 failed, 43 skipped**, 338 seconds | Game-free host, renderer, tools, existing checkpoint/devtools and source regression checks. Skips include Linux-only cases, missing .NET/spirv-val and other declared unavailable dependencies. |
| New/affected focused group | **11 passed, 0 failed**, 15 seconds | Profile isolation; mod-manager/native-loader agreement; co-op opt-in/build guards; randomizer synthetic formats and seed-save isolation; overlay/input/present/screensaver regressions. |
| Windows Vulkan renderer build | **206 translation units compiled; 0 failed; DLL linked**, 179 seconds | The combined Vulkan/menu/co-op overlay source builds with the available llvm-mingw toolchain. This validation build did not enable the optional NGX/FSR SDKs. |
| Changed native host compilation | **10 translation units passed** | `hos_main`, profiles, mods, bridge, puppet/platform support, SDL, input, native presentation and Windows display compile together against generated runtime headers. Not a linked full game. |
| Pinned co-op module | **Release build succeeded; 1,319/1,319 CTest cases passed**, 141 seconds | Module/network/state-machine tests, including encrypted/loopback traffic and slow-link simulations. No external server or two-game play session was started. |
| Pinned tracker + compatibility patch | **Build and TypeScript checks passed; 15 tests passed, 11 skipped** | Five test files, public mapping/logic and parser checks. Skipped cases require private save fixtures, which were not added. |
| Mod manager visual check | **Window, row selection, conflict winner and disable action observed** | Tested three authored synthetic mod folders; disabling one visibly changed the row to Off and enabled count from three to two. Screenshot in `docs/images/longshot-mod-manager.png`. |
| Companion preparation | **Pinned archive export and compatibility patch applied** | Source exports stay under ignored `work/longshot-companions`; source submodules remain at the reviewed revisions. |

Host toolchain: existing llvm-mingw from HookshotBuilder; co-op: Visual Studio 2022 x64/CMake; tracker: Node 24 and npm.
The suite used the existing builder Python environment for its declared dependencies. This work did not change Windows,
GPU-driver, BIOS, monitor, or installed game's settings.

## Findings fixed during integration

- Native co-op originally tried loading whenever its module was present. Longshot requires **exact `HOS_COOP=1`** and
  also gates its null-read/platform workarounds on an active module. A compiled bridge fixture checks default-off,
  invalid opt-in values, absent modules and unconsumed input.
- Co-op's Windows mouse handler originally ran ahead of the game menus. Menu clicks/wheel input now take priority;
  the existing menu/pointer checks remain intact.
- Source-extraction fixtures needed the new co-op boundary declarations. Overlay tests now also exercise co-op shown/hidden
  combinations and draw ordering; presentation tests count the co-op present callback. Assertions were retained.
- The GPU-watchdog fixture measured Windows process/DLL startup as watchdog runtime. It now measures elapsed time inside
  the test process, keeping the same deadline bounds and external process timeout.
- Tracker's npm lock omitted Windows optional dependency entries. Its skipped private-save suite also read the absent
  save at test collection time. The recorded patch repairs the lock and defers that read to `beforeAll` without removing assertions.

Before the merge, the older Longshot suite had 285 passes, four failures and 23 skips. Three old failures were missing/wrong
toolchain or Python dependencies; the other was a Windows path fixture. The newer upstream tests and correct existing
toolchain/dependency environment resolve those. The differing test totals reflect upstream's expanded suite, not an A/B performance comparison.

## Not yet verified in the combined game

No new full-game executable was linked or deployed. The source integration requires a fresh game lift; reusing an old
executable with only the new renderer does not validate it. Consequently the PR stays a **draft** pending:

1. Fresh build from the user's local dump, using this source and the normal SDK choices, in a separate development game folder.
2. Load an isolated copy of a save; verify play, sound, DualSense bindings, original checkpoint capture/restore and clean exit.
3. Switch profiles with a restart; verify that each sees only its own progress, and `--user` still overrides profile selection.
4. Inspect FPS size at multiple resolutions and actual controller navigation of the new native-menu rows.
5. Two-player co-op on isolated saves: puppets, joining/leaving, inventory/progress consistency, reconnect and saving.
6. Generate and verify a randomizer seed against the actual game build; play it. Synthetic round-trips do not prove seed beatability.
7. Verify tracker recognition against actual saves and its overlay during gameplay.
8. Before enabling frame generation/HDR, compare the same scene and check the prior blur/flicker symptoms. No FPS or stutter
   improvement has been measured, and no such improvement is claimed.

Linux, other GPU vendors, handheld devices, reserved NX2navi code and incomplete Master Quest content are not represented as
tested integrations. Existing playable files, native saves and graphics/controller settings were not replaced.

Detailed local logs are in ignored `work/fork-research/`: `final-suite.log`, `focused-final.log`, `renderer-build.log`,
`host-compile.log`, `coop-tests.log`, `tracker-integrated-build.log` and `tracker-integrated-tests.log`.
Those logs and generated game/companion data are not part of the source PR.
