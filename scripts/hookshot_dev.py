"""Read-only Hookshot developer console: inspect the HOS_DEVTOOLS=1 log feed.

SPDX-License-Identifier: GPL-3.0-or-later
No socket, arbitrary evaluation, memory writes, or game restore commands.
"""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I
from hookshot_checkpoint import CheckpointError, read_checkpoint

PREFIX = "devtools-v1 "
MAX_LINE = 4096
MAX_TAIL = 1024 * 1024


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate observation key")
        result[key] = value
    return result


def parse_sample(line):
    at = line.find(PREFIX)
    if at < 0 or len(line) > MAX_LINE:
        return None
    try:
        sample = json.loads(line[at + len(PREFIX):], object_pairs_hook=_unique_pairs)
        json.dumps(sample, allow_nan=False)  # reject non-finite values in extra fields too
        if not isinstance(sample, dict) or type(sample.get("schema")) is not int or sample["schema"] != 1 \
                or sample.get("kind") != "player-observation":
            return None
        bits = sample["position_bits"]
        if not isinstance(bits, list) or len(bits) != 3 or any(type(v) is not int or not 0 <= v < 2**32 for v in bits):
            return None
        position = list(struct.unpack("<fff", struct.pack("<III", *bits)))
        if not all(math.isfinite(v) for v in position):
            return None
        if any(type(sample.get(k)) is not int or not 0 <= sample[k] < 2**64 for k in ("sequence", "monotonic_ns")):
            return None
        for key, limit in (("program_id", 16), ("game_build_id", 64), ("runtime_build", 95), ("scene", 79)):
            if not isinstance(sample.get(key), str) or len(sample[key].encode("utf-8")) > limit:
                return None
        if re.fullmatch(r"[0-9a-f]{16}", sample["program_id"]) is None \
                or re.fullmatch(r"(?:[0-9a-f]{2}){1,32}", sample["game_build_id"]) is None:
            return None
        sample["position"] = position
        return sample
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        return None


def latest_sample(path):
    # Read only a bounded tail. Ignore partial final records and arbitrary log lines.
    with Path(path).open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        start = max(0, size - MAX_TAIL)
        stream.seek(start)
        lines = stream.read(MAX_TAIL).splitlines(keepends=True)
        if start:
            lines = lines[1:]  # the bounded tail may start halfway through a log record
    for line in reversed(lines):
        if not line.endswith(b"\n") or len(line) > MAX_LINE:
            continue
        try:
            sample = parse_sample(line.decode("utf-8"))
        except UnicodeError:
            continue
        if sample:
            return sample
    raise ValueError("no complete player observation in the log tail; enable HOS_DEVTOOLS=1 and enter gameplay")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "watch", "sample"):
        sub = commands.add_parser(name)
        sub.add_argument("--log", type=Path, required=True)
        if name == "watch":
            sub.add_argument("--interval", type=float, default=0.5)
        if name == "sample":
            sub.add_argument("--out", type=Path, required=True)
    sub = commands.add_parser("checkpoint-inspect")
    sub.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "checkpoint-inspect":
            checkpoint = read_checkpoint(args.path)
            print(json.dumps({"identity": asdict(checkpoint.identity), "provider": checkpoint.provider,
                              "provider_schema": checkpoint.provider_schema,
                              "exact_bytes": len(checkpoint.exact or b""),
                              "note": "Envelope validated. No capture/restore provider is installed by this tool."}, indent=2))
            return 0
        if args.command == "watch" and (not math.isfinite(args.interval) or not 0.1 <= args.interval <= 60):
            raise ValueError("watch interval must be between 0.1 and 60 seconds")
        previous = None
        waiting = False
        while True:
            try:
                sample = latest_sample(args.log)
                waiting = False
            except (OSError, ValueError):
                if args.command != "watch":
                    raise
                if not waiting:
                    print("Waiting for complete player observations (gameplay, HOS_DEVTOOLS=1)...", file=sys.stderr)
                    waiting = True
                time.sleep(args.interval)
                continue
            # Restarts reset sequence: identity and monotonic time disambiguate them.
            key = (sample["runtime_build"], sample["monotonic_ns"], sample["sequence"])
            if key != previous:
                text = json.dumps(sample, ensure_ascii=False, allow_nan=False, indent=2)
                if args.command == "sample":
                    # Preserve an existing export; snapshots are observations, not save states.
                    with args.out.open("x", encoding="utf-8") as stream:
                        stream.write(text + "\n")
                    print("Exported a player observation; it cannot restore the game.")
                else:
                    # ASCII escapes also work in Windows consoles with a legacy code page.
                    print(json.dumps(sample, allow_nan=False, indent=2), flush=True)
                previous = key
            if args.command != "watch":
                return 0
            time.sleep(args.interval)
    except (OSError, ValueError, CheckpointError) as error:
        print("hookshot-dev: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
