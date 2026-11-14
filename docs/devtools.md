# Experimental developer tools and checkpoint roadmap

This fork starts three related projects: resilient checkpoints, live development tools,
and documented mod interfaces. The live feed is read-only; checkpoint storage and
a native restore coordinator are implemented separately. An OoT capture/restore
backend is not enabled. The code does not change the renderer or load plugins automatically.
The normal game remains unchanged unless `HOS_DEVTOOLS=1` is explicitly set.

## What is implemented

- `host/devtools.h`: observer SDK ABI 1, with structure sizes, capability negotiation,
  bounded registration, copied identifiers, and callbacks over copied player observations.
- `host/devtools.c`: validation, re-entrancy rejection, UTF-8 JSON transport, and a
  maximum two log records per second. Observers receive each successful player sample;
  the samples are **not** a presentation-frame counter.
- `host/hos_main.c`: an observation in the existing serialized player-update hook.
  It reads scene and player position on the guest update path. The GPU replay and
  external inspector never read live guest memory.
- `scripts/hookshot_dev.py`: live inspection, bounded log reading, and observation
  export. It exposes no listener, arbitrary evaluator, or guest-memory write command.
- `scripts/hookshot_checkpoint.py`: the legacy schema-1 envelope, still readable for
  inspection; restore plans reject its missing save binding/runtime evidence.
- `scripts/hookshot_statefile.py`: streamed schema-2 checkpoints, exact/portable
  preflight, native save binding, corruption fallback and an atomic background writer.
- `host/checkpoint.c`: a native restore transaction coordinator with held-boundary
  requirements, bounded retries, fresh-scene enforcement, rollback and recovery states.
  See [the Sunshine adaptation](sunshine-checkpoints.md) for the protocol and missing backend.

The code is a development foundation, not a ready-to-install save-state feature.

## Try the live console in a developer build

Build this branch normally. The standalone builder discovers `host/devtools.c`
with the other host sources; no new library is required. For that run only:

```powershell
$env:HOS_DEVTOOLS = '1'
& 'C:\path\to\game\hookshot.exe'
```

Enter gameplay, then use a separate terminal:

```powershell
python -I scripts/hookshot_dev.py status --log 'C:\path\to\game\hookshot_log.txt'
python -I scripts/hookshot_dev.py watch --log 'C:\path\to\game\hookshot_log.txt'
python -I scripts/hookshot_dev.py sample --log 'C:\path\to\game\hookshot_log.txt' --out work/player.hos-observation.json
```

If the game is launched from a terminal its normal log may go there instead of the
log file; redirect its output to a local file and point the console there. Inspect
only a developer run's log, not an older installed build's log. `status` reports the
last complete observation, which may be stale if gameplay has stopped. The record
has monotonic time and a sequence number; it is not a proof the game is still running.

`sample` preserves an existing destination. An observation contains scene/position
and identity information, **not inventory, quest flags or the state of the world**.
It cannot be loaded as a save. Exports and checkpoints are local data and ignored by
Git when named `*.hos-observation.json` and `*.hsc`.

## Observer SDK contract

Include `host/devtools.h`. Set `struct_size`, `abi_version`, and required capabilities
in `HosDevObserverV1`; register after `hos_dev_init` and before guest threads start.
`examples/devtools/observer.c` is a compilable example, not enabled in normal builds.

ABI 1 grants only `HOS_DEV_CAP_PLAYER_SAMPLE`. An unknown ABI or capability is refused.
IDs are copied, unique ASCII names, at most 63 bytes. User data and callbacks must
remain valid until shutdown. Registration, publication and inspection require the
caller's serialization; arbitrary worker-thread calls are unsupported. Callbacks run
synchronously in the serialized guest update, so they must not block, do file I/O,
call guest functions, or throw through C. Re-entrant registration/publication/reset
is refused. Each callback receives a separate copy and may inspect the latest sample.

