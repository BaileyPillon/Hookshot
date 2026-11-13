# Longshot fork research and integration decisions

Research date: **13 November 2026**. Stars, availability and default branches are a dated snapshot, not a quality guarantee.

## Method and coverage

The survey collected **44 repository records** (41 accessible; three returned 404), including source trees, README claims,
licenses, default-head revisions, recent commits and releases. GitHub's direct fork inventories supplied **1,379 Lichii
fork records** and **274 NX2navi fork records** for candidate discovery. These are metadata inventories, not 1,653
individually audited codebases or necessarily unique projects. The table below is the reviewed shortlist, selected for
stars, active/distinct development, platform changes or noteworthy features. Source-level investigation was concentrated
on the integrations, compatibility boundaries and license questions.

Public GitHub search, surviving fork networks and relevant community links were used alongside the APIs. No relevant
repositories were found in the authenticated account's starred list. A follow-up read-only scan of six local Chromium
bookmark files and one Firefox bookmark database found no matching GitHub project bookmarks; unrelated bookmarks
and browsing history were not exported. Original Hookshot and Fritchii URLs returned 404;
that establishes availability, not the reason they disappeared. Renamed, private or unindexed forks can be missed.

The requested “frichi” and “lichi” were interpreted as **Fritchii** and **Lichii**. Hookshot is the native Switch 2 remake
recompilation. NX2navi and sostenesfreitas/ocarina-recomp also compile the Switch 2 remake natively, with different
runtimes. Lichii and the reviewed Fritchii nx2 branches are emulator lines. Shared save formats do not make their
renderers, generated code or executable patches interchangeable. An earlier version of this report incorrectly
called NX2navi an emulator and ocarina-recomp an N64 port; their own architecture/README sources establish the correction.

## Chosen implementation

| Feature family | Evidence and implementation | Current boundary |
|---|---|---|
| New renderer, input, UI and diagnostics | Exact Hookshot `4aee23659b9436dab2cd7be1ac07333c06246b7c`, release commit v2.2.0-rc.1, recovered through the surviving fork network. Merge `db7d828` retains the three Longshot checkpoint commits. | Prerelease source; no stable game deployment or measured performance improvement implied. |
| Pipeline warming / stutter reduction | Hookshot `333fa02` incorporates 11,985 pipeline descriptions from Fritchii's recipe; newer pipeline/program/memory fixes also included. | Descriptions hold state/hashes, not game shader code. Shader work is rebuilt locally; community shader blobs not imported. |
| Profile isolation | Nine-profile workflow from zelda-oot-perfis, independently implemented in `host/save_profile.c` and the native menu. | Restart required; explicit `--user` wins; no live save switching. |
| Mod manager | Independent native loader order/disable support plus CLI and Tk GUI, with conflict winner reports and optional title/build metadata. | File-level RomFS overlays only; no ExeFS or archive merging. Lichii-Enhanced's advertised manager was not real source at its reviewed revision. |
| Smaller configurable FPS display | Independent native-menu option, 50–150%, using upstream's rich FPS/frametime overlay. | No in-game measurement of the new combined renderer yet. |
| Co-op | GPL source bridge patches from the pinned oot-remake-multiplayer revision; its Hookshot base pin exactly matches this merge. | Optional, exact opt-in, fresh game lift needed; two-player gameplay acceptance pending. |
| Randomizer | Pinned MIT Hookshot Randomized companion, exported/started by Longshot's companion tool. | No progression solver; possible unbeatable seeds. No event-gift shuffle or proven co-op combination. |
| Completion tracker | Pinned MIT Boomerang companion; save-folder-aware launcher and build/test fixes. | Read-only save interpretation; uncertain mappings/manual identification remain. |
| Developer access | Upstream local control bridge, observation/bug-report tools plus retained Longshot checkpoint foundation. | Not OpenGOAL-style arbitrary hot reload or a new in-game checkpoint browser. |
| Launcher and resilient saves | Independently implemented game/profile/companion launcher, verified import into new profiles, native-save checkpoint browser and CPU/RAM/GPU advice. Mako and Ocarina Recomp migration workflows informed the design. | Original saves and existing profiles are never overwritten; advice does not automatically change settings. Not live-memory or pause-menu quicksave. |

## License and evidence findings that change the selection

