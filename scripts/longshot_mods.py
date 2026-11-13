"""Manage Longshot's RomFS layers. Changes apply on the next game launch.

No mod files are moved or rewritten. Disabled layers have a .longshot-disabled
marker; longshot-order.txt lists enabled priorities from first to last (winner).
The base game, checkpoints and ExeFS are never modified.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile

TITLE = "0400486024dec000"
BUILD = "e0f3ccfaf50065ae4ea01eb5aeb13b1a45da3348"
MARKER = ".longshot-disabled"
ORDER = "longshot-order.txt"


def key(name):
    # The runtime's C-locale _stricmp/lower_slash folds ASCII bytes, not Unicode.
    return name.replace("\\", "/").encode("utf-8").lower()


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def plain(path):
    if linked(path):
        raise ValueError(f"Linked path is not managed: {path}")
    return path


def unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate manifest key: {name}")
        result[name] = value
    return result


def read_order(root):
    path = root / ORDER
    if not path.exists():
        return []
    plain(path)
    if path.stat().st_size > 256 * 1024:
        raise ValueError("Mod order file is too large")
    return [line.replace("\\", "/") for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")]


def manifest_errors(folder):
    path = folder / "longshot-mod.json"
    if not path.exists():
        return []
    try:
        plain(path)
        if path.stat().st_size > 65536:
            raise ValueError("Manifest exceeds 64 KiB")
        meta = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if not isinstance(meta, dict):
            raise ValueError("Manifest must be a JSON object")
        if meta.get("title_id", TITLE).lower() != TITLE:
            raise ValueError("Manifest targets a different game")
        if meta.get("build_id", BUILD).lower() != BUILD:
            raise ValueError("Manifest targets a different game build")
        if type(meta.get("schema", 1)) is not int or meta.get("schema", 1) != 1:
            raise ValueError("Unsupported manifest schema")
        return []
    except (OSError, ValueError, AttributeError) as error:
        return [str(error)]


def scan(root):
    root = plain(Path(root).absolute())
    if not root.is_dir():
        raise ValueError(f"Mods folder does not exist: {root}")
    layers = []

    def discover(folder, depth, inherited_off=False):
        if linked(folder):
            return
        off = inherited_off or (folder / MARKER).exists()
        if depth and ((folder / "romfs").exists() or (folder / "exefs").exists()):
            name = folder.relative_to(root).as_posix()
            errors = manifest_errors(folder)
            if len(str(folder).encode("utf-8")) + 12 >= 260:
                errors.append("Folder exceeds the native loader's path limit")
            if any(ch in name for ch in "\r\n\t") or name.startswith("#"):
                errors.append("Folder name cannot be represented in the order file")
            files = []
            romfs = folder / "romfs"
            if romfs.is_dir() and not linked(romfs):
                for directory, dirs, names in os.walk(romfs, followlinks=False):
                    current = Path(directory)
                    depth_here = len(current.relative_to(romfs).parts)
                    dirs[:] = [d for d in dirs if not linked(current / d)] if depth_here < 32 else []
                    for filename in names:
                        p = current / filename
                        if len(str(p).encode("utf-8")) >= 260:
                            errors.append(f"File exceeds the native loader's path limit: {filename}")
                        files.append(p.relative_to(romfs).as_posix())
            if len({key(p) for p in files}) != len(files):
                errors.append("Two file paths collide in the native loader; rename them before enabling")
            layers.append({"name": name, "enabled": not off, "files": sorted(files, key=key),
                           "exefs_unsupported": (folder / "exefs").exists(), "errors": errors})
            return
        if depth >= 4:
            return
        for child in sorted(folder.iterdir(), key=lambda p: key(p.name)):
            if child.is_dir() and not child.name.startswith(".") and not linked(child):
                discover(child, depth + 1, off or child.name.startswith(("-", "_")))

    discover(root, 0)
    names = [key(layer["name"]) for layer in layers]
    if len(set(names)) != len(names):
        raise ValueError("Two mod folder names collide in the native loader")
    ranks = {key(name): i for i, name in enumerate(read_order(root))}
    return sorted(layers, key=lambda m: (ranks.get(key(m["name"]), -1), key(m["name"])))


def conflicts(layers):
    owners = {}
    spellings = {}
    for layer in layers:
        if not layer["enabled"]:
            continue
        for path in layer["files"]:
            k = key(path)
            owners.setdefault(k, []).append(layer["name"])
            spellings[k] = path
    return [{"path": spellings[k], "layers": names, "winner": names[-1]}
            for k, names in sorted(owners.items()) if len(names) > 1]


def atomic_text(path, text):
    if path.exists():
        plain(path)
    fd, temporary = tempfile.mkstemp(prefix=".longshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def set_enabled(root, name, enabled):
    root = Path(root).absolute()
    layers = scan(root)
    selected = next((m for m in layers if m["name"] == name), None)
    if selected is None:
        raise ValueError(f"Unknown mod: {name}")
    if enabled and selected["errors"]:
        raise ValueError("; ".join(selected["errors"]))
    folder = root / name
    if enabled and any(p.startswith(("-", "_")) for p in Path(name).parts):
        raise ValueError("This folder is disabled by its name; rename it yourself before enabling it")
    if enabled:
        for parent in folder.parents:
            if parent == root.parent:
                break
            if (parent / MARKER).exists():
                raise ValueError("An enclosing folder is disabled")
    marker = folder / MARKER
    if enabled:
        if marker.exists():
            plain(marker).unlink()
    else:
        atomic_text(marker, "Disabled by Longshot. Remove this file to enable the mod.\n")


def set_order(root, names):
    root = Path(root).absolute()
    layers = scan(root)
    found = {m["name"]: m for m in layers}
    if len(names) != len(set(names)):
        raise ValueError("A mod appears more than once in the order")
    for name in names:
        if name not in found:
            raise ValueError(f"Unknown mod: {name}")
        if found[name]["errors"]:
            raise ValueError("; ".join(found[name]["errors"]))
    atomic_text(root / ORDER, "# Longshot: first to last, last enabled layer wins\n" + "\n".join(names) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mods", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("conflicts")
    for command in ("enable", "disable"):
        commands.add_parser(command).add_argument("name")
    commands.add_parser("order").add_argument("names", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command in ("enable", "disable"):
            set_enabled(args.mods, args.name, args.command == "enable")
        elif args.command == "order":
            set_order(args.mods, args.names)
        layers = scan(args.mods)
        report = conflicts(layers) if args.command == "conflicts" else layers
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "conflicts":
            for row in report:
                print(f"{row['path']}: {' < '.join(row['layers'])}; winner: {row['winner']}")
            if not report:
                print("No enabled RomFS file conflicts.")
        else:
            for layer in layers:
                print(f"{'ON ' if layer['enabled'] else 'OFF'} {layer['name']} ({len(layer['files'])} files)")
                for error in layer['errors']:
                    print(f"    Invalid: {error}")
                if layer['exefs_unsupported']:
                    print("    ExeFS patches are not applied by this native recompilation.")
            if args.command not in ("list", "conflicts"):
                print("Saved. Changes apply on the next game launch.")
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"longshot-mods: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
