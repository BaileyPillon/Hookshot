"""Checkpoint integrity, transactional writes, compatibility and explicit restore capabilities. No game."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hookshot_checkpoint", ROOT / "scripts/hookshot_checkpoint.py")
cp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cp
spec.loader.exec_module(cp)


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hookshot-checkpoint-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "slot.hsc"
        self.identity = cp.Identity("0400486024dec000", "a" * 40, "fixture-only", "1" * 64,
                                    "fixture-x86_64", 1, "2" * 64, "3" * 64)
        self.checkpoint = cp.Checkpoint(self.identity, "fixture.position", 1,
                                        {"scene": "fixture", "position": [1.25, -2.5, 0]}, b"synthetic-fixture")

    def write(self, checkpoint=None):
        cp.write_checkpoint(self.path, checkpoint or self.checkpoint)
        return cp.read_checkpoint(self.path)

    def rewrite(self, transform):
        with zipfile.ZipFile(self.path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        transform(entries)
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def test_round_trip(self):
        self.assertEqual(self.write(), self.checkpoint)
        self.assertEqual(self.write(replace(self.checkpoint, exact=None)).exact, None)

    def test_legacy_exact_cannot_be_authorized_by_a_boolean(self):
        loaded = self.write()
        self.assertEqual(cp.choose_restore(loaded, self.identity).mode, "reject")
        self.assertEqual(cp.choose_restore(loaded, self.identity, exact_supported=True).mode, "reject")
        self.assertEqual(cp.choose_restore(loaded, self.identity, exact_supported="false").mode, "reject")
        for current in (replace(self.identity, runtime_build="next"), replace(self.identity, state_abi=2),
                        replace(self.identity, runtime_sha256="4" * 64), replace(self.identity, platform="other")):
            self.assertEqual(cp.choose_restore(loaded, current, exact_supported=True).mode, "reject")
            self.assertEqual(cp.choose_restore(loaded, current, exact_supported=True,
                             portable_providers={"fixture.position": 1}).mode, "reject")

    def test_legacy_portable_cannot_supply_native_save_binding(self):
        loaded = self.write(replace(self.checkpoint, exact=None))
        self.assertEqual(cp.choose_restore(loaded, self.identity, portable_providers={"fixture.position": 1}).mode,
                         "reject")
        self.assertEqual(cp.choose_restore(loaded, self.identity, portable_providers={"fixture.position": 2}).mode,
                         "reject")

    def test_different_game_mods_or_config_reject(self):
        loaded = self.write()
        for current in (replace(self.identity, program_id="0" * 16), replace(self.identity, game_build_id="b" * 40),
                        replace(self.identity, mod_set_sha256="4" * 64), replace(self.identity, config_sha256="4" * 64)):
            self.assertEqual(cp.choose_restore(loaded, current, exact_supported=True,
                             portable_providers={"fixture.position": 1}).mode, "reject")

    def test_observation_never_restores(self):
        loaded = self.write(replace(self.checkpoint, provider="hookshot.player-observation"))
        self.assertEqual(cp.choose_restore(loaded, self.identity, exact_supported=True,
                         portable_providers={"hookshot.player-observation": 1}).mode, "reject")

    def test_corrupted_payload(self):
        self.write()
        self.rewrite(lambda entries: entries.update({"exact.bin": b"changed"}))
        with self.assertRaises(cp.CheckpointError):
            cp.read_checkpoint(self.path)

    def test_unknown_duplicate_and_traversal_entries(self):
        for name in ("../outside", "unknown.json", "portable.json"):
            self.write()
            with zipfile.ZipFile(self.path, "a") as archive:
                archive.writestr(name, b"x")
            with self.assertRaises(cp.CheckpointError):
                cp.read_checkpoint(self.path)

    def test_nonfinite_json_and_duplicate_keys(self):
        for data in ({"x": float("nan")}, {"x": float("inf")}):
            with self.assertRaises(cp.CheckpointError):
                self.write(replace(self.checkpoint, portable=data))
        for raw in (b'{"x":1,"x":2}', b'{"x":1e999}', b'{"x":NaN}'):
            with self.assertRaises(cp.CheckpointError):
                cp._json(raw)

    def test_limits_and_compression(self):
        with self.assertRaises(cp.CheckpointError):
            self.write(replace(self.checkpoint, portable={"x": "x" * cp.MAX_PORTABLE}))
        self.write()
        with patch.object(cp, "MAX_EXACT", 2):
            with self.assertRaises(cp.CheckpointError):
                cp.read_checkpoint(self.path)
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", b"{}")
            archive.writestr("portable.json", b"{}")
        with self.assertRaises(cp.CheckpointError):
            cp.read_checkpoint(self.path)

    def test_atomic_failure_preserves_previous(self):
        self.write()
        previous = self.path.read_bytes()
        with patch.object(cp.os, "replace", side_effect=OSError("injected rename failure")):
            with self.assertRaises(OSError):
                self.write(replace(self.checkpoint, exact=b"new fixture"))
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob(".hookshot-checkpoint-*")), [])

    def test_bad_manifest_identity_and_schema(self):
        for field, value in (("schema", True), ("schema", 2), ("identity", []), ("provider_schema", True)):
            self.write()
            def change(entries):
                manifest = json.loads(entries["manifest.json"])
                manifest[field] = value
                entries["manifest.json"] = json.dumps(manifest).encode()
            self.rewrite(change)
            with self.assertRaises(cp.CheckpointError):
                cp.read_checkpoint(self.path)

    def test_full_nso_build_id_is_preserved(self):
        for digits in (2, 32, 40, 62, 64):
            identity = replace(self.identity, game_build_id="a" * digits)
            loaded = self.write(replace(self.checkpoint, identity=identity))
            self.assertEqual(loaded.identity.game_build_id, "a" * digits)
        for invalid in ("", "a" * 39, "a" * 66, "A" * 64):
            with self.assertRaises(cp.CheckpointError):
                self.write(replace(self.checkpoint, identity=replace(self.identity, game_build_id=invalid)))


if __name__ == "__main__":
    unittest.main()