- **NX2navi is not wholly MIT.** Its repository metadata reports MIT, but
  [LICENSE-ADDITIONS](https://github.com/tangerineturtle1/NX2navi/blob/5190f8e932b9/LICENSE-ADDITIONS)
  reserves later additions and requires written permission for copying/modification/distribution. No such code was
  copied, and a derivative fork is not a way around that restriction. Its descriptions informed comparison only.
  Similar DLSS/FSR/HDR/ultrawide/diagnostic features came from independently available Hookshot code instead.
- **Lichii-Enhanced is a claim, not a feature implementation, at this snapshot.** Its reviewed recursive tree contains
  only README.md and LICENSE. Stars on that repository cannot validate its advertised mod manager, setup wizard or online modes.
- **Mako's code and art have different terms.** The code is GPL-3.0, while its DoctorTwitch controller art is identified
  as CC BY-NC-ND 4.0. That art was not imported. The partial Master Quest preview is not advertised here as a complete mode.
- **An emulator patch is not necessarily a recompilation patch.** CPU/JIT/cache and ExeFS hooks need native equivalents.
  Host-profile selection and supported RomFS overlays were chosen instead of pretending an ExeFS module can be loaded here.
- **Popularity is only a discovery signal.** Star counts and community discussion do not establish save safety,
  completion, compatibility, speed or consensus. Tested source and matching revisions decide inclusion.

## Deliberately not combined in this branch

Mako's partial Master Quest content needs its own code/data/provenance review and full dungeon progression tests.
HeyListen's engine/job redesign requires a separate architectural evaluation rather than overlapping two render backends.
Android, PS5, Steam Deck, ROG Ally, BC-250, Intel Arc and AMD-specific presets are not applied to a Windows/NVIDIA PC.
Reserved/unlicensed source, distributed game-derived caches, ROM assets and restricted artwork are excluded.
No full randomizer logic solver, online matchmaking service, achievements backend, split-screen mode, arbitrary hot reload
or full-memory save-state implementation was established as a compatible, licensed drop-in feature by this research.

## Repository-by-repository record

The exact pins and machine-readable metadata are also in [longshot-fork-catalog.json](longshot-fork-catalog.json).
“Not imported” means no distinct code was ported from that candidate; overlapping work may already exist in shared upstream.
README descriptions below are discovery evidence, not independent gameplay verification.

| Repository | Stars | Reviewed revision | Finding / decision |
|---|---:|---|---|
| [BaileyPillon/Longshot](https://github.com/BaileyPillon/Longshot) | 0 | [d481e1336dfb](https://github.com/BaileyPillon/Longshot/tree/d481e1336dfb2de7cc8c255e042c7843aa0f7070) | Our fork; retained its checkpoint/devtools work and advanced the upstream base. |
| [NotRexed/Hookshot](https://github.com/NotRexed/Hookshot) | — | 404 | Original URL returned 404; recovered the exact v2.2.0-rc.1 revision through the surviving GitHub fork network. |
| [Shakoquo/Mako](https://github.com/Shakoquo/Mako) | 27 | [348436cce81b](https://github.com/Shakoquo/Mako/tree/348436cce81b3d095ab2a312a0d8e63c267778b4) | AMD/foliage fixes, hardware-aware setup, Master Quest child-dungeon preview. Hardware advice, launcher and save-import workflow independently adapted; common upstream fixes retained. Restricted controller art and partial dungeon mode not imported. |
| [madebyjordan/Longshot](https://github.com/madebyjordan/Longshot) | 2 | [01d3ee79e732](https://github.com/madebyjordan/Longshot/tree/01d3ee79e732a9978ae5a55f2953e171c1bd32bd) | Unrelated fork sharing our name; older AMD-oriented changes. Do not confuse its releases with this project. |
| [Sacrappy/HeyListen](https://github.com/Sacrappy/HeyListen) | 6 | [be8bd70948b1](https://github.com/Sacrappy/HeyListen/tree/be8bd70948b16e438a403a8a945edbce63080278) | Large host/job/render redesign. Not a small compatible feature patch; requires separate architecture and cross-GPU evaluation. |
| [RufflezAU/Hookshot](https://github.com/RufflezAU/Hookshot) | 8 | [216f7ebd5094](https://github.com/RufflezAU/Hookshot/tree/216f7ebd5094891376a3c583a86e80560d33ed53) | Deck/Linux performance work. Catalogue for that hardware; no global Windows desktop defaults imported. |
| [mihawk-99/PS5_Hookshot](https://github.com/mihawk-99/PS5_Hookshot) | — | 404 | URL returned 404; no source implementation verified or imported. |
| [TomShafford/Hookshot](https://github.com/TomShafford/Hookshot) | 8 | [7cb3bfceb81f](https://github.com/TomShafford/Hookshot/tree/7cb3bfceb81f96583521e859bd09280391b6a11d) | OoT fix branch; overlap with newer shared upstream. No duplicate cherry-picks or unmeasured defaults. |
| [evilmfkr/Evil_Hookshot](https://github.com/evilmfkr/Evil_Hookshot) | 8 | [82959d30fd98](https://github.com/evilmfkr/Evil_Hookshot/tree/82959d30fd9812005759ef30dfd2d9d7404c82c3) | Renderer/build compatibility work; shared upstream includes EvilOOT-derived build support. |
| [mooki000/hookshot-workbench](https://github.com/mooki000/hookshot-workbench) | 1 | [58ccb6e57152](https://github.com/mooki000/hookshot-workbench/tree/58ccb6e5715209aea639d721b62ab47ca4df950e) | Developer tooling concept; use the newer native control/bug-report bridge already in the upstream merge. |
| [LucieTheFool/boomerang-tracker](https://github.com/LucieTheFool/boomerang-tracker) | 0 | [0fb33437e620](https://github.com/LucieTheFool/boomerang-tracker/tree/0fb33437e620adb3d3634f28ed7650c20bb2361c) | Integrated as a pinned companion: read-only completion tracking, reachable-item suggestions, overlay and hotkeys; build/test fixes recorded. |
| [Mozencaz/OotrR](https://github.com/Mozencaz/OotrR) | 4 | [ddf9a98d986f](https://github.com/Mozencaz/OotrR/tree/ddf9a98d986fbdff36305b5b1f03c5a26207b46d) | Randomizer candidate with no verified license grant; no source copied. |
| [Smeef123/OoTRemakeRando](https://github.com/Smeef123/OoTRemakeRando) | 3 | [b6b85b4303f2](https://github.com/Smeef123/OoTRemakeRando/tree/b6b85b4303f29e562b0bb4fc09752f01792e845e) | Randomizer candidate, unclear license metadata; chose the explicitly MIT Hookshot-specific implementation instead. |
| [KAMOX06/hookshot-randomized](https://github.com/KAMOX06/hookshot-randomized) | 2 | [91f301987e8f](https://github.com/KAMOX06/hookshot-randomized/tree/91f301987e8f67b5239bb22429137077a1e330d0) | Integrated as pinned companion: chest/shop shuffle, skips, world-opening options, spoiler log and seed-specific saves. No progression solver. |
| [daurosk/oot-remake-multiplayer](https://github.com/daurosk/oot-remake-multiplayer) | 93 | [f5e4ca3b4071](https://github.com/daurosk/oot-remake-multiplayer/tree/f5e4ca3b407197349af3045abff4bb7475ac2fd8) | Integrated exact-base GPL bridge and pinned module; opt-in co-op, remote puppets, sync and chat. Automated tests, not two-player gameplay, verified here. |
| [ZuanCrisp/Fritchii](https://github.com/ZuanCrisp/Fritchii) | 7 | [7aeddb77aa41](https://github.com/ZuanCrisp/Fritchii/tree/7aeddb77aa41cbb32888c8b726d20fd0e16ff192) | Surviving mirror/release history; default nx2 is emulator code. Fritchii pipeline preparation is incorporated through the matching Hookshot upstream change. |
| [Benjaminvdw/Fritchii](https://github.com/Benjaminvdw/Fritchii) | 16 | [ef3679e93fac](https://github.com/Benjaminvdw/Fritchii/tree/ef3679e93fac5954ac6ea4476e495b65c2e36d2a) | Linux AppImage packaging candidate; newer Hookshot already has its own Linux packaging, not merged wholesale. |
| [giangero1/Fritchii-ZeroStutter](https://github.com/giangero1/Fritchii-ZeroStutter) | 2 | [85c513f2e609](https://github.com/giangero1/Fritchii-ZeroStutter/tree/85c513f2e609a7a4c7faff9ee93732cf9ee4b659) | Shader/preparation claims; use compatible Hookshot pipeline-state recipes and local compilation, not shared game-derived shader blobs. |
| [byronlai99/Fritchii-HDrum](https://github.com/byronlai99/Fritchii-HDrum) | 1 | [d4fa6f74a20f](https://github.com/byronlai99/Fritchii-HDrum/tree/d4fa6f74a20fc1e4737cb708ff950ca58e0504fe) | Fritchii language/distribution variation; source-localized Hookshot menus already incorporated. |
| [juvxncio/zelda-oot-perfis](https://github.com/juvxncio/zelda-oot-perfis) | 1 | [0e59f3c0e258](https://github.com/juvxncio/zelda-oot-perfis/tree/0e59f3c0e258cc50495d6796a6efae1f6846df53) | Nine-profile workflow adapted independently in the native host. Its emulator ExeFS module is not copied into the recompilation. |
| [zortos293/Lichii](https://github.com/zortos293/Lichii) | 8904 | [87d84d513c67](https://github.com/zortos293/Lichii/tree/87d84d513c67275ad0d6ae50ba51cce76e7e3ded) | Popular emulator foundation. Useful compatibility reference, not a native Hookshot subsystem to merge. |
| [Manaclenodisconnect/Lichii-Enhanced](https://github.com/Manaclenodisconnect/Lichii-Enhanced) | 277 | [bfe1a537fd9d](https://github.com/Manaclenodisconnect/Lichii-Enhanced/tree/bfe1a537fd9dac106d799917e8598b70353bce25) | Only README and LICENSE in the reviewed tree. Advertised manager/wizard/online functions are not an implementation; mod-management idea independently implemented. |
| [Shakoquo/Lichii-sharkiix-version](https://github.com/Shakoquo/Lichii-sharkiix-version) | 88 | [4243c082f593](https://github.com/Shakoquo/Lichii-sharkiix-version/tree/4243c082f59330b31686cb0e8b35ed82756f7ee0) | AMD-oriented emulator fork and lineage of Mako; avoid emulator GPU implementation in the native renderer. |
| [CheezerWheezer/Lichii](https://github.com/CheezerWheezer/Lichii) | 56 | [a8e84764e45e](https://github.com/CheezerWheezer/Lichii/tree/a8e84764e45e6b6a6615f7f26cc525e74f69a7a1) | AMD-superior branch; hardware-specific emulator tuning, not a general Longshot default. |
| [K-code-AI/Greenhat-Lichii](https://github.com/K-code-AI/Greenhat-Lichii) | 52 | [4307d3246b23](https://github.com/K-code-AI/Greenhat-Lichii/tree/4307d3246b239e5bfe4e4989f3eeaadb139f59c7) | Emulator fork/customizations; use the native Longshot manager and upstream diagnostics instead of merging another emulator. |
| [Syyrhc/Lichii-Ally](https://github.com/Syyrhc/Lichii-Ally) | 30 | [6d20d651a216](https://github.com/Syyrhc/Lichii-Ally/tree/6d20d651a2165b3c6408c7a6b2223c3464f79dcf) | ROG Ally/handheld focus. No desktop-wide power, resolution or memory presets imported. |
| [oceanpacificpeace/lichii-shader-sync](https://github.com/oceanpacificpeace/lichii-shader-sync) | 336 | [9a8bf8cf707b](https://github.com/oceanpacificpeace/lichii-shader-sync/tree/9a8bf8cf707b49f5f10ee283a62cfdb5103ccb78) | Shader-sync utility. Do not import/download community game-derived cache payloads; use locally rebuilt pipeline recipes. |
| [mja00/Lichii](https://github.com/mja00/Lichii) | 21 | [043d5296390e](https://github.com/mja00/Lichii/tree/043d5296390efadb865c4a57066ba9d4c59f9840) | OoT emulator compatibility branch; source/commit comparison reference, no emulator core transplant. |
| [tangerineturtle1/NX2navi](https://github.com/tangerineturtle1/NX2navi) | 3755 | [5190f8e932b9](https://github.com/tangerineturtle1/NX2navi/tree/5190f8e932b92cf694d9f8b5a7ef6e52c141de2a) | Research-only: LICENSE-ADDITIONS reserves new code despite MIT metadata. Independent/upstream analogues cover graphics/UI features; no reserved additions copied. |
| [loteran/NX2navi](https://github.com/loteran/NX2navi) | 12 | [1ab1e001985a](https://github.com/loteran/NX2navi/tree/1ab1e001985a333ab7e31217ba8810a3c521d3af) | Linux packaging fork; inherits the NX2navi licensing boundary. Not imported. |
| [ZuanCrisp/NX2Navi-Zelda-OOT-Port](https://github.com/ZuanCrisp/NX2Navi-Zelda-OOT-Port) | 9 | [53523106136d](https://github.com/ZuanCrisp/NX2Navi-Zelda-OOT-Port/tree/53523106136dd7eaa94f5e2e0f8965c064eca2d1) | NX2navi derivative; not treated as a separate native recompilation or a license workaround. |
| [prop11/Epona](https://github.com/prop11/Epona) | 0 | [f5da269add5c](https://github.com/prop11/Epona/tree/f5da269add5c8040d4f6c6aeb7f811cd08125f3c) | NX2navi derivative; no reserved additions imported. |
| [suvrathkesaraju-lgtm/Penguin-NX2navi](https://github.com/suvrathkesaraju-lgtm/Penguin-NX2navi) | 2 | [262c13979e15](https://github.com/suvrathkesaraju-lgtm/Penguin-NX2navi/tree/262c13979e15044effd2c5b27576e82678114d5c) | NX2navi Linux derivative; no reserved additions imported. |
| [sostenesfreitas/ocarina-recomp](https://github.com/sostenesfreitas/ocarina-recomp) | 1175 | [406b3ae0321e](https://github.com/sostenesfreitas/ocarina-recomp/tree/406b3ae0321eff8dd083a607a8186aa56b52b873) | Native Switch 2 remake recompilation (GPL-3.0), with a different runtime. The maintainer now directs players and fixes toward Hookshot. Shared native saves and migration tools inform Longshot save import; not an N64 port. |
| [pavelgajdo/Hokkaido](https://github.com/pavelgajdo/Hokkaido) | 242 | [32c4089558e2](https://github.com/pavelgajdo/Hokkaido/tree/32c4089558e25395aa026c594f2b70e5773360b1) | Android-focused emulator fork. Platform port is outside this Windows native integration. |
| [xTopher1049/Tuxchii](https://github.com/xTopher1049/Tuxchii) | 78 | [e3d621cc75e9](https://github.com/xTopher1049/Tuxchii/tree/e3d621cc75e9101ea16f74216caa4296efc5f99d) | Linux-oriented emulator fork. Keep Hookshot's native Linux implementation instead. |
| [conongnang/Lichii](https://github.com/conongnang/Lichii) | 13 | [79f33200cf6c](https://github.com/conongnang/Lichii/tree/79f33200cf6c7c5aa506170a4fb17662bcdf8318) | OoT/AMD performance branch; no unsupported assumptions about NVIDIA or native-host parity. |
| [skolvolt/Lichii](https://github.com/skolvolt/Lichii) | 5 | [c0b50af5cc72](https://github.com/skolvolt/Lichii/tree/c0b50af5cc72049bca74a09f08868e2ce3d1f810) | Skitchii/OoT emulator branch; catalogue candidate, not transplanted. |
| [lethevimlet/lichii-bc250](https://github.com/lethevimlet/lichii-bc250) | 17 | [811a3d22d3f1](https://github.com/lethevimlet/lichii-bc250/tree/811a3d22d3f12ff880fc6bbc39a45d871ade5596) | BC-250-specific tuning; does not apply to the target NVIDIA desktop. |
| [Unfixedeward/Lichii](https://github.com/Unfixedeward/Lichii) | 2 | [b3a82f93f373](https://github.com/Unfixedeward/Lichii/tree/b3a82f93f373099cae4e51d4dfce5cb72ac9f26a) | Intel Arc-specific emulator work; separate hardware validation required. |
| [nauxph/Lichii-AMD](https://github.com/nauxph/Lichii-AMD) | 2 | [1779779ccdbe](https://github.com/nauxph/Lichii-AMD/tree/1779779ccdbe20d0afbde2e5fb733e195593a647) | AMD emulator work; separate implementation/measurement required in native Hookshot. |
| [kanade333/Zakantine](https://github.com/kanade333/Zakantine) | 3 | [a612e1dbe3f0](https://github.com/kanade333/Zakantine/tree/a612e1dbe3f06d6c07cffebdc47e1307f257acf6) | Lichii/nx2 derivative; no distinct tested native integration selected. |
| [JimerSamuel/Fritchii](https://github.com/JimerSamuel/Fritchii) | 1 | [9a2124404816](https://github.com/JimerSamuel/Fritchii/tree/9a2124404816de459aa305de1732794cd1520853) | Arc B580-focused Fritchii branch; not a general desktop preset. |
| [Frizti/Fritchii](https://github.com/Frizti/Fritchii) | — | 404 | Original URL returned 404. Surviving mirrors and shared Hookshot pipeline-source provenance used instead. |

## Verification and follow-up

See [feature usage](longshot-features.md), [source/patch provenance](../integrations/README.md) and
[the validation record](longshot-validation.md). Automated checks and compilation are separate from game acceptance.
The regular play installation, saves and display settings were not replaced by this integration.
