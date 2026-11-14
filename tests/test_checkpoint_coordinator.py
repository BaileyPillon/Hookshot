"""SPDX-License-Identifier: GPL-3.0-or-later
Compile the production native restore coordinator against a synthetic backend. No game or GPU.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    compiler = shutil.which(args.cxx)
    if not compiler:
        raise SystemExit("checkpoint coordinator: no C compiler")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="hookshot-coordinator-") as directory:
        executable = Path(directory) / ("fixture.exe" if os.name == "nt" else "fixture")
        subprocess.run([compiler, "-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
                        "-I" + str(ROOT / "host"), str(ROOT / "host/checkpoint.c"),
                        str(ROOT / "tests/checkpoint_fixture.c"), "-o", str(executable)],
                       check=True, env=env, timeout=60)
        subprocess.run([str(executable)], check=True, env=env, timeout=10)


if __name__ == "__main__":
    main()