This is a source-linked observer interface, **not a sandbox or a DLL hot-loader**.
It does not yet offer the mutating gameplay events needed for complete new game modes.
The host/renderer `MkwVkHost` interface is unchanged; this SDK has a separate ABI.

Log wire schema 1 uses `devtools-v1 ` followed by one JSON object. Position is three
IEEE-754 binary32 bit patterns (`position_bits`); the Python client also displays
decoded numbers. Integers avoid locale-dependent decimal formatting. UTF-8 strings
are validated and escaped. Unsupported/overlong/non-finite samples are rejected;
partially formatted records are never emitted.

## Checkpoints and compatibility

[sunshine-checkpoints.md](sunshine-checkpoints.md) documents the implemented
two-path adaptation, the streamed file format and the native transaction contract.
Schema 2 adds originating save binding and exact runtime signatures; schema 1 remains
inspection-only. The developer console recognizes both formats:

```text
python -I scripts/hookshot_dev.py checkpoint-inspect work/synthetic.hsc
```

Preflight selects exact only with a matching binary, mapping, memory layout,
scheduler/continuation and resource signatures plus an explicit provider. Otherwise
it may select an explicitly registered portable provider; different game/build,
mod/configuration or native-save identities reject. It never turns an observation
into gameplay progress. Actual application still requires an OoT backend and held
runtime barriers; neither a matching file nor a player-update lock supplies those.

## Next milestones and acceptance gates

| Milestone | Work | Required evidence |
| --- | --- | --- |
| Portable resume | Version-specific provider for scene, age, pose, health and progress; stage transition through game functions | Separate test saves, rollback on rejected data, repeated level changes, save/reload verification |
| Runtime commands | Bounded typed command queue; apply on a verified guest boundary, acknowledgements and capability checks | Ordering, cancellation, stale-session rejection and no operations from the inspector thread |
| New game modes | Explicit mod initialization, scene/item/interaction events, manifests and conflict/version checks | One example challenge mode, deterministic dispatch and disabled-mod behavior |
| Live reload | Replace observer code/data only at a quiescent lifecycle boundary | Unload ownership, callback lifetime and rollback on failed reload |
| Exact snapshots | Quiesce guest workers/fibers, drain capture/replay queues, handle audio/files, recreate resources and invalidate caches | Controlled end-to-end restore across GPU/audio activity; same-build identity enforcement |

A serialized player update is **not** a global safe point. Hookshot has native thread
stacks, OS handles, captured GPU work and external resources. Copying its guest heap
alone cannot safely restore a session. The Sunshine design is inspiration; none of
its code or state layouts are copied here. OpenGOAL-style arbitrary live evaluation
also requires a deliberately designed boundary, not an unrestricted memory console.

## Validation

```text
python -I -B tests/test_devtools.py --cxx clang++
python -I -B tests/test_checkpoint_envelope.py
python -I -B tests/test_checkpoint_statefile.py
python -I -B tests/test_checkpoint_coordinator.py --cxx clang++
python -I -B tests/run_all.py
```

Fixtures use synthetic samples and payloads, not game data. Test results establish
SDK/transport/format behavior; they do not establish gameplay capture/restore safety.
The `Checkpoints and developer tools` workflow runs these focused tests on Ubuntu and
Windows with Python 3.12. The existing source-regression workflow also discovers them.

Initial foundation validation on 2026-11-10 (upstream base `d481e13`, Windows, Python 3.14.7,
llvm-mingw): the observer/CLI check and 12 checkpoint checks passed. Both modified
runtime translation units compiled with the native build's target/include options.
The complete game-free suite reported 286 passed, 2 failed and 21 skipped; both
failures reproduce on an untouched archive of that upstream commit:

- `nx2/test_nup_out_of_space.py`: Windows extended-path prefix differs in a fixture.
- `tests/test_precompile_compute_guard.py`: its forced MSVC target cannot find
  `windows.h` in this llvm-mingw environment.

No gameplay build or capture/restore runtime test has been performed for this branch.
