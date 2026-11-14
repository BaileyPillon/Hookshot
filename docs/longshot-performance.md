# Longshot performance investigation — November 2026

The earlier ordinary-mode acceptance sample averaged 38.88 FPS in the Deku Tree. It was not a controlled comparison.
On a fresh launch of the same executable (`ccd7a233`), the dungeon reached 59.8–60.0 FPS before any source change.
The cause of the earlier 39 FPS result is therefore not established. Castle Town reproduced a heavier workload and
became the comparison scene. No change to Windows, the graphics driver, BIOS or the separate regular play installation
was made for these measurements.

## Change under test

Backport [MagicBeanDev/Longshot's occlusion-report fix, `cd906265`](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/cd9062658d35884032590b822b825ebbd00899e2),
by HumanBean, building on jordanella/dyst's earlier work. That is a separate community project from this
BaileyPillon/Longshot fork. The imported code and its tests are GPL-compatible.

Previously, every samples-passed report said an object was visible. The game consequently submitted objects hidden
behind other geometry. The renderer now obtains real Vulkan query results for depth-only bounding-box draws and
returns available counts to the game without waiting for the GPU. Missing, stale, skipped or overflowing query runs
remain visible. Colour-writing draws are not queried by default. `RX_VK_OCC_QUERIES=0` is the comparison/rollback switch.
The device must support host query reset; otherwise the old conservative path remains in use.

The full local game was incrementally rebuilt with the existing O2/PGO hot code and NVIDIA NGX support. The candidate
reports source fingerprint `23b69111`. Both sides below use that same executable and renderer, changing only the named
process environment variables. This avoids comparing different game recompilations.

## Measurement method

- Ryzen 7 7800X3D, RTX 5070 Ti 16 GB, NVIDIA 610.47, Windows 11 Pro 26200; 64 GB RAM configured at 4800 MT/s.
- 2560×1440 configured output, 1600×900 window, DLSS Quality, Reflex On, 60 FPS cap, frame generation and HDR Off.
- Every controlled run starts from identical copies of the same native save in a new private user directory. The
  user's active experimental profile and regular game's saves are not used as writable benchmark directories.
- Load Deku Tree, debug-teleport to `Market_Child`, wait for gameplay/loading completion and 600 additional presents.
  Measure 45 seconds standing at the entrance, then 45 seconds with right-stick X held at 0.6. Exclusive scripted input
  prevents simultaneous player movement. Reject a window if its map changes or loading resumes.
- `HOS_PRESENT_TRACE` supplies original-game CPU present intervals. FPS is 1000 divided by the mean interval, not the
  average of a rounded FPS counter. These are not monitor scanout times or generated-frame counts. p99 is the 99th
  percentile interval; smaller is better. Draw counts are the mean of bridge samples over the window.
- Earlier trials were interrupted by normal player input and are excluded from controlled comparisons. The user
  confirmed playing during those trials. One early apparent Market run actually ended at Hyrule Castle.
- Other applications remain open. Background CPU work and driver caches are uncontrolled; alternating runs and the
  draw-count reduction support a narrower conclusion than a universal FPS guarantee.

## Warm-cache comparison

The new renderer's state-header change invalidated its local translated shader cache. A first visit was used for
warming, then the runs below alternated the query setting. These particular trials temporarily used
`RX_VK_PRECOMPILE=0` in the child process to test visited areas while developing. This is not a recommended saved
setting: complete shader preparation and a normal-startup verification are required before play handoff.

| Run | Occlusion queries / CPU reservation | Standing FPS / p99 ms | Turning FPS / p99 ms | Standing / turning mean draws | Turning frames over 50 ms |
|---|---|---|---|---|---|
| off-b | Off / default | 59.462 / 23.977 | 58.298 / 24.834 | 2938 / 1465 | 2 |
| on-b | On / default | 59.818 / 22.805 | 59.782 / 23.118 | 2518 / 1249 | 0 |
| off-c | Off / default | 55.432 / 26.598 | 57.331 / 26.040 | 2972 / 1453 | 1 |
| shared-a | On / `HOS_RESERVE_CORE=0` | 56.008 / 24.259 | 53.462 / 37.576 | 2496 / 1277 | 12 |

Matched entrance screenshots were inspected with queries off and on: buildings, pavement, the guard and distant scene
remained visible. NPC and fairy animations differ between captures. This is a spot check, not proof that every camera
angle or object in the game is correct. The paired runs suggest about 14–15% fewer submitted draws in these views.
The all-cores-shared trial did not improve this machine's result and was not retained.

All trials are retained locally, including less favourable results. Before this sequence, `on-a` reached 60.000/60.002 FPS
in 35-second dungeon standing/turning windows, but its later Market standing window fell to 40.267 FPS (p99 40.110 ms).
Its Market turning window then recovered to 58.851 FPS with three frames over 50 ms. The initial cache-warming control
had a 213.564 ms frame while turning in the Market. These observations rule out claiming that the code change alone
eliminates every slowdown. Temporary Reflex-Off and Above-Normal-priority trials showed no convincing improvement;
Reflex On and normal process priority were restored.

Local measurement scripts, raw present traces, screenshots, process settings and copied saves remain in ignored
`work/longshot-performance` and `work/fork-research`. None of the game-derived files is part of this source change.

## Build and regression checks

The incremental full-game build examined 646 translation units, rebuilt the changed host/renderer pieces and linked
both binaries without failures. The full source suite then passed **495 checks, zero failures, 43 declared skips** in
1,345 seconds with two workers. Targeted occlusion-ring and FSR uniform-ownership fixtures also passed. Gameplay
benchmarks were paused while these checks and shader preparation ran.

Complete shader preparation exited 0 after 2,229 seconds. It produced 25,382 noted graphics pipelines and 9,925 compute
pipelines from 4,127 compute programs, with none missing. On the next normal start, NVIDIA's required first-game-process
warm completed in 17.0 seconds (3.4 seconds for computes); subsequent loading used the prepared caches at program creation.
The first run's long preparation is not an acceptable recurring startup cost: another fresh launch must verify reuse.
