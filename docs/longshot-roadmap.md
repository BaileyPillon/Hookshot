# Ranked Longshot development backlog

For the visible new-feature ranking requested on November 14, start with [Features players will notice](longshot-player-roadmap.md).
This page retains the engineering and acceptance work that supports those features.

Updated 13 November 2026 (local time). This is the working order for BaileyPillon/Longshot, based on the
[49-repository review and Reddit sources](longshot-fork-research.md), inspected source, and this PC's local tests.
It is not a popularity leaderboard or a promise that every fork can be merged. MagicBeanDev/Longshot is a separate project.

The repository's severity × reach × confidence score informs the order. **Reach here is scoped to the affected
Longshot workflow/target PC**, not an invented share of all gamers. A reproduced defect takes precedence over a
feature request; prerequisites, compatibility and effort break ties. Community anecdotes guide discovery and
user needs; controlled tests decide defaults. The target is Windows, Ryzen 7 7800X3D, RTX 5070 Ti 16 GiB and 64 GiB RAM.

| Rank | Improvement and evidence | Priority reasoning | Acceptance gate | State |
|---|---|---|---|---|
| 1 | Preserve the destination when save import/export fails. [GPL upstream 58484df8](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/58484df8), recurring save-migration requests and local injected failures. | S0 × 1 × 1 = **8**. Existing slots were deleted before the new copy completed. Small, high-confidence data-safety fix. | Partial slot/loose-file failures leave old data intact; rename failure rolls back; failed rollback retains named recovery data; source and backup survive. | Adapted; nine failure/success checks pass. Included in the subsequent 511-pass full sweep. |
| 2 | Report heap plus mapped pages accurately so the game sizes its caches to the console budget. [GPL upstream a4c77174](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/a4c77174). Local testing observed heavy Windows paging, not a proven sole cause of all slow frames. | S2 × 1 × 0.7 = **2.1**. Strong mechanism and upstream measurements; local impact still requires measurement. Better fit than smaller-VRAM presets for this GPU. | Duplicate/partial mappings, free/reallocate, saturation, allocation failure and exact legacy reports; same-route process/guest memory and frame-time comparison. | Conservative accounting subset implemented. Lazy heap commitment and changed GPU-import defaults excluded. Compiled checks pass and the combined game loads. Controlled RAM/FPS comparison remains pending; pressured runs are retained. |
| 3 | Complete acceptance of the existing controller/gameplay/render bundle: hold toggles, damage choices, layout/ocarina/web fixes, CPU paths, conservative occlusion and Lichii shadow-map tables. | Delivery gate before stacking another renderer rewrite. Eleven selected commits already integrated; 506 checks and 13 applicable GitHub jobs passed at 3ef85c28. | Fresh shaders; new menu controls visible and usable; preserved preferences; multi-area gameplay; no claim of locked 60 until measurements support it. | Compiled and deployed only to the experimental folder; fresh shader preparation completed successfully. Multi-area acceptance remains open. Regular play install untouched. |
| 4 | Prevent mouse releases outside the window becoming clicks after return; hide the idle cursor during controller/keyboard play. [d906c8f4](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/d906c8f4), [c0442078](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/c0442078). | S3 × 1 × 0.7 = **0.7**. Fits a DualSense-first setup and multitasking; small native-host changes, no graphics-cache reset. | Compiled focus/menu/pointer fixtures; visible menu interaction and cursor recovery. Do not attribute the earlier NPC conversation to this bug without reproducing it. | Adapted with the existing co-op pointer hook preserved. Regression fixtures pass; full native interaction acceptance remains pending. |
| 5 | Make performance comparisons reproducible: reject dialogue/loading, isolate input for the whole route, record system pressure and retained slower runs. | Prerequisite for performance claims across every future candidate. The previous baseline's NPC dialogue invalidated its standing/turning comparison; a later run suffered severe paging. | Same native save bytes, settings, route and original-frame trace; no source tests/builds during measurements; retained invalid-run reason and cleanup. | Local harness now rejects events and supports child-only whole-route input isolation; use for this iteration, then promote reusable parts. |
| 6 | Read-only sampled live game-state interface, then an Ocarina Atlas adapter with explicit localhost scope. [1ea02558](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/1ea02558), [Ocarina Atlas](https://github.com/antonioalvromero/Ocarina-Atlas). | Useful developer/community interface, independent of the clean performance comparison. Current Boomerang tracker remains save-based. | Opt-in, bounded snapshots, versioned schema, no arbitrary memory writes, accurate map/position/flags, disconnect/reconnect; review map artwork before bundling. | Native sampler/CLI built; 511 checks pass and two-client copied-save gameplay verified. Original Adventure Journal adds visible trail/waypoints/counters. Atlas base/art license gap prevents treating the full app as an MIT drop-in. |
| 7 | Finish real two-player co-op and full randomizer/multiworld validation. | Existing optional features need acceptance more than another similar companion. No broad Reddit consensus proves synchronization or progression correctness. | Two actual clients, transitions/reconnect/save consistency; complete randomized progression and delivery; retain separate profiles/mode install. | Source integrations and narrower tests complete; end-to-end acceptance pending. |
| 8 | In-game checkpoint browser and configurable controller shortcuts, followed by genuine live-state quicksave/load. | Strong prior user request and Sunshine-inspired design. Native-save archives already work; instant world restoration needs a safe-point backend and resource reconstruction, not filesystem copying. | Saving at a safe point, explicit restore boundary, interrupted-write recovery, audio/GPU/actor consistency, control reset, crash/version rejection and pause-menu navigation. | Launcher archive browser exists. Pause-menu/live-memory backend remains development work; do not label archives as live save states. |
| 9 | Additional renderer experiments: GPU mirror-copy dispatch, sparse VRAM, quick pipelines and recorder scheduling. | Only promote a measured benefit with acceptable frame-time tails and visuals. The current 16 GiB target does not justify every low-VRAM change; earlier parallel recording and sampler caching lost locally. | Several same-scene A/B runs, GPU/CPU timing, visual checks, memory cost and rollback; no cache-stamp bypass. | Candidates retained; no unmeasured global defaults. |

## Iteration rules and preserved boundaries

- The ordinary play installation, its settings and saves are protected separately from the experimental game.
  Profile 4's current experimental progress is also protected. Tests use copied native saves.
- Save-copy failure recovery uses temporary folders on the destination volume and a retained backup. It handles
  reported copy/rename failures; it is not a claim of atomic recovery from a power loss between every rename.
- The accounting adaptation keeps Windows heap commitment and GPU-import lifetime rules. No hard page-allocation
  limit is introduced: upstream reports that the game can retry rejected allocations indefinitely.
- Frame generation/HDR remain off on this PC after the earlier confirmed flicker. The FPS counter, PS5 prompts,
  15% deadzone, 2× text and existing bindings stay as selected.
- No arbitrary app closure, memory cleaner, page-file change or global priority tweak is part of this work.
- The user chose to keep Blender running after Windows counters showed a competing GPU workload. Continue independent
  development; defer a clean 60 FPS acceptance measurement until a quiet window. Preserve pressured/aborted runs.
- Restricted NX2navi additions, community game-derived caches, incomplete Master Quest assets and incompatible
  emulator cores remain excluded. Improvements that need original development stay explicit backlog items.
- Each iteration records source tests, build, deployment, runtime observations and acceptance separately in
  [validation](longshot-validation.md) and [performance](longshot-performance.md). The PR remains a draft while
  the outstanding gameplay gates are open.
