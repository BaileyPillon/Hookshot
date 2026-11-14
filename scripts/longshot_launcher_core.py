"""Local launcher operations. Save imports never replace an existing profile."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oot_checkpoints as checkpoints
import oot_saves

DEFAULT_ACCOUNT = "5a3c9e1f0b7d24680000000000000001"
LIMITS = checkpoints.ACCOUNT_FILES | checkpoints.SLOT_FILES


def plain_path(path, *, directory=True):
    """Do not follow links, including links in an ancestor, for save operations."""
    path = Path(os.path.abspath(path))
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Choose a regular folder, not a link: {parent}")
    if path.exists():
        checkpoints.normal_path(path, directory=directory)
    return path


def profile_folder(game, number):
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 9:
        raise ValueError("Choose save profile 1 through 9")
    base = plain_path(Path(game) / "user")
    return plain_path(base if number == 1 else base / "profiles" / f"profile-{number}")


def closed_games():
    active = oot_saves.running_games()
    if active:
        raise ValueError("Save your progress and close the game first: " + ", ".join(active))


def save_files(source):
    """Read complete native save slots with bounded sizes and consistency checks."""
    source = plain_path(source)
    if not source.is_dir():
        raise ValueError("Select the save account folder containing account.sav and slot_00, slot_01, …")
    paths = [source / "account.sav"]
    if (source / "option.sav").exists():
        paths.append(source / "option.sav")
    slots = []
    for folder in sorted(source.iterdir()):
        if not re.fullmatch(r"slot_\d{2}", folder.name):
            continue
        if int(folder.name[5:]) > 11:
            raise ValueError(f"Unknown native slot: {folder.name}")
        plain_path(folder)
        for name in checkpoints.SLOT_FILES:
            paths.append(folder / name)
        slots.append(folder.name)
    if not slots:
        raise ValueError("No complete native saves found. Select the account folder, not a single slot.")
    before, data = {}, {}
    for path in paths:
        plain_path(path, directory=False)
        info = checkpoints.normal_path(path)
        if not 0 < info.st_size <= LIMITS[path.name]:
            raise ValueError(f"Empty or oversized save: {path.name}")
        before[path] = checkpoints.stat_key(info)
        with path.open("rb") as stream:
            if checkpoints.stat_key(os.fstat(stream.fileno())) != before[path]:
                raise ValueError("Save changed while reading; close the game and retry")
            content = stream.read(LIMITS[path.name] + 1)
        if len(content) != info.st_size:
            raise ValueError("Save changed while reading; close the game and retry")
        data[path.relative_to(source)] = content
    if any(checkpoints.stat_key(checkpoints.normal_path(p)) != key for p, key in before.items()):
        raise ValueError("Save changed while reading; close the game and retry")
    return data, slots


def import_save(source, game, number):
    """Verified staged copy; original saves and existing destination profiles survive."""
    if number == 1:
        raise ValueError("Import into a new profile from 2 through 9; profile 1 is your original playthrough")
    closed_games()
    source = plain_path(source)
    destination = profile_folder(game, number)
    if destination.exists():
        raise ValueError("This profile already exists. Choose a new profile to keep its progress.")
    data, slots = save_files(source)
    account = source.name.lower() if re.fullmatch(r"[0-9a-fA-F]{32}", source.name) else DEFAULT_ACCOUNT
    destination.parent.mkdir(parents=True, exist_ok=True)
    plain_path(destination.parent)
    destination.mkdir()  # Reserve exclusively. Never overwrite even an empty existing profile.
    try:
        with tempfile.TemporaryDirectory(prefix=".import-", dir=destination) as temporary:
            staged = Path(temporary) / "save"
            root = staged / account
            for relative, content in data.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
                    raise ValueError("Save verification failed; the new profile was not published")
            closed_games()
            staged.rename(destination / "save")
    except BaseException:
        if not (destination / "save").exists():
            destination.rmdir()
        raise
    return {"folder": str(destination), "slots": slots, "files": len(data), "account": account}


def launch_plan(game, number=1, romfs=None):
    game = Path(game).resolve()
    executable = checkpoints.game_executable(game)
    image = game / "image.bin"
    assets = Path(romfs).resolve() if romfs else game / "romfs"
    if not image.is_file() or not assets.is_dir():
        raise ValueError("Choose a built game folder with image.bin and romfs (or specify --romfs)")
    user = profile_folder(game, number)
    env = dict(os.environ)
    env["HOS_COOP"] = "0"
    env.pop("HOS_FS_OVERLAY", None)
    env.pop("HOS_MODS", None)
    # Explicit --user wins over saved menu/environment profile selection on both platforms.
    return [str(executable), str(image), "--romfs", str(assets), "--user", str(user)], env


def start_game(game, number=1, romfs=None, *, journal_endpoint=None):
    closed_games()
    command, env = launch_plan(game, number, romfs)
    if journal_endpoint is not None:
        # The companion receives samples over one local connection. It neither
        # exposes a network server nor enables arbitrary memory access.
        if not isinstance(journal_endpoint, str) or not journal_endpoint or len(journal_endpoint) > 180:
            raise ValueError("Invalid local journal endpoint")
        env["HOS_CONTROL"] = journal_endpoint
        env["HOS_CONTROL_MEM"] = "0"
        env.pop("HOS_INPUT_EXCLUSIVE", None)
        env.pop("HOS_INPUT_SCRIPT", None)
    # Explicit --user bypasses native profile directory creation. Create all parents
    # before the game starts, including a profile's first-ever launch.
    user = profile_folder(game, number)
    user.mkdir(parents=True, exist_ok=True)
    plain_path(user)
    return subprocess.Popen(command, cwd=game, env=env)


def coop_launch_plan(game, number, server, port, name, password, romfs=None):
    """Join with a separate profile and the normal puppet mod loader; never start a server."""
    if number == 1:
        raise ValueError("Choose a separate co-op profile from 2 through 9")
    command, env = launch_plan(game, number, romfs)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,253}", server):
        raise ValueError("Enter the server's host name or IPv4 address, without a URL or port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Enter a server port from 1 to 65535")
    if not 1 <= len(name) <= 16 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Use a player name of 1 to 16 characters, without control characters")
    if not password or len(password.encode("utf-8")) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError("Enter the session password (1 to 128 UTF-8 bytes, without control characters)")
    binary_folder = Path(command[0]).parent
    module = plain_path(binary_folder / "hookshot_coop.dll", directory=False)
    if not module.is_file():
        raise ValueError("Build and install the pinned co-op module beside the experimental game executable first")
    pack = plain_path(binary_folder / "mods/contents/0400486024DEC000/coop-puppet")
    for required in ("romfs", "coop_puppet.json", "coop_rooms.txt", "coop_hud/hud.json"):
        path = plain_path(pack / required, directory=(required == "romfs"))
        if not path.exists():
            raise ValueError("Generate the co-op puppet pack in mods/contents/0400486024DEC000/coop-puppet first")
    # The marker stays on disk. Exact co-op opt-in enables only this named pack
    # under the scoped mod root, preserving the native prompt-size-table merge.
    if not (pack / ".longshot-disabled").is_file():
        raise ValueError("Disable the coop-puppet mod in Manage mods before joining; co-op loads it for this session")
    env = {k: v for k, v in env.items() if not k.startswith("LICHII_COOP_")}
    env.update(HOS_COOP="1", HOS_MODS=str(pack.parent),
               LICHII_COOP_SERVER=server, LICHII_COOP_PORT=str(port),
               LICHII_COOP_NAME=name, LICHII_COOP_PASSWORD=password,
               LICHII_COOP_HOST_SAVE="0", LICHII_COOP_PUPPET="1",
               LICHII_COOP_OBJECTS="1", LICHII_COOP_SPAWN="1", LICHII_COOP_CHEATS="0")
    return command, env


def start_coop(game, number, server, port, name, password, romfs=None):
    if os.name != "nt":
        raise ValueError("The pinned native co-op module currently requires Windows")
    closed_games()
    command, env = coop_launch_plan(game, number, server, port, name, password, romfs)
    user = profile_folder(game, number)
    user.mkdir(parents=True, exist_ok=True)
    plain_path(user)
    return subprocess.Popen(command, cwd=game, env=env)


def hardware_info():
    result = {"cpu": "Unknown", "ram_gib": None, "gpus": [], "platform": sys.platform}
    if os.name == "nt":
        script = ("$c=Get-CimInstance Win32_Processor; $m=Get-CimInstance Win32_ComputerSystem; "
                  "$g=Get-CimInstance Win32_VideoController; "
                  "@{cpu=($c.Name -join ', ');ram_gib=[math]::Round($m.TotalPhysicalMemory/1GB,1);"
                  "gpus=@($g | ForEach-Object {@{name=$_.Name;driver=$_.DriverVersion}})} | ConvertTo-Json -Depth 4")
        try:
            process = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                     capture_output=True, text=True, timeout=20,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            if process.returncode == 0:
                result.update(json.loads(process.stdout))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            text = Path("/proc/cpuinfo").read_text()
            result["cpu"] = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("model name"))
            memory = Path("/proc/meminfo").read_text()
            result["ram_gib"] = round(int(re.search(r"MemTotal:\s+(\d+)", memory)[1]) / 1048576, 1)
        except (OSError, StopIteration, TypeError):
            pass
    # Win32_VideoController.AdapterRAM truncates above 4 GiB. Query NVIDIA directly instead.
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            process = subprocess.run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10,
                                     **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            if process.returncode == 0:
                nvidia = []
                for line in process.stdout.splitlines():
                    name, memory, driver = (part.strip() for part in line.split(","))
                    nvidia.append({"name": name, "vram_gib": round(float(memory) / 1024, 1), "driver": driver})
                result["gpus"] = [g for g in result["gpus"] if "nvidia" not in g["name"].lower()] + nvidia
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return result


def recommendations(info):
    """Conservative starting points, not measured performance or automatic settings."""
    rows = [("Frame generation", "Off for the first test", "Check ordinary frames for flicker before adding generated frames."),
            ("Frame limit", "60 FPS to start", "Measure a consistent scene before increasing the limit."),
            ("HDR", "Keep your working setting", "Enable only after checking your display and Windows HDR setup.")]
    names = " ".join(g.get("name", "") for g in info.get("gpus", [])).lower()
    if "rtx" in names:
        rows.append(("Upscaling", "Try DLSS Quality if GPU-limited", "Requires a build with NVIDIA NGX and its runtime; compare image quality in motion."))
    elif info.get("gpus"):
        rows.append(("Upscaling", "Try FSR if GPU-limited", "Availability depends on the GPU and renderer build; compare against native resolution."))
    ram = info.get("ram_gib")
    if ram is not None and ram < 24:
        rows.append(("Memory", "Keep optional companions closed initially", "Measure available memory before running the game and extra applications together."))
    rows.append(("Controller", "10–15% deadzone as a starting point", "Raise it if an untouched stick moves the camera or Link."))
    return rows
