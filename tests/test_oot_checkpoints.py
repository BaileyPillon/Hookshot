"""Game-free coverage of the native slot checkpoint CLI and its write boundary."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import oot_checkpoints as checkpoints
from hookshot_checkpoint import CheckpointError
from hookshot_statefile import read_state, write_state

PROFILE = "a" * 32


class NativeCheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / "game"
        self.exefs = self.game / ".hookshot_exefs"
        self.exefs.mkdir(parents=True)
        self.exe = self.game / ("hookshot.exe" if os.name == "nt" else "hookshot")
        self.exe.write_bytes(b"fixture executable")
        (self.game / "image.bin").write_bytes(b"fixture game image")
        header = b"NSO0" + bytes(0x3c) + b"\xba" * 20 + bytes(12)
        (self.exefs / "main").write_bytes(header)
        npdm = bytearray(0x100)
        npdm[:4] = b"META"
        npdm[0x70:0x74] = (0x80).to_bytes(4, "little")
        npdm[0x80:0x84] = b"ACI0"
        npdm[0x90:0x98] = int(checkpoints.PROGRAM, 16).to_bytes(8, "little")
        (self.exefs / "main.npdm").write_bytes(npdm)
        self.user = self.game / "user"
        self.profile = self.user / "save" / PROFILE
        self.slot = self.profile / "slot_03"
        self.slot.mkdir(parents=True)
        (self.profile / "account.sav").write_bytes(b"account")
        (self.profile / "option.sav").write_bytes(b"settings")
        (self.slot / "progress.sav").write_bytes(b"earlier progress")
        (self.slot / "caption.sav").write_bytes(b"earlier caption")
        other_slot = self.profile / "slot_00"
        other_slot.mkdir()
        (other_slot / "progress.sav").write_bytes(b"a different slot")
        (other_slot / "caption.sav").write_bytes(b"other caption")
        os.utime(other_slot / "progress.sav", (10, 10))
        self.archive = self.root / "quicksave.hsc"
        self.destination = self.root / "restored user"

    def capture(self):
        with patch.object(checkpoints, "running_games", return_value=[]):
            return checkpoints.capture(self.game, self.user, None, None, self.archive)

    def test_reopen_original_progress_in_independent_profile(self):
        self.assertEqual(self.capture().slot, "slot_03")
        (self.slot / "progress.sav").write_bytes(b"later progress")
        self.exe.write_bytes(b"a compatible recompile")
        checkpoints.prepare(self.game, self.archive, self.destination)
        restored = self.destination / "save" / PROFILE
        self.assertEqual((restored / "slot_03" / "progress.sav").read_bytes(), b"earlier progress")
        self.assertEqual((restored / "slot_03" / "caption.sav").read_bytes(), b"earlier caption")
        self.assertEqual((restored / "option.sav").read_bytes(), b"settings")
        self.assertFalse((restored / "slot_00").exists())
        self.assertEqual((self.slot / "progress.sav").read_bytes(), b"later progress")

    def test_wrong_slot_profile_or_game_image_refuses_before_writing(self):
        self.capture()
        for options in ({"slot": "0"}, {"profile": "b" * 32}):
            with self.assertRaises(CheckpointError):
                checkpoints.prepare(self.game, self.archive, self.destination, **options)
            self.assertFalse(self.destination.exists())
        (self.game / "image.bin").write_bytes(b"different image")
        with self.assertRaises(CheckpointError):
            checkpoints.prepare(self.game, self.archive, self.destination)
        self.assertFalse(self.destination.exists())

    def test_existing_profile_and_interrupted_staging(self):
        self.capture()
        with self.assertRaises(FileExistsError):
            checkpoints.prepare(self.game, self.archive, self.user)
        self.assertEqual((self.slot / "progress.sav").read_bytes(), b"earlier progress")
        with patch.object(checkpoints.os, "fsync", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                checkpoints.prepare(self.game, self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        checkpoints.prepare(self.game, self.archive, self.destination)

    def test_corrupt_or_path_bearing_archive_refuses_before_writing(self):
        self.capture()
        info = read_state(self.archive)
        payload = info.portable
        payload["files"]["../outside.sav"] = "YQ=="
        write_state(self.archive, identity=info.identity, provider=info.provider, provider_schema=info.provider_schema,
                    binding=info.binding, portable=payload)
        with self.assertRaises(CheckpointError):
            checkpoints.prepare(self.game, self.archive, self.destination)
        self.capture()
        data = bytearray(self.archive.read_bytes())
        data[-1] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaises(CheckpointError):
            checkpoints.prepare(self.game, self.archive, self.destination)
        self.assertFalse(self.destination.exists())

    def test_running_game_blocks_capture(self):
        with patch.object(checkpoints, "running_games", return_value=["Hookshot"]):
            with self.assertRaisesRegex(CheckpointError, "close the running game"):
                checkpoints.capture(self.game, self.user, PROFILE, "3", self.archive)
        self.assertFalse(self.archive.exists())

    def test_cli_discovery_and_prepare(self):
        self.capture()
        args = [sys.executable, "-I", "-B", str(ROOT / "scripts/oot_checkpoints.py"), "--game", str(self.game)]
        listed = subprocess.run([*args, "slots", "--user", str(self.user)], check=True, capture_output=True, text=True)
        self.assertIn(f"{PROFILE}  slot_03 slot_00", listed.stdout)
        subprocess.run([*args, "prepare", str(self.archive), "--new-user", str(self.destination)],
                       check=True, capture_output=True, text=True)
        self.assertTrue((self.destination / "save" / PROFILE / "slot_03" / "progress.sav").is_file())


if __name__ == "__main__":
    unittest.main()
