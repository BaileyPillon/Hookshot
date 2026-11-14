# Longshot integration validation — 13 November 2026

Branch: `feat/fork-feature-integration`. Upstream base: `4aee23659b9436dab2cd7be1ac07333c06246b7c`
(Hookshot v2.2.0-rc.1). The previous Longshot checkpoint/devtools commits remain in history.

## Verified

| Check | Result | What it proves |
|---|---|---|
| Parallel recording comparison | **Normal renderer retained: 56.933/57.919 FPS standing/turning versus 58.597/55.324 with three recording threads** | Normal path had better p99 in both 30-second windows and fewer moving-camera stalls. Existing option tested only in child environment, never saved; both clean exits. |
| Latest code/build CI, `1d50ac16` | **All 13 applicable GitHub checks passed** | Both Windows/Linux source shards, renderer/Builder/AppImage, DLSS+FSR link, checkpoints, SPIR-V and workflow checks; release publication skipped. The dav1d job exercised the official mirror fallback and compiled the dependency successfully. |
| Dependency download resilience | **Official VideoLAN GitHub mirror matched the existing pinned 1.5.4 source-tree SHA-256** | The primary VideoLAN server failed before compilation in two CI attempts. The fallback changes the download origin only; the existing source integrity gate remains mandatory. Windows shell syntax and CPM checks passed; Linux-only pin tests are covered by Linux CI, not by a direct Windows invocation. |
| Latest normal-startup gameplay, source `844b897e` | **Deku 59.996/58.150; Market 51.954/53.507; field approach 59.974; Kakariko entrance 58.627 FPS** | Standing/turning or bounded movement windows, no profiler or loader/cache overrides. A newly captured compatible checkpoint restored and loaded, preparation cache reused in 4.296 s, clean exit. These results do not meet a consistent 60 FPS target. |
| Native window and counter | **Small FPS counter at top right and PS5 prompts visibly confirmed** | Focus experiment varied and lost focus during testing; it does not establish a causal FPS fix. No physical DualSense/audio acceptance claimed. |
| Alternating runtime builds | **Candidate's two Market runs: 56.03/52.10 and 58.03/58.87 FPS, standing/turning** | Controls 51.92/44.57 and 56.61/57.30 FPS; same graphics, cache-backed create mode and private saves. Candidate faster in both pairs, but control variation is substantial; no locked-60 or precise percentage gain claim. All four exited cleanly and left no loader fallback marker. |
| Follow-up accessor/loading-policy backports | **Full source suite: 495 passed, 0 failed, 43 skipped**, 478 seconds, 3 workers | Source `844b897e`; existing toolchain and no concurrent game. Full game/renderer incremental compilation succeeded in 31 s, followed by 3 s executable link and under 1 s renderer link. Shader translator/cache stamp inputs unchanged. |
| Performance follow-up CI, `90c1e6b0` | **All 13 applicable GitHub checks passed** | Windows/Linux source shards, renderer/Builder/AppImage, DLSS+FSR link, checkpoints, SPIR-V and workflow checks. The standalone occlusion fixture's Microsoft-CRT deprecation was fixed without weakening its assertions or `-Werror`; release jobs were intentionally skipped. |
| Normal-startup runtime and restart | **Deku Tree 59.99–60.00; Market 59.19–59.42; Kakariko entrance 59.74 FPS in final-a; later Market repeats slower** | Original-game present traces and inspected screenshots. Full cache reused on restart in 5.7 s. Sampler-cache On experiment severely stalled and was rejected; background workload/memory pressure confound attribution. See the performance report for every retained result and limits. |
| Occlusion backport full source suite | **495 passed, 0 failed, 43 skipped**, 1,345 seconds, 2 workers | Clean complete sweep with the correct existing toolchain; no gameplay benchmark ran concurrently. Shader preparation ran in the background. No assertions/timeouts weakened. |
| Occlusion backport local build and cache | **Incremental game/renderer build succeeded; shader preparation exited 0** | Source `23b69111`, existing O2/PGO and NGX. Full preparation took 2,229 s. The subsequent game's one-time cache warm built 25,382 noted and 9,925 compute pipelines in 17.0 s, with none missing. Only the experimental ordinary-mode game was updated. |
| Final source sweep and failed-case reruns | **494 checks passed across the sweep and reruns; 43 skipped; no unresolved failures** | The full sweep took 687 s with a game running: 490 passed, two compiler setup failures and two 60 s fixture timeouts. Setting the existing `HOOKSHOT_MINGW` fixed `fpx_sticky` and `spawn_emit` (56/58 s). After the game closed, unchanged `exclusive_marks` and `fallback_buffer_cleanup` passed serially in 19 s. This is not a single clean 494-pass run; no assertion or timeout was weakened. |
| Full `python -I -B tests/run_all.py --jobs 3` after launcher additions | **493 passed, 0 failed, 43 skipped**, 506 seconds | Game-free host, renderer, tools, existing checkpoint/devtools and source regression checks. Skips include Linux-only cases, missing .NET/spirv-val and other declared unavailable dependencies. Run alongside the fresh game compilation. |
| New/affected focused group | **11 passed, 0 failed**, 15 seconds | Profile isolation; mod-manager/native-loader agreement; co-op opt-in/build guards; randomizer synthetic formats and seed-save isolation; overlay/input/present/screensaver regressions. |
| Windows Vulkan renderer build | **206 translation units compiled; 0 failed; DLL linked**, 179 seconds | The combined Vulkan/menu/co-op overlay source builds with the available llvm-mingw toolchain. This validation build did not enable the optional NGX/FSR SDKs. |
| Changed native host compilation | **10 translation units passed** | `hos_main`, profiles, mods, bridge, puppet/platform support, SDL, input, native presentation and Windows display compile together against generated runtime headers. Not a linked full game. |
| Pinned co-op module | **Release build succeeded; 1,319/1,319 CTest cases passed**, 141 seconds | Module/network/state-machine tests, including encrypted/loopback traffic and slow-link simulations. No external server or two-game play session was started. |
| Pinned tracker + compatibility patch | **Build and TypeScript checks passed; 15 tests passed, 11 skipped** | Five test files, public mapping/logic and parser checks. Skipped cases require private save fixtures, which were not added. |
| Mod manager visual check | **Window, row selection, conflict winner and disable action observed** | Tested three authored synthetic mod folders; disabling one visibly changed the row to Off and enabled count from three to two. Screenshot in `docs/images/longshot-mod-manager.png`. |
| Companion preparation | **Pinned archive export and compatibility patch applied** | Source exports stay under ignored `work/longshot-companions`; source submodules remain at the reviewed revisions. |
| Launcher save operations | **12 tests passed** | Verified copies, original/profile isolation, first-launch creation of missing profile parents, rejection of incomplete/oversized saves and links, cleanup on simulated disk failure, and stopping publication when a game starts during import. |
| Co-op join form backend | **16 launcher tests passed**, including the earlier 12 | Additional checks reject profile 1, invalid connection fields, missing module/pack metadata and a puppet pack active in ordinary play. The plan clears inherited test/cheat flags and keeps the password out of command arguments. No connection is implied by these tests. |
| Full-randomizer integration | **4 boundary checks passed** | Missing mode installation fails closed; separate game/app-data target; rejected ordinary-game process and mod paths; managed Turbo A does not start or remap controller bindings. |
| Pinned OoTrR + isolation patch | **351 tests run, 69 skipped, zero failures**; **59-module self-check passed** | 282 passing tests; skipped cases require local game data. Logic self-check loaded 1,136 location names. This alone does not prove an actual seed is beatable or Archipelago item delivery works in gameplay. |
| Launcher visual/function check | **Capture and restore observed in the Tk window** | An authored synthetic save was captured, listed and restored into profile 2. The source still contained both slots; the restored profile contained only the selected slot. Hardware advice displayed the detected CPU, RAM and GPU without writing settings. |
| GitHub checks for `30acd9279cd1` | **All applicable checks passed** | Both Windows/Linux source-test shards, checkpoints, SPIR-V/workflow checks, Windows renderer/Builder, full DLSS+FSR link check, and Linux AppImage build. Release publication was intentionally skipped on this draft PR. |
| Randomizer with local game assets | **Seed 1132026 generated; independent overlay verifier returned OK** | Chest/shop shuffle and patch consistency against the actual build's assets. Verifier reported 174 chests, 141 changed, and 63/64 shop slots changed. Does not prove progression logic or beatability. |
| Co-op asset generation | **Completed from the local RomFS** | Generated child/adult puppet packs, HUD, and room data (3,599 placements in 257 rooms / 12 dungeons). Files remain local and outside ordinary active mods. Not a two-player gameplay result. |
| Tracker runtime | **Window opened and parsed an isolated copy of the actual save** | Displayed slot 03 / Inside the Deku Tree, three hearts and three Skulltulas. Source saves were not used as the tracker's writable settings directory. Full-game mapping accuracy and overlay during gameplay still need acceptance. |
| Fresh full Windows build | **646 translation units; zero failures; executable and renderer linked** | Fresh lift with co-op hooks, the normal eight hot-code pieces at O2 with the shipped PGO profile, and NVIDIA NGX enabled. Final compilation reused completed objects and took 348 seconds, followed by 4 seconds linking the executable. Earlier manually invoked monolithic compilations were interrupted after discovering the omitted split step; their elapsed times are not normal build-time measurements. |
| Experimental deployment | **Separate game folder, copied saves/settings/caches, shared read-only-use RomFS path** | The new executable, renderer, co-op module and regenerated controller prompts were installed separately from the regular play installation. NVIDIA DLSS initialization and the first-start preparation screen were observed. Frame generation and HDR remain off. This row alone does not prove gameplay. |
| Combined-game runtime | **Copied Deku Tree save loaded; Link/camera moved; scene screenshots inspected; exit 0** | Windows 11 / 7800X3D / 64 GB / RTX 5070 Ti, driver 610.47. Source fingerprint `9e1287f9`. Twenty control-bridge samples over 40.5 s after movement: mean 53.55 FPS, range 3.9–60.5; the first 17 were 59.0–60.5. Stalls occurred and their cause is not established. This is not a before/after benchmark or proof of stutter-free play. |
| Cache reuse | **Restart reused 46,673 program keys and five play-cache files; intro active at 8.7 s uptime** | Initial preparation took roughly 35 minutes; restart did not repeat it. A fresh 42,072-record shipped pipeline-state list was installed before that restart. |
| Actual native-save checkpoint | **Slot 03 archived and restored into profile 3; native profile override mounted it; only slot 03 listed** | The original copied profile retained all six slots. The game loaded `InsideTheDekuTree` from the restored profile and exited 0. Checkpoints are native save snapshots tied to build identity, not live-memory states. |
| Co-op runtime after fix | **One client connected over encrypted loopback; copied save loaded; movement and exit 0** | Source `ccd7a233`; server bound only to 127.0.0.1, then stopped. Module, HUD/font assets and 3,599-entry room table loaded. Server saw map/enemy-state messages. No second player, remote puppet, reconnect or multi-player save result is claimed. |
| Co-op UI | **Join form inspected; all fields and password note fit** | Screenshot `docs/images/longshot-coop-join.png`; backend validation and runtime connection tested separately. |
| OoTrR actual seed | **Seed longshot1132026: logic replay reported beatable, 32 spheres** | Generated from the user's local package into its dedicated mode; 1,136 location names loaded. A proof in the solver is not an actual completed campaign. |
| OoTrR game and companion | **New game booted, opening and Kokiri Forest cutscene rendered; exit 0; companion opened seed and reported live tracking On** | Separate game had 96 active RomFS files and merged the PS5 font table. The companion recognized the package and dedicated mods directory; its setup confirmed automatic Turbo A disabled. Cutscenes had substantial stalls while source tests were also running; no smooth-play claim or completed randomized progression. |
| Saved preferences | **Runtime readback retained PS5 prompts, 15% deadzone, text 2x, FPS 70% at top right, DLSS Quality, Reflex, FG/HDR off** | Game screenshots showed PlayStation prompts. Physical DualSense input and audible speaker output are not verified by settings readback. |
| Final ordinary-mode launch | **Current-build checkpoint restored into profile 4, loaded and rendered Deku Tree; co-op logged Off; exit 0** | Source `ccd7a233`. Twelve stationary bridge samples after loading: mean 38.88 FPS, range 36.2–45.0. This differs from the earlier moved-camera sample and is not an A/B benchmark. Performance remains an acceptance concern; this branch is not promoted over the regular game. |

