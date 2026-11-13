"""Save import transaction failures, profile isolation and launcher environment."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import longshot_launcher_core as core


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.source = self.root / "source" / ("a" * 32)
        (self.source / "slot_00").mkdir(parents=True)
        for relative in ("account.sav", "option.sav", "slot_00/progress.sav", "slot_00/caption.sav"):
            (self.source / relative).write_bytes(relative.encode())
        self.processes = patch.object(core.oot_saves, "running_games", return_value=[]).start()
        self.addCleanup(patch.stopall)

    def test_import_preserves_source_and_original_profile(self):
        original = self.game / "user" / "save" / "sentinel"
        original.parent.mkdir(parents=True)
        original.write_text("original")
        report = core.import_save(self.source, self.game, 3)
        target = core.profile_folder(self.game, 3) / "save" / self.source.name
        self.assertEqual(report["slots"], ["slot_00"])
        self.assertEqual(original.read_text(), "original")
        for p in self.source.rglob("*.sav"):
            self.assertEqual((target / p.relative_to(self.source)).read_bytes(), p.read_bytes())
        (target / "slot_00/progress.sav").write_bytes(b"new progress")
        self.assertEqual((self.source / "slot_00/progress.sav").read_bytes(), b"slot_00/progress.sav")

    def test_rejects_existing_profile_and_original(self):
        for number in (1, 2):
            target = core.profile_folder(self.game, number)
            target.mkdir(parents=True)
            with self.assertRaises(ValueError):
                core.import_save(self.source, self.game, number)
            self.assertEqual(list(target.iterdir()), [])

    def test_rejects_incomplete_or_oversized_save_before_reserving_profile(self):
        p = self.source / "slot_00/progress.sav"
        p.unlink()
        with self.assertRaises(OSError):
            core.import_save(self.source, self.game, 2)
        self.assertFalse(core.profile_folder(self.game, 2).exists())
        p.write_bytes(b"x" * (core.LIMITS[p.name] + 1))
        with self.assertRaises(ValueError):
            core.import_save(self.source, self.game, 2)

    def test_cleanup_on_failed_publication(self):
        with patch.object(Path, "rename", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                core.import_save(self.source, self.game, 2)
        self.assertFalse(core.profile_folder(self.game, 2).exists())
        self.assertEqual((self.source / "account.sav").read_bytes(), b"account.sav")

    def test_stops_if_game_starts_during_import(self):
        self.processes.side_effect = [[], ["Hookshot"]]
        with self.assertRaisesRegex(ValueError, "close the game"):
            core.import_save(self.source, self.game, 2)
        self.assertFalse(core.profile_folder(self.game, 2).exists())

    def test_linked_save_is_not_imported(self):
        target = self.source / "slot_00/progress.sav"
        outside = self.root / "outside.sav"
        outside.write_bytes(b"outside")
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            core.import_save(self.source, self.game, 2)
        self.assertFalse(core.profile_folder(self.game, 2).exists())

    def test_linked_profile_parent_is_not_written(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.game / "user").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            core.import_save(self.source, self.game, 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_launch_isolates_profile_and_optional_modes(self):
        exe = self.game / ("hookshot.exe" if os.name == "nt" else "hookshot")
        exe.touch()
        (self.game / "image.bin").touch()
        assets = self.root / "assets"
        assets.mkdir()
        with patch.dict(os.environ, {"HOS_COOP": "1", "HOS_FS_OVERLAY": "other-seed", "HOS_SAVE_PROFILE": "9"}):
            command, env = core.launch_plan(self.game, 2, assets)
        self.assertEqual(command[-2:], ["--user", str(core.profile_folder(self.game, 2).resolve())])
        self.assertIn(str(assets.resolve()), command)
        self.assertEqual(env["HOS_COOP"], "0")
        self.assertNotIn("HOS_FS_OVERLAY", env)
        self.assertFalse(core.profile_folder(self.game, 2).exists())

    def test_invalid_profile_never_defaults_to_original(self):
        for number in (0, 10, "2", True):
            with self.assertRaises(ValueError):
                core.profile_folder(self.game, number)

    def test_first_launch_creates_profile_parents_before_start(self):
        (self.game / ("hookshot.exe" if os.name == "nt" else "hookshot")).touch()
        (self.game / "image.bin").touch()
        (self.game / "romfs").mkdir()
        def started(command, **kwargs):
            user = Path(command[-1])
            self.assertTrue(user.is_dir())
            self.assertEqual(user.name, "profile-4")
            self.assertFalse((self.game / "user/save").exists())
            (user / "startup-marker").write_text("isolated")
            return "child"
        with patch.object(core.subprocess, "Popen", side_effect=started):
            self.assertEqual(core.start_game(self.game, 4), "child")
        self.assertEqual((core.profile_folder(self.game, 4) / "startup-marker").read_text(), "isolated")

    def test_ocarina_recomp_portuguese_save_layout(self):
        path = self.root / "ocarina" / "perfil" / "save" / self.source.name
        path.mkdir(parents=True)
        (path / "account.sav").write_bytes(b"account")
        self.assertIn(str(path), core.oot_saves.find_saves(str(self.root / "ocarina")).values())

    def test_hardware_advice_does_not_claim_unknown_gpu_support(self):
        names = [row[0] for row in core.recommendations({})]
        self.assertNotIn("Upscaling", names)
        rows = core.recommendations({"gpus": [{"name": "NVIDIA GeForce RTX 5070 Ti"}], "ram_gib": 64})
        self.assertIn("Try DLSS Quality if GPU-limited", [r[1] for r in rows])
        self.assertNotIn("Memory", [r[0] for r in rows])


if __name__ == "__main__":
    unittest.main()
