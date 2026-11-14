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
A second normal launch reused those caches: startup preparation took 5.7 seconds and built no new noted pipelines.
The 37-minute preparation did not repeat. This does not mean every pipeline predicted for the entire game is in the
driver's cache: its separate probe found 3 of 32 predicted examples.

The first GitHub run caught a Windows Microsoft-CRT `getenv` deprecation under `-Werror` in the new standalone
occlusion fixture. Declaring `_CRT_SECURE_NO_WARNINGS` before its headers keeps the portable read-only call, assertions
and warning policy intact. The fixture passed locally with the compiler's runtime DLL directory on PATH. All 13
applicable GitHub jobs passed at `90c1e6b0`, including both OS source-test shards and the DLSS/FSR renderer link check.

## Normal-startup gameplay and rejected settings

These runs used normal shader preparation and default core reservation. Occlusion queries remained On; sampler
caching was Off except in the explicitly named experiment. They use original-game present intervals, as above.

| Run / view | Average FPS | p99 ms | Worst ms | Frames over 50 ms |
|---|---:|---:|---:|---:|
| final-a / Deku Tree standing, 35 s | 60.000 | 18.764 | 23.029 | 0 |
| final-a / Deku Tree turning, 35 s | 59.990 | 18.951 | 55.953 | 1 |
| final-a / Market standing, 45 s | 59.423 | 23.850 | 47.741 | 0 |
| final-a / Market turning, 45 s | 59.195 | 23.822 | 45.319 | 0 |
| final-a / field forest-entrance movement, 45 s | 58.005 | 31.540 | 104.575 | 9 |
| final-a / Kakariko entrance movement, 45 s | 59.741 | 23.673 | 29.374 | 0 |
| final-b / sampler cache On, Market standing, 45 s | 28.137 | 547.577 | 3145.334 | 43 |
| final-b / sampler cache On, Market turning, 45 s | 2.143 | 2813.343 | 3011.796 | 70 |
| final-c / sampler cache Off again, Market standing, 45 s | 53.396 | 28.231 | 102.539 | 4 |
| final-c / sampler cache Off again, Market turning, 45 s | 55.396 | 32.227 | 184.705 | 12 |

The movement windows combine forward stick input and camera turning. The field run is in its forest approach corridor,
not the centre of the open field; Kakariko is its entry steps, not a village tour. Screenshots were inspected at the
entries and after movement. This is bounded gameplay verification, not a campaign-wide visual/performance guarantee.

The sampler-cache experiment was rejected and never written to saved options. Its severe stalls coincided with high
system page-input activity. After reverting it, multi-second stalls disappeared, but the repeated default run was
still slower than final-a. Background work was changing, so the sampler switch alone cannot be assigned all of that
difference. During final-c, the game had a 15.13 GiB working set, Windows had about 4.2 GB available, and Blender and AI
applications were active. They were left running. Page-input counters include file-backed reads and do not by themselves
prove that Windows was reading the page file or that the game has a memory leak.

These results establish near-60 gameplay in several bounded windows, **not sustained smooth 60 FPS everywhere**.

## Pipeline-cache memory experiment

`memory-a` used child-only `RX_VK_PCACHE_LOAD=0`, leaving the existing cache files intact. Market standing/turning
averaged 58.043 / 58.836 FPS, p99 28.420 / 25.978 ms, with 4 / 3 frames over 50 ms. Its working set near the Market
windows was about 13.4 GB. The later forest movement crossed into Kokiri Forest; that timing window was rejected.

The experiment also made 1,152 listed pipelines unavailable from the caches. The existing safety net consequently
wrote `hookshot_load_start.txt`, changing later automatic launches from loading programs when the game creates them
to keeping all listed programs ready before the title. `memory-control`, with the pipeline cache enabled again,
therefore **was not a single-variable comparison** with memory-a. It averaged 56.249 / 51.567 FPS, p99 33.788 / 65.395 ms,
with 9 / 56 frames over 50 ms. Its working set was about 20.5 GB and available physical memory fell below 2 GB.

The file-cache-off repeat `memory-b` inherited that fallback and began recompiling 26,792 listed pipelines before
the title. Preparation took 352.5 seconds. Its Market standing/turning windows averaged 52.000 / 53.220 FPS, p99
49.233 / 41.786 ms, with 22 / 16 frames over 50 ms. The working set again reached about 20.5 GB. This memory option
is rejected: it was never saved to the environment file. The changed loader mode,
uncontrolled background activity and startup cost prevent treating the 13.4-versus-20.5 GB observations as an isolated
measurement of the pipeline cache file's memory cost. The fallback marker is retained with the local experiment
evidence when restoring the normal cache-backed path; genuine repeated cache misses remain protected by the safety net.

