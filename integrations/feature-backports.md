# Native feature backports

These source-only changes were adapted from the GPL-3.0 community project
[MagicBeanDev/Longshot](https://git.magicbean.dev/MagicBeanDev/Longshot), a different repository from
BaileyPillon/Longshot. Full upstream history was reviewed locally. Existing license notices remain in place;
the table records attribution for the adapted portions. No game-generated cache, code, save or asset is included.

| Upstream revision | Author | Adapted feature |
|---|---|---|
| [eca9b12a8f8dcfddb51b5bbdce89b7fede2ba0fa](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/eca9b12a8f8dcfddb51b5bbdce89b7fede2ba0fa) | TrashPanda; co-authors Joey Magnus and HumanBean | Walk captured memory ranges once per scan, preserving descending-address fallback |
| [5a8ae7e3e89ad5069d1d8fd7290bd46515415115](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/5a8ae7e3e89ad5069d1d8fd7290bd46515415115) | klimovich008; co-author HumanBean | Own-thread lookup, waiter-aware condition-variable signals and cached environment options |
| [f3fe1763dda267a134494f1d21e6ad10b1ec4cd8](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/f3fe1763dda267a134494f1d21e6ad10b1ec4cd8) | HumanBean | Unknown/unissued occlusion queries remain visible; query numbering across queues |
| [08771847e57fe018d2ab04a73dcc329c38be8d83](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/08771847e57fe018d2ab04a73dcc329c38be8d83) | mooki | Scarecrow Song recording/playback timing |
| [b7a46d6bc603200bca00794fd17789ba8dfac20f](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/b7a46d6bc603200bca00794fd17789ba8dfac20f) | bluetoe | Scarecrow recall follows remapped ocarina notes |
| [9f64464b8b9cbf26d13f823711b639c98d324b59](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/9f64464b8b9cbf26d13f823711b639c98d324b59) | mooki | Deku floor-web stepping above 60 FPS |
| [d9648863ab786fd81cb632a65b13ab697b6ee004](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/d9648863ab786fd81cb632a65b13ab697b6ee004) | jarynclouatre | Complete face-button layout presets after clearing a binding |
| [f3673ee4e1e06369f2cb4abf203883896e43cce3](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/f3673ee4e1e06369f2cb4abf203883896e43cce3) | simonwjackson | Half/Normal/Double/Quadruple damage |
| [8732ffaba8a6e543473beab6fe84191557576ecf](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/8732ffaba8a6e543473beab6fe84191557576ecf) | simonwjackson | Half damage uses the complete hit before lethal clamping |
| [e65cb1e00b8116363326988ca05db15822f0924e](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/e65cb1e00b8116363326988ca05db15822f0924e) | simonwjackson | Per-button hold-to-toggle controls and reset on focus/menu/rebind transitions |
| [7315957c08b0ee3845f2a76a132ec1d3c0f105d1](https://git.magicbean.dev/MagicBeanDev/Longshot/commit/7315957c08b0ee3845f2a76a132ec1d3c0f105d1) | pmwork-personal; Lichii work by Zortos | Clustered-light shadow-map descriptor tables, derived from Lichii bd0171f7 and 282a585a |

## Compatibility choices

- Preserve the existing `hookshot_options.ini` name, Longshot save-profile/FPS-size settings, and optional co-op hooks.
- Hold toggles default off. Damage defaults to Normal and is Normal whenever Debug tools are disabled. Existing bindings
  are not remapped by installing this bundle. A layout preset changes bindings only when selected explicitly.
- Use the existing option callback for new option IDs 54/55. No `MkwVkHost` or `MkwVkRenderer` layout changes, so no
  ABI version bump is needed. The unrelated upstream FPS option 53 was not imported.
- Native patch fixtures retain their assertions. Adaptations use the existing `hookshot_env.h`, include the real
  hold-toggle helper in extracted binding fixtures, and retain this branch's MSCRT fixture compatibility definition.
- Repair the Debug-help translation lookup in all 13 existing language tables and add translated damage labels.
  The new long damage/toggle hints currently use the normal English fallback; speaker review remains welcome.
- The descriptor-table port uses this branch's existing descriptor writer. Shader translation changes require fresh
  local shader preparation; an old cache stamp must never be forced to match.
- `RX_VK_HANDLE_TABLES=0` and `HOS_CV_SIGNAL_ALWAYS=1` are diagnostic rollback switches, not recommended defaults.
- Sparse VRAM, a wholesale HeyListen engine replacement, restricted NX2navi additions and emulator frame-generation
  integrations were not combined. The target GPU has 16 GiB; prior local frame generation caused confirmed flicker.

See [research](../docs/longshot-fork-research.md) and [validation](../docs/longshot-validation.md) for the distinction
between source regression tests, local gameplay observation and still-unverified features.