Host toolchain: existing llvm-mingw from HookshotBuilder; co-op: Visual Studio 2022 x64/CMake; tracker: Node 24 and npm.
The suite used the existing builder Python environment for its declared dependencies. This work did not change Windows,
GPU-driver, BIOS, monitor, or installed game's settings.
The regular installation's executable, renderer, options and environment-file hashes matched the pre-test baseline.
Separate local desktop shortcuts were created for the experimental launcher and full-randomizer game; the source PR itself
does not install shortcuts or contain the user's package paths, seeds, caches or saves.

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
- The launcher explicitly supplies `--user`, bypassing the native menu profile selector. It now creates a new profile's
  parent directories before starting the game; the dedicated first-launch regression passes.
- Actual co-op startup exposed a font-loading access violation: `HOS_FS_OVERLAY` replaced the resource size table after
  the prompt-size merge. The join plan now uses `HOS_MODS` scoped to the puppet pack's parent. Exact `HOS_COOP=1` permits
  that top-level `coop-puppet` marker for this session without changing it on disk. The normal loader merges the PS5 font
  entry, the crash disappeared, and the client reached gameplay. A compiled fixture checks ordinary/invalid opt-in values
  still leave it disabled. The incremental full-game rebuild compiled and linked without failures in 21 seconds.

