"""Archive an OoT native save slot and resume it in a separate Hookshot profile.

SPDX-License-Identifier: GPL-3.0-or-later
Save normally in OoT and exit before capture. Resume stages an isolated save
folder and starts the game's own loader. The checkpoint contains the native
save point, including persisted progress, rather than live process memory.
"""
import argparse
import base64
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I
from hookshot_checkpoint import CheckpointError, Identity
from hookshot_statefile import SaveBinding, choose_restore, read_state, write_state
from oot_saves import TITLE, data_home, running_games

PROVIDER = "hookshot.oot-native-slot"
SCHEMA = 1
PROGRAM = TITLE.lower()
ACCOUNT_FILES = {"account.sav": 128 * 1024, "option.sav": 256 * 1024}
SLOT_FILES = {"caption.sav": 512 * 1024, "progress.sav": 1024 * 1024}
REQUIRED = {"account.sav", *SLOT_FILES}


def normal_path(path, *, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise CheckpointError(f"checkpoint source must be a regular path: {path}")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise CheckpointError(f"unexpected checkpoint source type: {path}")
    return info


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def game_executable(game):
    names = ("bin/hookshot.exe", "hookshot.exe") if os.name == "nt" else ("bin/hookshot", "hookshot")
    for name in names:
        path = game / name
        if path.is_file():
            return path
    raise CheckpointError(f"Hookshot executable not found under {game}")


def raise_walk_error(error):
    raise error


def mods_fingerprint(game):
    # The launcher inherits these settings. Match both the overlay and the mod tree.
    # Hookshot's env-file parser excludes both path-valued switches.
    mods = os.environ.get("HOS_MODS", str(game / "mods"))
    overlay = os.environ.get("HOS_FS_OVERLAY")
    digest = hashlib.sha256()
    for kind, name in (("mods", mods), ("overlay", overlay)):
        digest.update(kind.encode("ascii") + b"\0")
        if not name:
            continue
        root = Path(name)
        if not root.is_absolute():
            root = game / root
        if not root.exists():
            continue
        normal_path(root, directory=True)
        for folder, dirs, files in os.walk(root, onerror=raise_walk_error):
            dirs.sort()
            for name in dirs:
                normal_path(Path(folder) / name, directory=True)
            for name in sorted(files):
                path = Path(folder) / name
                normal_path(path)
                digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
                digest.update(bytes.fromhex(fingerprint(path)))
    return digest.hexdigest()


def game_identity(game, exefs=None):
    exe = game_executable(game)
    source = exefs if exefs is not None else game / ".hookshot_exefs"
    with (source / "main").open("rb") as stream:
        header = stream.read(0x60)
    if len(header) != 0x60 or header[:4] != b"NSO0":
        raise CheckpointError("expected the builder's unpacked main NSO to identify the game build")
    # Check the title ID in the same ExeFS. NPDM's ACI0 contains the ProgramId.
    with (source / "main.npdm").open("rb") as stream:
        npdm = stream.read(64 * 1024 + 1)
    if not 0x80 <= len(npdm) <= 64 * 1024 or npdm[:4] != b"META":
        raise CheckpointError("invalid main.npdm")
    aci = int.from_bytes(npdm[0x70:0x74], "little")
    if aci < 0x80 or aci + 0x18 > len(npdm) or npdm[aci:aci + 4] != b"ACI0" \
            or int.from_bytes(npdm[aci + 0x10:aci + 0x18], "little") != int(PROGRAM, 16):
        raise CheckpointError("the ExeFS is not the supported OoT title")
    exe_hash = fingerprint(exe)
    image_hash = bytes.fromhex(fingerprint(game / "image.bin"))
    configuration = hashlib.sha256(b"hookshot.oot-native-slot:1\0" + image_hash).hexdigest()
    identity = Identity(PROGRAM, header[0x40:0x60].rstrip(b"\0").hex(), "native-" + exe_hash[:12],
                        exe_hash, sys.platform + "-" + platform.machine().lower(), 1,
                        mods_fingerprint(game), configuration)
    identity.validate()
    return identity


def slot_name(value):
    if re.fullmatch(r"[0-9]{1,2}", value) is None or not 0 <= int(value) <= 11:
        raise CheckpointError("slot must be a native slot number from 0 to 11")
    return f"slot_{int(value):02d}"


def profile_name(value):
    if re.fullmatch(r"[0-9a-fA-F]{32}", value) is None:
        raise CheckpointError("profile must be the 32-digit ID under user/save")
    return value.lower()


def stat_key(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def native_slots(user):
    save = user / "save"
    normal_path(user, directory=True)
    normal_path(save, directory=True)
    result = {}
    for root in sorted(save.iterdir()):
        if re.fullmatch(r"[0-9a-f]{32}", root.name) is None or not root.is_dir():
            continue
        normal_path(root, directory=True)
        if not (root / "account.sav").is_file():
            continue
        slots = []
        for index in range(12):
            slot = f"slot_{index:02d}"
            folder = root / slot
            if all((folder / name).is_file() for name in SLOT_FILES):
                normal_path(folder, directory=True)
                progress = normal_path(folder / "progress.sav")
                caption = normal_path(folder / "caption.sav")
                if progress.st_size and caption.st_size:
                    slots.append((progress.st_mtime_ns, caption.st_mtime_ns, slot))
        if slots:
            result[root.name] = [slot for _, _, slot in sorted(slots, reverse=True)]
    return result


def read_slot(user, profile, slot):
    root = user / "save" / profile
    for directory in (user, user / "save", root, root / slot):
        normal_path(directory, directory=True)
    files = {name: (root / name, limit) for name, limit in ACCOUNT_FILES.items()}
    files.update({name: (root / slot / name, limit) for name, limit in SLOT_FILES.items()})
    if not (root / "option.sav").exists():
        del files["option.sav"]
    before = {name: stat_key(normal_path(path)) for name, (path, _) in files.items()}
    data = {}
    for name, (path, limit) in files.items():
        with path.open("rb") as stream:
            if stat_key(os.fstat(stream.fileno())) != before[name]:
                raise CheckpointError("save changed during capture")
            content = stream.read(limit + 1)
        if not content or len(content) > limit:
            raise CheckpointError(f"{name} is empty or exceeds its bound")
        data[name] = content
    if any(stat_key(normal_path(path)) != before[name] for name, (path, _) in files.items()):
        raise CheckpointError("save changed during capture")
    return data


def capture(game, user, profile, slot, output, *, exefs=None):
    active = running_games()
    if active:
        raise CheckpointError("finish saving and close the running game before capture: " + ", ".join(active))
    if profile is None or slot is None:
        slots = native_slots(user)
        if profile is None:
            if len(slots) != 1:
                raise CheckpointError("choose a profile from the slots command")
            profile = next(iter(slots))
        if slot is None:
            matches = slots.get(profile_name(profile))
            if not matches:
                raise CheckpointError("the selected profile has no complete native saves")
            slot = matches[0][5:]
    profile, slot = profile_name(profile), slot_name(slot)
    identity = game_identity(game, exefs)
    files = read_slot(user, profile, slot)
    binding = SaveBinding(profile, PROGRAM, slot)
    portable = {"files": {name: base64.b64encode(data).decode("ascii") for name, data in files.items()}}
    write_state(output, identity=identity, provider=PROVIDER, provider_schema=SCHEMA,
                binding=binding, portable=portable)
    return binding


def validated_files(info):
    if set(info.portable) != {"files"} or not isinstance(info.portable["files"], dict):
        raise CheckpointError("invalid native save payload")
    files = info.portable["files"]
    limits = ACCOUNT_FILES | SLOT_FILES
    if not REQUIRED <= files.keys() <= limits.keys():
        raise CheckpointError("native save payload has missing or unknown files")
    data = {}
    for name, encoded in files.items():
        limit = limits[name]
        if not isinstance(encoded, str) or len(encoded) > 4 * ((limit + 2) // 3):
            raise CheckpointError(f"invalid native save length for {name}")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise CheckpointError(f"invalid native save encoding for {name}") from error
        if not content or len(content) > limit:
            raise CheckpointError(f"invalid native save length for {name}")
        data[name] = content
    return data


def prepare(game, checkpoint, destination, *, exefs=None, profile=None, slot=None):
    info = read_state(checkpoint)
    identity = game_identity(game, exefs)
    saved = info.binding
    if saved.save_data != PROGRAM or saved.profile != profile_name(saved.profile) \
            or not re.fullmatch(r"slot_[0-9]{2}", saved.slot) or saved.slot != slot_name(saved.slot[5:]):
        raise CheckpointError("invalid native OoT save binding")
    requested = SaveBinding(profile_name(profile) if profile is not None else saved.profile, PROGRAM,
                            slot_name(slot) if slot is not None else saved.slot)
    plan = choose_restore(info, identity, binding=requested, portable_providers={PROVIDER: SCHEMA})
    if plan.mode != "portable":
        raise CheckpointError(plan.reason)
    data = validated_files(info)

    # Reserve a new --user folder. The game sees no save tree until the complete
    # staged tree has been written and verified. Never overwrite an existing one.
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix=".checkpoint-", dir=destination) as temporary:
            staged = Path(temporary) / "save"
            root = staged / saved.profile
            (root / saved.slot).mkdir(parents=True)
            for name, content in data.items():
                path = (root / saved.slot if name in SLOT_FILES else root) / name
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.read_bytes() != content:
                    raise CheckpointError(f"read-back verification failed for {name}")
            staged.rename(destination / "save")
    except BaseException:
        if not (destination / "save").exists():
            try:
                destination.rmdir()
            except OSError:
                pass
        raise
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="Hookshot game folder")
    parser.add_argument("--exefs", type=Path, help="unpacked ExeFS if outside the builder's game folder")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("slots", help="list native save slots, most recent first")
    listing.add_argument("--user", type=Path, help="native data folder")
    save = commands.add_parser("capture", help="archive a native save after the game has exited")
    save.add_argument("--user", type=Path, help="native data folder (GAME/user on Windows or the XDG Hookshot folder)")
    save.add_argument("--profile", help="required when more than one profile has saves")
    save.add_argument("--slot", help="native slot number, defaults to the most recent save")
    save.add_argument("--out", required=True, type=Path)
    for name in ("prepare", "resume"):
        load = commands.add_parser(name, help="stage a new save folder" + (" and launch Hookshot" if name == "resume" else ""))
        load.add_argument("checkpoint", type=Path)
        load.add_argument("--new-user", required=True, type=Path)
        load.add_argument("--profile", help="require this originating profile")
        load.add_argument("--slot", help="require this originating slot")
        if name == "resume":
            load.add_argument("--romfs", type=Path, help="game assets, defaults to GAME/romfs")
    args = parser.parse_args(argv)
    try:
        game = args.game.resolve(strict=True)
        default_user = game / "user" if os.name == "nt" else Path(data_home()) / "hookshot"
        if args.command == "slots":
            for profile, slots in native_slots(args.user or default_user).items():
                print(f"{profile}  {' '.join(slots)}")
            return 0
        if args.command == "capture":
            output = args.out.absolute()
            if output.suffix.lower() != ".hsc":
                raise CheckpointError("checkpoint output must end in .hsc")
            binding = capture(game, args.user or default_user, args.profile, args.slot, output, exefs=args.exefs)
            print(f"Captured {binding.slot} to {output}")
            return 0
        destination = args.new_user.absolute()
        if args.command == "resume":
            exe = game_executable(game)
            image = (game / "image.bin").resolve(strict=True)
            romfs = (args.romfs or game / "romfs").resolve(strict=True)
            if not image.is_file() or not romfs.is_dir():
                raise CheckpointError("Hookshot needs image.bin and a ROMFS directory")
        binding = prepare(game, args.checkpoint, destination, exefs=args.exefs, profile=args.profile, slot=args.slot)
        print(f"Prepared {binding.slot} in {destination}", flush=True)
        if args.command == "resume":
            print("Choose Continue to resume the staged save.", flush=True)
            return subprocess.run([str(exe), str(image), "--romfs", str(romfs), "--user", str(destination)], cwd=game).returncode
        return 0
    except (CheckpointError, OSError) as error:
        print(f"oot-checkpoints: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
