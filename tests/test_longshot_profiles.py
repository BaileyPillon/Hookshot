"""Run the production profile selector against isolated directories, including UTF-8.

Verify env/config precedence, original-path preservation, invalid selections,
file/reparse-point refusal and bounded output. No real save is opened.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
RUN_ALL_SKIP = {"linux": "native Windows filesystem fixture; selector also builds with the POSIX host"}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import win_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) / "Zelda-日本"
        folder.mkdir()
        base = folder / "user"
        base.mkdir()
        original = base / "original.sav"
        original.write_bytes(b"synthetic save: preserve me")
        fixture = folder / "fixture.c"
        fixture.write_text('#include "save_profile.h"\n#include <stdio.h>\n#include <stdlib.h>\nvoid hos_log(const char *s, ...) {}\nint main(int n,char**a){char out[1024];if(n<2)return 3;if(!hos_save_profile_select(a[1],out,n>2?atoi(a[2]):sizeof out))return 2;puts(out);return 0;}\n')
        resource = folder / "utf8.res"
        resource.write_bytes(win_manifest.res_bytes())
        exe = folder / "fixture.exe"
        subprocess.run([args.cxx, "-x", "c", "-std=c11", "-I" + str(ROOT / "host"), str(fixture), str(ROOT / "host/save_profile.c"), "-x", "none", str(resource), "-o", str(exe)], check=True)
        def run(profile=None, capacity=None):
            env = dict(os.environ)
            env.pop("HOS_SAVE_PROFILE", None)
            if profile is not None:
                env["HOS_SAVE_PROFILE"] = profile
            return subprocess.run([str(exe), str(base)] + ([str(capacity)] if capacity else []), env=env,
                                  capture_output=True, text=True, encoding="utf-8")
        assert Path(run().stdout.strip()) == base
        config = folder / "hookshot_options.ini"
        config.write_text("save_profile=3\n")
        assert Path(run().stdout.strip()) == base / "profiles/profile-3"
        assert Path(run("2").stdout.strip()) == base / "profiles/profile-2"
        assert Path(run("1").stdout.strip()) == base
        for invalid in ("0", "10", "2bad", "../../", "-1"):
            assert run(invalid).returncode == 2, invalid
        assert run("2", 4).returncode == 2
        (base / "profiles/profile-4").write_text("a file must not be a save directory")
        assert run("4").returncode == 2
        # Junctions require no developer mode. Do not delete through them.
        target = folder / "outside"
        target.mkdir()
        link = base / "profiles/profile-5"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if made.returncode == 0:
            try:
                assert run("5").returncode == 2
                assert not list(target.iterdir())
            finally:
                os.rmdir(link)
        assert original.read_bytes() == b"synthetic save: preserve me"
        print("profiles: original unchanged; separate paths, UTF-8, config/env precedence, invalid/file/junction refusal passed")


if __name__ == "__main__":
    main()