Before the merge, the older Longshot suite had 285 passes, four failures and 23 skips. Three old failures were missing/wrong
toolchain or Python dependencies; the other was a Windows path fixture. The newer upstream tests and correct existing
toolchain/dependency environment resolve those. The differing test totals reflect upstream's expanded suite, not an A/B performance comparison.

## Not yet verified in the combined game

The follow-up [performance investigation](longshot-performance.md) records the newer renderer and controlled native
frame-time measurements. The earlier FPS samples above remain historical observations of the earlier build; they are
not the baseline for a claimed percentage speedup.

A new executable and matching renderer were freshly lifted, compiled and deployed to a separate experimental folder.
The PR stays a **draft** while the following gameplay acceptance checks are completed:

1. Physical DualSense input and audible speaker output; the controller was not detected during this run.
2. FPS size at multiple resolutions and actual controller navigation of the new native-menu rows.
3. Two-player co-op: remote puppets, inventory/progress consistency, reconnect and saving.
4. Complete randomized progression and Archipelago delivery; seed generation, logic replay and a successful boot are narrower checks.
5. Tracker mapping accuracy and overlay during extended gameplay.
6. Before enabling frame generation/HDR, compare the same scene and check the prior blur/flicker symptoms. Both stay Off
   during the follow-up performance work; its results do not validate either feature or every game area.

