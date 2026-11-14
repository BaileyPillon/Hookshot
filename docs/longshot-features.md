# Longshot integration branch

This branch combines Hookshot **v2.2.0-rc.1** with Longshot's checkpoint foundation, separate save profiles,
adjustable FPS text, a mod manager, hold-toggle controls, damage scaling, selected native renderer/gameplay fixes,
an original live Adventure Journal, and pinned co-op, randomizer and completion-tracker integrations.
It is a development build. See [validation](longshot-validation.md) for exactly what was tested and what still needs gameplay acceptance.
The [ranked development backlog](longshot-roadmap.md) records the implementation order and remaining acceptance gates.
The [player feature ranking](longshot-player-roadmap.md) prioritizes the item wheel, live companion, checkpoints,
co-op customization and other noticeable additions, with evidence and explicit implementation boundaries.

The [research report](longshot-fork-research.md) explains the selection, licenses and exclusions. The existing
play installation is not updated by these source changes or the companion preparation commands.

## Included from the newer Hookshot foundation

The upstream merge includes pipeline preparation from Fritchii's recipe; renderer, shader and memory-management fixes;
newer DLSS/FSR frame-generation paths and frame diagnostics; radial stick deadzones, alternate controller bindings,
independent ocarina-note bindings and touchpad menu support; field-of-view/camera controls; audio/background controls;
13-language menus; opening skip; and the local control/bug-report tools. Availability of graphics features depends on
the build's optional SDKs and the GPU. Inclusion of source is not a performance measurement or a recommendation to enable frame generation.

## Controller and gameplay additions

**Insert → Controls → Bindings** now has a **Toggle** column. Turn it on for a held action, such as running,
shielding or aiming: one press holds the action, the next releases it. It follows the existing remapped keyboard
and controller bindings, including DualSense bindings. All toggles start Off; Plus/Minus and the separate ocarina
note rows cannot latch. Opening menus, losing focus or rebinding releases latched actions. Resetting controls also
resets toggles. Enabling a toggle does not swap your physical button bindings.

**Insert → Debug → Debug tools On → Player → Damage taken** offers Half, Normal, Double and Quadruple damage.
Normal is the default. Turning Debug tools off restores Normal behavior without forgetting the selected value.
Healing is unaffected; Half rounds up to a quarter heart, and Heart protection takes precedence. This is a local
gameplay option; mixed co-op/randomizer use has not been validated.

The bundle also fixes complete controller layout selection after a cleared face-button binding, Scarecrow Song
timing and remapped-note recall, and floor-web reactions above 60 FPS. It includes CPU-path changes, conservative
occlusion handling and Lichii-derived shadow-map table support. See the [backport provenance](../integrations/feature-backports.md)
and [validation](longshot-validation.md); these fixes do not imply locked 60 FPS in all scenes.

## Adventure Journal: live trail, waypoints and collection counters

In the launcher, select a profile and choose **Play with journal**. It starts the game with a unique local connection
and opens the companion. Load a save, then use the journal on a second monitor or enable **Keep on top**.
**Compact** reduces it to a small live counter/area window for single-monitor play; turn it off to return to the
previous full-window size and position. Hidden trail drawing is suspended while compact; sampling continues.

- Follow the current area, child/adult state, health, rupees, Gold Skulltula count and loose heart pieces.
- See a session trail of Link's movement. This is a breadcrumb trace, **not an illustrated map or dungeon floor plan**.
  Gaps separate area changes, loading, large jumps and abrupt vertical changes; north is up. Gradual movement between
  floors can share a trail; this view does not identify dungeon floors.
- Name and **Mark shown spot** to remember a location. Select a waypoint for distance, direction and height difference.
  When paused, the explicitly labelled last position is the one marked. Disconnected games cannot add a waypoint.
- See area visits and collection-counter changes in the session feed. Unknown values remain unknown; an older save
  does not imply a new pickup. Individual collectible locations are not automatically marked from a total count.
- Close/reopen the journal while its launcher-started game keeps running. Choose **Play with journal** again to reopen
  that session. A game originally started without the journal needs a normal saved restart to enable the connection.

![Adventure Journal with real copied-save gameplay](images/longshot-adventure-journal.png)

Notes live in `<experimental game>/longshot-journal/profile-N.json`, separately from native saves. Writes use a staged
file and detect notes changed by another window. Trail and feed are bounded and session-only; reopening starts a new
trail while retaining named waypoints. Child/adult waypoints are separate. The companion only subscribes to sampled
data; it sends no game input, arbitrary memory access or save writes. Its connection is local, not a LAN web server.

