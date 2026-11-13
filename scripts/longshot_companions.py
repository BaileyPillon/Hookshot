"""Prepare, build and launch Longshot's pinned optional companions.

Generated data stays under work/longshot-companions, never in a submodule or a
play installation. All commands use an explicit game/save folder when needed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integrations/manifest.json"


def entry(name):
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["companions"][name]


def run(command, cwd=ROOT, env=None):
    subprocess.run([str(p) for p in command], cwd=cwd, env=env, check=True)


def tool(name):
    found = shutil.which(name + (".cmd" if os.name == "nt" and name == "npm" else ""))
    if not found and os.name == "nt" and name == "npm":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/npm.cmd"
        if candidate.is_file():
            found = str(candidate)
    if not found:
        raise ValueError(f"{name} is required; install it and add it to PATH")
    return found


def prepare(name):
    spec = entry(name)
    source = ROOT / "integrations" / name
    if not (source / ".git").exists():
        raise ValueError("Initialize companions first: git submodule update --init")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != spec["commit"]:
        raise ValueError(f"{name}: checkout does not match its reviewed pin")
    digest = hashlib.sha256(head.encode())
    for relative in spec["patches"]:
        digest.update((ROOT / "integrations" / relative).read_bytes())
    stamp = digest.hexdigest()
    destination = ROOT / "work/longshot-companions" / f"{name}-{stamp[:12]}"
    marker = destination / ".longshot-source.json"
    if destination.exists():
        if not marker.is_file() or json.loads(marker.read_text())["stamp"] != stamp:
            raise ValueError(f"Incomplete preparation; preserve/rename this folder and retry: {destination}")
        return destination
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "source.zip"
        run(["git", "-C", source, "archive", "--format=zip", spec["commit"], "-o", archive])
        with zipfile.ZipFile(archive) as contents:
            for info in contents.infolist():
                target = (destination / info.filename).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise ValueError("Source archive contains an escaping path")
            contents.extractall(destination)
    for patch in spec["patches"]:
        run(["git", "apply", "--directory=" + destination.relative_to(ROOT).as_posix(), ROOT / "integrations" / patch])
    marker.write_text(json.dumps({"stamp": stamp, "commit": head, "companion": name}, indent=2), encoding="utf-8")
    return destination


def game_folder(path):
    path = Path(path).resolve()
    if not (path / "romfs").is_dir() or not (path / "image.bin").is_file():
        raise ValueError("Choose a built game folder containing romfs and image.bin")
    if not any(p.is_file() for p in (path / "bin/hookshot.exe", path / "hookshot.exe")):
        raise ValueError("No Hookshot/Longshot executable in that game folder")
    return path


def launch_plan(name, directory, game=None, saves=None):
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    if name == "ootrr":
        if not game:
            raise ValueError("Full randomizer requires --game <experimental game folder>")
        # Never install its seeds or attach its live tracker to ordinary play.
        mode_game = game_folder(Path(game) / "longshot-modes/ootrr")
        marker = mode_game / "longshot-mode.json"
        if not marker.is_file() or json.loads(marker.read_text()).get("mode") != "ootrr":
            raise ValueError("Prepare the separate full-randomizer game first; see docs/longshot-features.md")
        python = directory / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise ValueError("Build the full randomizer first: longshot_companions.py build ootrr")
        env["LONGSHOT_OOTRR_GAME"] = str(mode_game)
        key = hashlib.sha256(str(mode_game).encode()).hexdigest()[:12]
        env["LONGSHOT_OOTRR_DATA"] = str(directory / "build/longshot" / key)
        env["HOS_COOP"] = "0"
        env.pop("HOS_FS_OVERLAY", None)
        env.pop("HOS_MODS", None)
        return [str(python), "-I", "-m", "oot_rando"], env
    if name == "randomizer":
        if sys.version_info < (3, 14):
            raise ValueError("The randomizer requires Python 3.14 or newer (compression.zstd)")
        if not game:
            raise ValueError("Randomizer launch requires --game <experimental game folder>")
        env["OOT_GAME"] = str(game_folder(game))
        env["HOS_COOP"] = "0"  # Mixing randomizer and co-op is not validated.
        env.pop("HOS_FS_OVERLAY", None)
        return [sys.executable, "-I", str(directory / "tools/gui.py")], env
    if not saves or not Path(saves).is_dir():
        raise ValueError("Tracker launch requires --saves <save/profile folder>")
    if not (directory / "dist-electron/main.cjs").is_file():
        raise ValueError("Build the tracker first with: longshot_companions.py build tracker")
    env["OOT_SAVE_DIR"] = str(Path(saves).resolve())
    env["OOT_USER_DATA"] = str(directory / "longshot-user-data")
    return [tool("node"), str(directory / "scripts/start.mjs")], env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "prepare", "build", "test", "launch"))
    parser.add_argument("companion", choices=("oot-coop", "randomizer", "ootrr", "tracker"))
    parser.add_argument("--game", type=Path)
    parser.add_argument("--saves", type=Path)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="print a launch plan without opening an app")
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            print(json.dumps(entry(args.companion), indent=2))
            return 0
        directory = prepare(args.companion)
        print(directory, flush=True)
        if args.action == "prepare":
            return 0
        if args.companion == "oot-coop":
            build = directory / "build"
            if args.action == "build":
                run([args.cmake, "-S", directory, "-B", build, "-DCOOP_BUILD_HOOKSHOT=ON", "-DCOOP_BUILD_TESTS=ON"])
                run([args.cmake, "--build", build, "--config", "Release", "--parallel", max(1, args.jobs)])
            elif args.action == "test":
                ctest = Path(args.cmake).with_name("ctest.exe" if os.name == "nt" else "ctest")
                run([ctest, "--test-dir", build, "-C", "Release", "--output-on-failure", "-j", max(1, args.jobs)])
            else:
                raise ValueError("Co-op is launched from an isolated game; see docs/longshot-features.md")
        elif args.action == "launch":
            command, env = launch_plan(args.companion, directory, args.game, args.saves)
            if args.dry_run:
                print(json.dumps({"command": command, "cwd": str(directory), "environment":
                                  {k: env[k] for k in ("OOT_GAME", "OOT_SAVE_DIR", "OOT_USER_DATA", "HOS_COOP",
                                                       "LONGSHOT_OOTRR_GAME", "LONGSHOT_OOTRR_DATA") if k in env}}, indent=2))
            else:
                subprocess.Popen(command, cwd=directory, env=env)
        elif args.companion == "ootrr":
            python = directory / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if args.action == "build":
                if not python.exists():
                    run([sys.executable, "-I", "-m", "venv", directory / ".venv"])
                run([python, "-I", "-m", "pip", "install", "-r", ROOT / "integrations/ootrr-requirements.txt"])
                run([python, "-I", "-m", "pip", "install", "--no-deps", "-e", directory])
            else:
                if not python.is_file():
                    raise ValueError("Build ootrr first")
                run([python, "-I", "-m", "unittest", "discover", "-s", directory / "tests", "-v"], directory)
                run([python, "-I", "-m", "oot_rando", "selftest"], directory)
        elif args.companion == "tracker":
            npm = tool("npm")
            if args.action == "build":
                run([npm, "ci", "--no-audit", "--no-fund"], directory)
                run([npm, "run", "typecheck"], directory)
                run([npm, "run", "build"], directory)
            else:
                run([npm, "test"], directory)
        else:
            raise ValueError("Randomizer has no build step; launch its GUI or run tests/test_longshot_randomizer.py")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"longshot-companions: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
