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

    def test_journal_launch_uses_private_endpoint_and_preserves_parent_environment(self):
        (self.game / ("hookshot.exe" if os.name == "nt" else "hookshot")).touch()
        (self.game / "image.bin").touch()
        (self.game / "romfs").mkdir()
        inherited = {"HOS_CONTROL": "other-game", "HOS_CONTROL_MEM": "rw", "HOS_INPUT_SCRIPT": "A",
                     "HOS_INPUT_EXCLUSIVE": "1"}
        with patch.dict(os.environ, inherited), patch.object(core.subprocess, "Popen") as started:
            core.start_game(self.game, 3, journal_endpoint="longshot-journal-test")
            command, env = started.call_args.args[0], started.call_args.kwargs["env"]
            self.assertEqual(env["HOS_CONTROL"], "longshot-journal-test")
            self.assertEqual(env["HOS_CONTROL_MEM"], "0")
            self.assertNotIn("HOS_INPUT_SCRIPT", env)
            self.assertNotIn("HOS_INPUT_EXCLUSIVE", env)
            self.assertEqual(Path(command[-1]).resolve(), core.profile_folder(self.game, 3).resolve())
            self.assertEqual({key: os.environ[key] for key in inherited}, inherited)

    def test_hardware_advice_does_not_claim_unknown_gpu_support(self):
        names = [row[0] for row in core.recommendations({})]
        self.assertNotIn("Upscaling", names)
        rows = core.recommendations({"gpus": [{"name": "NVIDIA GeForce RTX 5070 Ti"}], "ram_gib": 64})
        self.assertIn("Try DLSS Quality if GPU-limited", [r[1] for r in rows])
        self.assertNotIn("Memory", [r[0] for r in rows])

    def coop_fixture(self):
        (self.game / ("hookshot.exe" if os.name == "nt" else "hookshot")).touch()
        (self.game / "image.bin").touch()
        (self.game / "romfs").mkdir()
        (self.game / "hookshot_coop.dll").touch()
        pack = self.game / "mods/contents/0400486024DEC000/coop-puppet"
        (pack / "romfs").mkdir(parents=True)
        (pack / "coop_hud").mkdir()
        for name in ("coop_puppet.json", "coop_rooms.txt", "coop_hud/hud.json", ".longshot-disabled"):
            (pack / name).touch()
        return pack

    def test_coop_plan_isolates_profile_and_secret_and_clears_inherited_modes(self):
        pack = self.coop_fixture()
        with patch.dict(os.environ, {"HOS_FS_OVERLAY": "randomizer", "LICHII_COOP_TEST_PUPPET": "1",
                                     "LICHII_COOP_CHEATS": "1", "LICHII_COOP_SERVER": "wrong-server"}):
            command, env = core.coop_launch_plan(self.game, 3, "127.0.0.1", 27510, "Link", "test-only")
        self.assertEqual(Path(command[-1]).resolve(), core.profile_folder(self.game, 3).resolve())
        self.assertNotIn("test-only", command)
        self.assertEqual(env["LICHII_COOP_PASSWORD"], "test-only")
        self.assertEqual(env["LICHII_COOP_SERVER"], "127.0.0.1")
        self.assertNotIn("HOS_FS_OVERLAY", env)
        self.assertEqual(Path(env["HOS_MODS"]).resolve(), pack.parent.resolve())
        self.assertEqual(env["HOS_COOP"], "1")
        self.assertEqual(env["LICHII_COOP_CHEATS"], "0")
        self.assertNotIn("LICHII_COOP_TEST_PUPPET", env)
        self.assertFalse(core.profile_folder(self.game, 3).exists())
        self.assertTrue((pack / ".longshot-disabled").exists())

    def test_coop_refuses_original_profile_bad_addresses_and_secrets(self):
        self.coop_fixture()
        valid = [self.game, 2, "localhost", 27510, "Link", "test-only"]
        for index, value in ((1, 1), (2, "https://host"), (2, "host:27510"), (2, "::1"),
                             (3, 0), (3, 65536), (3, True), (4, ""), (4, "x" * 17),
                             (4, "bad\nname"), (5, ""), (5, "x" * 129), (5, "é" * 65), (5, "secret\n")):
            args = valid.copy()
            args[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                core.coop_launch_plan(*args)
        self.assertFalse((self.game / "user").exists())

    def test_coop_refuses_a_pack_active_in_ordinary_play(self):
        pack = self.coop_fixture()
        (pack / ".longshot-disabled").unlink()
        with self.assertRaisesRegex(ValueError, "Disable the coop-puppet"):
            core.coop_launch_plan(self.game, 2, "localhost", 27510, "Link", "test-only")

    def test_coop_refuses_missing_module_or_pack_metadata(self):
        pack = self.coop_fixture()
        module = self.game / "hookshot_coop.dll"
        module.unlink()
        with self.assertRaisesRegex(ValueError, "module"):
            core.coop_launch_plan(self.game, 2, "localhost", 27510, "Link", "test-only")
        module.touch()
        (pack / "coop_rooms.txt").unlink()
        with self.assertRaisesRegex(ValueError, "puppet pack"):
            core.coop_launch_plan(self.game, 2, "localhost", 27510, "Link", "test-only")


if __name__ == "__main__":
    unittest.main()