The original implementation uses Python/Tk, like the existing launcher. No Atlas base code, artwork or dataset is
bundled. Atlas's README documents separate terms for those parts; see the [research correction](longshot-player-roadmap.md#atlas-boundary-discovered-during-implementation).
The native sampler must be present in the experimental executable; build fingerprint `793ee543` was tested locally.
This is functional companion validation, not evidence of a frame-rate improvement or full-game collectible accuracy.

## Live data for trackers and developer tools

The optional local control bridge now supplies sampled Link position, facing/camera direction, health, rupees,
map, age, action prompt and music through `status`. Explicit `oot` subscriptions can watch up to 64 named or hashed
game flags. Samples carry their original frame/time; paused or loading games do not manufacture fresh data.

For a game already launched with the bridge enabled, a client can request three samples with:

```powershell
python -I scripts/hookshot_ctl.py --sock longshot-tools --json watch --events oot --every 60 --flags PlayerStatus.Life --count 3
```

The socket/pipe name must match the game's `HOS_CONTROL`. See [the protocol and launch guide](control.md) for setup.
Ordinary play leaves the bridge off. Merely enabling it does not continuously scan the game; a pending status request
or due subscription is needed. Full changed-flag scanning requires the additional `--changes` option and has a
measurable cost in upstream testing, so leave that off when a few named values suffice. Reads use copied samples;
arbitrary memory access still requires its separate setting. Windows multi-client busy-pipe handling is covered too.

The Adventure Journal above consumes this interface. It is not a completed Atlas overlay, exhaustive item tracker,
or restorable world save state.
The [validation record](longshot-validation.md) distinguishes synthetic transport tests from actual game observation.

## Launcher, save imports and checkpoint browser

From this checkout, with Python and Tk installed:

```powershell
python -I scripts/longshot_launcher.py --game "<experimental game folder>"
```

The launcher selects profiles 1–9, opens the mod manager, and starts the pinned completion tracker or randomizer.
Build the tracker first using the companion instructions below. Graphics/controller options remain in the game's
Insert menu. Ordinary play disables inherited co-op and randomizer-overlay environment settings.
The launcher's explicit `--user` selection takes precedence over the in-game profile option for that launch.

**Saves & checkpoints** lists native saves in the selected profile. Save normally and close the game first:

- **Import saves:** select the source account folder containing `account.sav` and `slot_00`, `slot_01`, etc.
  This works with the same native save format used by Hookshot, NX2navi, Ocarina Recomp and the emulator forks.
  Choose an unused destination profile from 2–9 using the bottom selector. Files are bounded, staged, flushed,
  read back and verified before publication. Existing profiles, profile 1 and source saves are never overwritten.
  Linked paths and incomplete slots are refused. The separate `oot_saves.py` migration tool also recognizes
  Ocarina Recomp's Portuguese `perfil/save/<account>` layout.
- **Capture selected save:** archives that native save point under the experimental game's `longshot-checkpoints`.
- **Restore selected checkpoint:** checks its identity/payload and restores into a new profile. The retained
  `.hookshot_exefs` identifies the game; developers can supply a separate `--exefs <folder>`.

![Checkpoint captured and restored using synthetic saves](images/longshot-checkpoints.png)

These are native-save checkpoints, not snapshots of live process memory or a pause-menu quicksave feature.
The launcher does not establish arbitrary mid-combat restoration. Keep the checkpoint files local: they contain saves.
**This PC** reads CPU/RAM/GPU information and offers conservative starting points; it never changes game or Windows
settings. NVIDIA VRAM comes from `nvidia-smi` where available, avoiding Windows' truncated 4 GiB adapter field.
Advice is not a measured performance result. An optional `--romfs <folder>` lets ordinary development launches share
existing assets; companion tools expect the game folder's usual `romfs` layout.

## Save profiles and FPS counter

In **Insert → Gameplay**:

- **Save profile:** 1 keeps the existing `user` folder. Profiles 2–9 use `user/profiles/profile-2` through `profile-9`.
  Save your progress, select a profile, then restart. A new profile starts a separate playthrough; it does not copy your
  existing progress. The application’s display/controller options remain shared.
- **FPS counter size:** 50–150%, independent of the menu size. Position, graph, frame-time and other existing counter
  controls still work. The default is 100%, preserving the upstream size until you change it.