## Follow-up renderer changes

Source fingerprint `844b897e` adds two reviewed GPL backports from the separate community project:

- [Hugo Claria's `fbd42024`](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/fbd420241afdba1d5ba2936971eb48549edb85ae):
  take the per-thread pass/descriptor writer once per hot function, retaining the same object and rendering operations.
  Four affected fixtures use the new reference names while keeping their existing assertions. The author's measured
  Steam Deck CPU-work reduction is not reported as a Windows FPS gain here.
- [HumanBean's `341d63a4`](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/341d63a485013ef56ef4912a8553caa2959a3239):
  a single isolated slow program load no longer permanently selects the heavier start mode. Only waits over 20 ms
  count; over 500 ms in two consecutive sessions or over 2,000 ms in one session trigger that fallback. The independent
  rule for more than 500 unavailable listed pipelines is unchanged, so it still catches the rejected cache experiment.
  Compiled fixtures cover thresholds, consecutive-session strikes, marker files and cache-miss protection.

The local build examined 646 translation units, completed compilation in 31 seconds with no failures, and linked the
executable and renderer in 3 seconds and under 1 second respectively. The shader translator and cache stamp inputs are
unchanged. The old experimental binaries are retained locally for alternating comparisons and rollback.
The complete local source suite passed **495 checks, zero failures, 43 declared skips** in 478 seconds with three
workers and no game running. No assertion, warning policy or timeout was relaxed.

### Alternating full-game comparison

Both sides used the same preserved graphics settings, pipeline cache enabled and explicit child-only
`RX_VK_LOAD=create`. Each fresh launch used the same private save copy and the same settled Market entry route.
Windows were 30 seconds standing and 30 seconds turning; no compiler, source tests or sampler ran concurrently.
The normal process priority and all other user applications were retained. Binary copies were SHA-256 verified.

| Run / source | Standing FPS / p99 ms | Turning FPS / p99 ms | Frames over 50 ms, standing / turning |
|---|---|---|---|
| cpu-before-a / 23b69111 | 51.920 / 33.943 | 44.575 / 42.503 | 1 / 2 |
| cpu-after-a2 / 844b897e | 56.027 / 29.960 | 52.099 / 41.746 | 3 / 5 |
| cpu-before-b2 / 23b69111 | 56.608 / 29.683 | 57.303 / 27.931 | 0 / 2 |
| cpu-after-b2 / 844b897e | 58.029 / 27.462 | 58.870 / 25.589 | 0 / 2 |

The candidate was faster than its preceding control in both pairs, but the control's own large improvement shows
substantial run-to-run variation. The evidence supports retaining the tested changes, not attributing the entire
FPS difference to them or promising a locked 60. The final comparison left the candidate installed in ordinary
experimental mode; the dedicated randomizer and regular play installations were not updated. No fallback or strike
marker was recreated during these four runs, and the saved environment still contains no loading/cache override.

### Diagnostic sampling and process priority

A separate 20-second all-thread sample of `844b897e` in the Market identifies CPU work as the next investigation:
the presentation thread was running in about 79% of sampled instants, with draw translation, memory/mirror work and
replay submission prominent. Main-thread waits and synchronization also matter. The sampled run averaged 55.05 FPS
and used about five CPU cores, **including diagnostic overhead**. Sampled occupancy includes preemption and is not
CPU instruction timing; the report's estimated savings are hypotheses, not achieved improvements. Raw stacks, binary
wait-chain records and linker maps remain local; no game-derived symbols or data are published.

With sampling markers removed, four 20-second standing windows in the same process alternated Normal and Above Normal
priority. Normal averaged 59.802 and 59.984 FPS (p99 21.613/21.381 ms); Above Normal averaged 57.252 and 54.739
(p99 27.375/29.438 ms). None had a frame over 50 ms. Higher priority was rejected and Normal restored before clean exit.
The profiling switch remained enabled, but the sampler was inactive during these four windows. The earlier 20-second
diagnostic-route windows were slower: 53.367 standing / 42.638 turning, with a 964.653 ms worst turning frame. These
unfavourable observations remain recorded; diagnostic runs are not the main before/after performance evidence.