Linux, other GPU vendors, handheld devices, reserved NX2navi code and incomplete Master Quest content are not represented as
tested integrations. Existing playable files, native saves and graphics/controller settings were not replaced.

Detailed local logs are in ignored `work/fork-research/`: `final-suite.log`, `focused-final.log`, `renderer-build.log`,
`host-compile.log`, `coop-tests.log`, `tracker-integrated-build.log` and `tracker-integrated-tests.log`.
Those logs and generated game/companion data are not part of the source PR.

## Ranked iteration, 13 November 2026

The [ranked backlog](longshot-roadmap.md) connects the existing fork/Reddit research to concrete acceptance gates.
The preceding eleven-backport bundle at `3ef85c28` passed 506 checks with zero failures and 43 declared skips,
and all 13 applicable GitHub jobs passed. It was fully lifted and compiled locally. This iteration adds staged
save-copy recovery, mapped-page reports and two mouse/cursor fixes; upstream attribution is in
[feature backports](../integrations/feature-backports.md).

- Save failures were reproduced against the previous implementation: four failing checks and one error in the
  nine-case portable transaction suite. After adaptation all nine pass, including partial copies, rollback failure,
  read-only cleanup, a backup failure, preserved settings and dry run. Fixtures use authored bytes, never real saves.
- Compiled memory fixtures check duplicate/partial/zero mappings, leaf boundaries, allocation failure, double frees,
  capped totals and exact legacy reports. Heap commitment and GPU-import thresholds were not changed.
- Mouse focus, pointer and screensaver fixtures passed. The imported cursor fixture initially assumed no co-op hover
  hook; its ordering assertion was adapted to preserve both behaviors rather than deleting the hook.
- Fresh shader preparation exited 0 in 1,530.3 seconds. The final precompile reported 24,489 noted pipelines and
  9,925 compute pipelines, with zero of either not made. The translator's old cache was not relabelled or forced valid.
- The incremental native build compiled in 367 seconds with zero failures, then linked the executable in four
  seconds and renderer in one. Runtime content fingerprint: `a2f3402d` (a content fingerprint, not a Git revision).
- The experimental executable and renderer were backed up, replaced and SHA-256 verified. Saved options were
  byte-identical after shader preparation. A new compatible slot-03 archive was captured and restored into a private
  test directory. The active experimental profile and ordinary play installation were not used as test destinations.

The complete suite finished in 1,208 seconds with **508 passes, one timing failure and 43 declared skips**. The
failed `test_prepare_stall.py` fixture printed a waiting message after its simulated moving worker paused; its
unchanged isolated rerun passed in 52.4 seconds with the game and compilers closed. All 509 checks therefore have
passing coverage, but this was not a single all-green sweep. No assertion or timeout was relaxed.

Gameplay results follow when finished. Source tests, successful compilation, checkpoint preparation and actual
gameplay acceptance are separate gates.