`HOS_SAVE_PROFILE=1` through `9` overrides the saved profile for one launch. An explicit `--user <folder>` takes
precedence over both: checkpoint restoration, randomizer seeds and isolated test runs retain their chosen save folders.
Invalid profiles or unusable profile directories stop startup instead of falling back to the original saves.
Directory junctions/symlinks at the newly selected profile directories are refused.

Existing checkpoint tools are preserved. This branch does **not** claim a new live-memory quicksave system or
an in-game checkpoint browser; the existing native-save checkpoint backend has its previous capabilities.

## Mod manager

From this checkout, with Python and Tk available:

```powershell
python -I scripts/longshot_mods_gui.py --mods "<experimental game folder>\mods"
```

![Longshot mod manager with synthetic test mods](images/longshot-mod-manager.png)

The window enables/disables mods, moves their priority, and identifies overlapping RomFS files and the winning mod.
It reports optional game/build manifest mismatches and warns when a mod includes unsupported ExeFS patches.
It never downloads mods, rewrites their assets, or edits saves. Changes take effect at the next game launch.

Command-line equivalents:

```powershell
python -I scripts/longshot_mods.py --mods "<folder>" list
python -I scripts/longshot_mods.py --mods "<folder>" conflicts
python -I scripts/longshot_mods.py --mods "<folder>" disable "A mod"
python -I scripts/longshot_mods.py --mods "<folder>" enable "A mod"
python -I scripts/longshot_mods.py --mods "<folder>" order "First" "Last"
```

Add `--json` before the command for structured reports. The native loader understands the manager's
`.longshot-disabled` marker and `longshot-order.txt`. Unlisted mods load alphabetically first; the last enabled layer
wins a file overlap. Existing `-`/`_` folder-name disabling still works. Directory links are not traversed.
Two mods editing different resources inside the **same archive** still conflict at the whole-file level; this manager
does not merge archives or prove that a mod is playable. `HOS_FS_OVERLAY` has precedence over all mod layers.

An optional `longshot-mod.json` beside a mod's `romfs` can contain:

```json
{
  "schema": 1,
  "title_id": "0400486024dec000",
  "build_id": "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
}
```

The manager checks this metadata before enabling/reordering. A missing manifest means compatibility is unknown.
The native loader does not independently enforce manifests placed manually. Paths must fit its existing 260-byte
UTF-8 buffers; the manager reports paths beyond that limit.

## Optional companions

Initialize the pinned sources once:

```powershell
git submodule update --init
```

`scripts/longshot_companions.py` exports the pinned sources into ignored `work/longshot-companions/` folders and applies
the recorded compatibility patches. It checks the source revision and keeps each source/patch combination in a separate
folder. Generated overlays, companion settings and randomizer saves stay local. Preserve old companion folders when
updating if they contain seeds or progress; the script does not migrate or delete them.

### Completion tracker

Requires Node.js 22.15+ or 24, npm and network access for the locked build dependencies:

```powershell
python -I scripts/longshot_companions.py build tracker
python -I scripts/longshot_companions.py test tracker
python -I scripts/longshot_companions.py launch tracker --saves "<chosen user or profile folder>"
```

Boomerang Tracker reads saves and offers completion categories, reachable-item suggestions, a compact overlay and
customizable overlay hotkeys. Longshot passes the selected save folder explicitly and gives it separate local settings.
The tracker reads saves; its manual checklist answers and settings are separate files. Some mappings are uncertain and
some locations need manual identification. Its full-game accuracy has not been established by Longshot's synthetic tests.

### Randomizer

Requires Python 3.14+ with Tk. Use a separate experimental game build:

```powershell
python -I scripts/longshot_companions.py launch randomizer --game "<experimental game folder>"
```

The companion GUI offers chest/shop shuffling, dungeon-item options, opening/cutscene skips, world-opening options,
spoiler logs and per-seed saves. It generates overlays from your own local game assets; none are included here.
It validates its patches before launch. **There is no progression-logic solver: seeds can be unbeatable.**
Longshot's launcher disables co-op for this mode; randomizer/co-op combinations are not validated. Rebuild seeds after
changing the game build, following the companion's update instructions. Add `--dry-run` to print the launch plan without opening it.

### Co-op (experimental, Windows)

The native bridge and renderer hooks are integrated. The optional module is pinned to a revision whose Hookshot pin is
the same `4aee23659b9436dab2cd7be1ac07333c06246b7c` base used here. It supports remote Link puppets, synchronization,
chat, and its own optional gameplay tools. Every machine must use compatible game/module versions and matching settings.

Build/test the module with CMake and the Visual Studio C++ tools:

```powershell
python -I scripts/longshot_companions.py build oot-coop --cmake "<path to cmake.exe>"
python -I scripts/longshot_companions.py test oot-coop --cmake "<path to cmake.exe>"
```

For a local development session:

1. Build the **whole Longshot game** from this branch, including a fresh lift. Replacing only the renderer or copying
   the DLL beside an older executable does not install the frame hooks.
2. Put the built `hookshot_coop.dll` beside the experimental **game executable** (inside `bin` when applicable).
3. Generate the puppet pack from your own local RomFS using the pinned companion's
   `tools/puppet_pack/build.py --romfs <local romfs> --mod-dir <game>/mods/contents/0400486024DEC000/coop-puppet`.
   Generated packs, shaders, HUD assets and game files must never be committed or shared.
4. Configure `coop.ini`, authentication and the server using the pinned companion's [setup guide](../integrations/oot-coop/docs/setup.md).
   Start with a password-protected local session and isolated `--user` folders. Server hosting/port forwarding is a separate explicit action.
5. The join form sets **exactly `HOS_COOP=1`** and scopes `HOS_MODS` to `<game>/mods/contents/0400486024DEC000`.
   Unset, `0`, or any other co-op opt-in value leaves the module unloaded. No server is started by
   the default game or the build command. Co-op-specific null-read/platform workarounds also stay inactive when the module is off.

The launcher now provides **Join co-op**. Put the pack at
`<executable folder>/mods/contents/0400486024DEC000/coop-puppet`, then disable it in **Manage mods**. The join form
requires profile 2–9, a host name or IPv4 address, port, player name and session password. It supplies the pack's RomFS
through the normal mod loader only for that session; HUD and room metadata remain in the module's expected location.
This preserves the resource-size-table merge required by PlayStation prompts. Ordinary play leaves the pack disabled.
Other enabled mods under that title folder can still load; do not combine a randomizer with co-op without separate testing.
The password is passed in the child process environment and is not saved by the launcher. Hosting remains a separate action.

Longshot additionally keeps the game's menus ahead of the co-op panel for mouse clicks/wheel events.
The companion's automated tests passed. A single game joined an encrypted loopback server, loaded a copied Deku Tree save,
rendered the scene, accepted movement and exited cleanly. Two-player synchronization, remote puppets and reconnect still need testing.

### Full randomizer / Archipelago tools (OoTrR)

OoTrR is an additional optional companion; it does not replace the simpler randomizer or its existing seeds.
Its newly MIT-licensed pin includes a progression-logic randomizer, save/live tracking and Archipelago tools.
Logic verification is not equivalent to completing a seed in the actual remake.

```powershell
python -I scripts/longshot_companions.py build ootrr
python -I scripts/longshot_companions.py test ootrr
python -I scripts/longshot_companions.py launch ootrr --game "<experimental game folder>"
```

Prepare a **separate built game** at `<experimental game folder>/longshot-modes/ootrr`, with its own executable,
options, caches, mods and saves. Its `longshot-mode.json` must contain `{"schema":1,"mode":"ootrr"}`. Game assets
can be shared read-only by normal play; do not run an asset-writing Builder against a shared RomFS junction.
The launcher refuses to substitute the ordinary game when this mode installation is absent. Build the dependency
environment before choosing **Full randomizer** in the launcher.

Choose your local game package in the companion. Seeds install only into this mode game's `mods` folder; its live tracker
can attach only to that mode's `hookshot.exe`. Start that dedicated executable to play a generated seed, beginning a new
playthrough as the seed requires. Your ordinary saves are not imported. The integration disables OoTrR's automatic
controller remapping to preserve existing bindings. Multiworld needs explicit server/slot setup and remains experimental;
no server connection or public hosting is started by these preparation commands.

![Configured full-randomizer companion](images/longshot-full-randomizer.png)

## Builds and updates

Use the normal [development guide](development.md) to build the game. Keep this prerelease integration separate from
the regular play installation until gameplay acceptance is complete. Existing saves/settings are not migrated by this PR.
The mod manager and companions are tools in this checkout; no new installer or desktop shortcut is implied.

No default enables frame generation or HDR here. For a system that previously showed flicker, begin testing with its known
working settings and compare the same scene before trying these features. The subsequent
[performance investigation](longshot-performance.md) records the occlusion-query backport, reduced per-draw CPU lookups,
the safeguard against isolated shader stalls selecting a heavier loading mode, controlled comparisons and
remaining limits. It does not establish sustained 60 FPS throughout the game or promote the experimental build over the
regular installation.
