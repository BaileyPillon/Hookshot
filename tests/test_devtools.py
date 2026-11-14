"""Run the production observer SDK and read-only CLI without a game or GPU."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("developer watch did not report the expected observation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    cxx = shutil.which(args.cxx)
    if not cxx:
        raise SystemExit("compiler not found")
    env = dict(os.environ)
    env["PATH"] = str(Path(cxx).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="hookshot-devtools-") as tmp:
        folder = Path(tmp)
        exe = folder / ("fixture.exe" if os.name == "nt" else "fixture")
        subprocess.run([cxx, "-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
                        "-D_CRT_SECURE_NO_WARNINGS",  # fixed fixture strings also compile against the MSVC CRT
                        "-I" + str(ROOT / "host"), str(ROOT / "host/devtools.c"),
                        str(ROOT / "tests/devtools_fixture.c"), str(ROOT / "examples/devtools/observer.c"),
                        "-o", str(exe)], check=True, env=env, capture_output=True, text=True, timeout=60)
        run = subprocess.run([str(exe)], check=True, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10)
        samples = [json.loads(line) for line in run.stdout.splitlines()]
        assert len(samples) == 2 and [s["sequence"] for s in samples] == [1, 3]
        assert samples[0]["scene"] == 'Kokiri_测试"\\\n'
        assert len(samples[0]["game_build_id"]) == 64
        script = ROOT / "scripts/hookshot_dev.py"
        log = folder / "hookshot_log.txt"
        # A truncated newer record must not hide the most recent complete one.
        log.write_text("[hos fixture] devtools-v1 " + json.dumps(samples[0]) + "\n"
                       "[hos fixture] devtools-v1 {\"schema\":", encoding="utf-8")
        status = subprocess.run([sys.executable, "-I", str(script), "status", "--log", str(log)],
                                capture_output=True, text=True, check=True)
        assert json.loads(status.stdout)["position"] == [1.25, -2.5, 0.0]
        out = folder / "sample.hos-observation.json"
        cmd = [sys.executable, "-I", str(script), "sample", "--log", str(log), "--out", str(out)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        preserved = out.read_bytes()
        assert subprocess.run(cmd, capture_output=True).returncode == 1
        assert out.read_bytes() == preserved
        for bad in ("not-json", '{"schema":2}', '{"schema":true}'):
            log.write_text("[hos fixture] devtools-v1 " + bad + "\n", encoding="utf-8")
            assert subprocess.run([sys.executable, "-I", str(script), "status", "--log", str(log)],
                                  capture_output=True).returncode == 1
        malformed = []
        for key, value in (("sequence", 2**64), ("sequence", True), ("game_build_id", "a" * 39),
                           ("position_bits", [0x7f800000, 0, 0]), ("scene", "测试" * 27)):
            malformed.append(json.dumps(dict(samples[0], **{key: value})))
        malformed.append(json.dumps(samples[0])[:-1] + ',"sequence":99}')
        for bad in malformed:
            log.write_text("devtools-v1 " + bad + "\n", encoding="utf-8")
            assert subprocess.run([sys.executable, "-I", str(script), "status", "--log", str(log)],
                                  capture_output=True).returncode == 1
        log.write_bytes(b'devtools-v1 ' + json.dumps(samples[0]).replace('Kokiri_', 'Kokiri_\xff').encode('latin-1') + b'\n')
        assert subprocess.run([sys.executable, "-I", str(script), "status", "--log", str(log)],
                              capture_output=True).returncode == 1
        # Watch must survive a missing startup log and emit updates after it appears.
        watch_log = folder / "not-created-yet.log"
        watch_out, watch_err = folder / "watch.out", folder / "watch.err"
        with watch_out.open("w", encoding="utf-8") as stdout, watch_err.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen([sys.executable, "-I", str(script), "watch", "--log", str(watch_log),
                                        "--interval", "0.1"], stdout=stdout, stderr=stderr)
            try:
                wait_for(lambda: "Waiting for" in watch_err.read_text(encoding="utf-8"))
                watch_log.write_text("devtools-v1 " + json.dumps(samples[0]) + "\n", encoding="utf-8")
                wait_for(lambda: '"sequence": 1' in watch_out.read_text(encoding="utf-8"))
                watch_log.write_text("devtools-v1 " + json.dumps(samples[1]) + "\n", encoding="utf-8")
                wait_for(lambda: '"sequence": 3' in watch_out.read_text(encoding="utf-8"))
                assert process.poll() is None
            finally:
                process.terminate()
                process.wait(timeout=5)
        main_source = (ROOT / "host/hos_main.c").read_text(encoding="utf-8")
        assert "if (hos_dev_enabled()) oot_dev_observe(c, actor);" in main_source
        assert 'hos_dev_init(dev && !strcmp(dev, "1"), devtools_log_sample, NULL);' in main_source
    print("observer SDK: ABI/capability checks, isolation, re-entrancy, bounds, UTF-8 and rate limit passed")
    print("live CLI: JSON/float validation, UTF-8, partial records, startup watch and export preservation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
