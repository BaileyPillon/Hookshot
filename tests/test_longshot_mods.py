"""Synthetic mod trees: Python conflict reports agree with the actual native loader.

No game assets. The native fixture compiles mods.c unchanged except its unused
guest-runtime header; Windows filesystem calls and the production hash table run.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import longshot_mods as mods

RUN_ALL_ARGS = ["--cxx", "{cxx}"]


class Manager(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "mods"
        for name in ("A", "Z", "group/Nested", "_off"):
            p = self.root / name / "romfs" / "Test" / "file.txt"
            p.parent.mkdir(parents=True)
            p.write_text(name)

    def tearDown(self):
        self.temp.cleanup()

    def winner(self):
        return mods.conflicts(mods.scan(self.root))[0]["winner"]

    def test_order_disable_and_restore(self):
        self.assertEqual(self.winner(), "Z")
        mods.set_order(self.root, ["Z", "A"])
        self.assertEqual(self.winner(), "A")
        mods.set_enabled(self.root, "A", False)
        self.assertEqual(self.winner(), "Z")
        mods.set_enabled(self.root, "A", True)
        self.assertEqual(self.winner(), "A")
        self.assertEqual((self.root / "A/romfs/Test/file.txt").read_text(), "A")

    def test_reject_escaping_unknown_duplicates_and_wrong_build(self):
        for name in ("../A", "unknown", "_off"):
            with self.assertRaises(ValueError):
                mods.set_enabled(self.root, name, True)
        with self.assertRaises(ValueError):
            mods.set_order(self.root, ["A", "A"])
        (self.root / "A/longshot-mod.json").write_text('{"build_id":"wrong"}')
        mods.set_enabled(self.root, "A", False)
        with self.assertRaises(ValueError):
            mods.set_enabled(self.root, "A", True)
        self.assertTrue((self.root / "A" / mods.MARKER).exists())

    def test_disabled_parent_and_exefs_warning(self):
        (self.root / "group" / mods.MARKER).write_text("")
        (self.root / "A/exefs").mkdir()
        layers = {m["name"]: m for m in mods.scan(self.root)}
        self.assertFalse(layers["group/Nested"]["enabled"])
        self.assertTrue(layers["A"]["exefs_unsupported"])
        with self.assertRaises(ValueError):
            mods.set_enabled(self.root, "group/Nested", True)

    def test_manifest_duplicate_keys(self):
        (self.root / "A/longshot-mod.json").write_text('{"schema":1,"schema":2}')
        self.assertIn("Duplicate", mods.manifest_errors(self.root / "A")[0])

    def test_native_winners(self):
        if not NATIVE:
            self.skipTest("Windows native loader fixture")
        def check():
            result = subprocess.run([str(NATIVE), str(self.root)], capture_output=True, text=True, check=True)
            actual = Path(result.stdout.strip())
            expected = self.root / self.winner() / "romfs/Test/file.txt"
            self.assertEqual(actual, expected)
        check()
        mods.set_order(self.root, ["Z", "A"])
        check()
        mods.set_enabled(self.root, "A", False)
        check()
        mods.set_enabled(self.root, "A", True)
        check()
        # Runtime accepts slash/case normalization in hand-edited order files too.
        (self.root / mods.ORDER).write_text("z\ngroup\\nested\n")
        check()


NATIVE = None
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        if os.name == "nt":
            folder = Path(temporary)
            source = (ROOT / "host/mods.c").read_text().replace('#include "hos.h"', '#include <stdint.h>\nvoid hos_log(const char*, ...);')
            source += '\nvoid hos_log(const char *s, ...) {}\nint hos_prompts_romfs(const char *k, const char *p, char *o, size_t n) {return 0;}\n'
            source += 'int main(int n,char **a){if(n!=2)return 2;_putenv_s("HOS_MODS",a[1]);hos_mods_init(0);char p[1024];if(!hos_mods_file("test/file.txt",p,sizeof p))return 3;puts(p);return 0;}\n'
            (folder / "fixture.c").write_text(source)
            NATIVE = folder / "fixture.exe"
            subprocess.run([args.cxx, "-x", "c", "-std=c11", "-I" + str(ROOT / "host"), str(folder / "fixture.c"), "-o", str(NATIVE)], check=True)
        result = unittest.main(argv=[sys.argv[0]], exit=False)
        sys.exit(not result.result.wasSuccessful())
