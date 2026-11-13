# Optional source integrations

`manifest.json` records the exact reviewed revisions; `.gitmodules` records their upstream locations.
These are optional source dependencies, not bundled game files or prebuilt executables.
Each submodule retains its own license and attribution. Initialize them with `git submodule update --init`.

| Component | Revision | License | Integration |
|---|---|---|---|
| [oot-remake-multiplayer](https://github.com/daurosk/oot-remake-multiplayer) | `f5e4ca3b407197349af3045abff4bb7475ac2fd8` | GPL-3.0 | Native bridge/lifter/renderer patches plus optional module |
| [Hookshot Randomized](https://github.com/KAMOX06/hookshot-randomized) | `91f301987e8f67b5239bb22429137077a1e330d0` | MIT | Isolated source preparation and launcher |
| [Boomerang Tracker](https://github.com/LucieTheFool/boomerang-tracker) | `0fb33437e620adb3d3634f28ed7650c20bb2361c` | MIT | Isolated source preparation, build and save-folder-aware launcher |

The co-op source patches `hookshot/patches/0001-coop-bridge.patch`, `0002-coop-puppets.patch`, and
`0003-coop-platforms.patch` were applied to Longshot's host, renderer and lifter. Original attribution remains in
those files. Longshot's follow-up changes require exact opt-in, gate puppet/platform workarounds on module activation,
keep menu mouse priority, and extend the existing regression fixtures. No co-op server starts automatically.

`patches/tracker-build.patch` repairs omitted Windows optional dependency entries in the upstream npm lockfile and
moves a private-save fixture read into `beforeAll`, so a skipped suite does not read an absent save during collection.
It does not remove any assertions or include private fixtures. The patch is applied to an ignored export, preserving
the source submodule's reviewed revision. Upstream's MIT license also applies to the modified tracker portions.

The independent save-profile and mod-manager implementations are part of Longshot under its repository license.
They use workflow ideas from the research, not reserved NX2navi additions or Mako's restricted controller artwork.

See [usage and limits](../docs/longshot-features.md), [research](../docs/longshot-fork-research.md) and
[validation](../docs/longshot-validation.md). No game-derived cache, overlay, puppet pack, save or secret belongs here.
