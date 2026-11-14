"""SPDX-License-Identifier: GPL-3.0-or-later
Streaming two-path storage, immutable worker writes and fail-closed runtime preflight. No game.
"""
from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import hookshot_statefile as sf
from hookshot_checkpoint import CheckpointError, Identity


class StatefileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="hookshot-state-")
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "synthetic.hsc"
        self.identity = Identity("0400486024dec000", "a" * 40, "fixture", "b" * 64,
                                 "fixture-x86_64", 1, "c" * 64, "d" * 64)
        self.binding = sf.SaveBinding("fixture-profile", "fixture-save", "slot-a")
        self.context = sf.ExactContext(0x1000, 0x2000, "1" * 64, "2" * 64, "3" * 64)
        self.capture = dict(identity=self.identity, provider="fixture.progress", provider_schema=1,
                            binding=self.binding, portable={"scene": "fixture", "progress": {"flag": True}},
                            exact_context=self.context, exact_blocks=(b"owned-snapshot", b"second-block"))

    def write(self, **changes):
        sf.write_state(self.path, **dict(self.capture, **changes))
        return sf.read_state(self.path)

    def plan(self, info, **changes):
        args = dict(binding=self.binding, context=self.context, exact_supported=True,
                    portable_providers={"fixture.progress": 1})
        args.update(changes)
        return sf.choose_restore(info, self.identity, **args)

    def chunks(self):
        data = self.path.read_bytes()
        count = sf.HEADER.unpack_from(data)[2]
        offset, chunks = sf.HEADER.size, []
        for _ in range(count):
            tag, flags, size, checksum = sf.CHUNK.unpack_from(data, offset)
            start = offset + sf.CHUNK.size
            chunks.append((tag, offset, start, size))
            offset = start + size
        return data, chunks

    def corrupt(self, wanted):
        data, chunks = self.chunks()
        data = bytearray(data)
        for tag, _, start, size in chunks:
            if tag == wanted:
                self.assertGreater(size, 0)
                data[start] ^= 1
                self.path.write_bytes(data)
                return
        self.fail("fixture chunk not found")

    def test_roundtrip_and_exact_staging(self):
        info = self.write()
        self.assertEqual(info.portable, self.capture["portable"])
        self.assertEqual(info.exact_blocks, 2)
        self.assertEqual(self.plan(info).mode, "exact")
        output = Path(self.folder.name) / "staged.bin"
        self.assertEqual(sf.stage_exact(self.path, output), info)
        self.assertEqual(output.read_bytes(), b"".join(self.capture["exact_blocks"]))
        with self.assertRaises(CheckpointError):
            sf.stage_exact(self.path, self.path)

    def test_native_binding_digest_is_unambiguous_and_stable(self):
        info = self.write()
        self.assertEqual(info.binding.digest(), self.binding.digest())
        self.assertEqual(len(self.binding.digest()), 32)
        self.assertNotEqual(sf.SaveBinding("ab", "c", "slot").digest(),
                            sf.SaveBinding("a", "bc", "slot").digest())

    def test_all_exact_runtime_signatures_are_required(self):
        info = self.write()
        for key, value in (("code_anchor", 0x3000), ("guest_base", 0x4000),
                           ("layout_sha256", "4" * 64), ("threads_sha256", "5" * 64),
                           ("resources_abi_sha256", "6" * 64)):
            self.assertEqual(self.plan(info, context=replace(self.context, **{key: value})).mode, "portable")
        for value in (None, self.context):
            self.assertEqual(self.plan(info, context=value, exact_supported=False).mode, "portable")
        self.assertEqual(self.plan(info, context=None, portable_providers={}).mode, "reject")
        self.assertEqual(self.plan(info, exact_supported="false").mode, "portable")

    def test_changed_build_uses_explicit_portable_provider(self):
        info = self.write()
        for changes in (dict(runtime_build="new"), dict(runtime_sha256="e" * 64),
                        dict(platform="other"), dict(state_abi=2)):
            current = replace(self.identity, **changes)
            args = dict(binding=self.binding, context=self.context, exact_supported=True)
            self.assertEqual(sf.choose_restore(info, current, **args).mode, "reject")
            self.assertEqual(sf.choose_restore(info, current, **args,
                             portable_providers={"fixture.progress": 1}).mode, "portable")
        for schema in (True, 2, "1"):
            self.assertEqual(self.plan(info, exact_supported=False,
                             portable_providers={"fixture.progress": schema}).mode, "reject")

    def test_other_games_mods_and_save_slots_reject(self):
        info = self.write()
        for changes in (dict(program_id="0" * 16), dict(game_build_id="b" * 40),
                        dict(mod_set_sha256="0" * 64), dict(config_sha256="0" * 64)):
            self.assertEqual(sf.choose_restore(info, replace(self.identity, **changes), binding=self.binding,
                             context=self.context, exact_supported=True,
                             portable_providers={"fixture.progress": 1}).mode, "reject")
        for key in ("profile", "save_data", "slot"):
            self.assertEqual(self.plan(info, binding=replace(self.binding, **{key: "other"})).mode, "reject")
        info = self.write(provider="hookshot.player-observation")
        self.assertEqual(self.plan(info, portable_providers={info.provider: 1}).mode, "reject")

    def test_corrupt_exact_keeps_portable_and_preserves_previous_staging(self):
        self.write()
        self.corrupt(b"EXAC")
        info = sf.read_state(self.path)
        self.assertIsNotNone(info.exact_error)
        self.assertEqual(self.plan(info).mode, "portable")
        self.assertEqual(self.plan(info, portable_providers={}).mode, "reject")
        output = Path(self.folder.name) / "staged.bin"
        output.write_bytes(b"previous")
        with self.assertRaises(CheckpointError):
            sf.stage_exact(self.path, output)
        self.assertEqual(output.read_bytes(), b"previous")
        self.assertEqual(list(output.parent.glob(".hookshot-exact-*")), [])

    def test_portable_or_metadata_corruption_rejects_whole_state(self):
        for tag in (b"META", b"PORT"):
            self.write()
            self.corrupt(tag)
            with self.assertRaises(CheckpointError):
                sf.read_state(self.path)

    def test_unknown_optional_chunks_and_unknown_required_rejection(self):
        for flag in (0, sf.REQUIRED):
            self.write()
            data = bytearray(self.path.read_bytes())
            struct.pack_into("<I", data, 12, 5)
            content = b"future optional description"
            data += sf.CHUNK.pack(b"FUTR", flag, len(content), sf._checksum(4, b"FUTR", flag, content)) + content
            self.path.write_bytes(data)
            if flag:
                with self.assertRaises(CheckpointError):
                    sf.read_state(self.path)
            else:
                self.assertEqual(sf.read_state(self.path).optional_tags, ("FUTR",))

    def test_truncation_trailing_data_and_size_bounds(self):
        self.write()
        data, chunks = self.chunks()
        cuts = {0, 7, 15, len(data) - 1}
        for _, offset, start, size in chunks:
            cuts.update((offset, start - 1, start, start + size - 1))
        for cut in cuts:
            self.path.write_bytes(data[:cut])
            with self.assertRaises(CheckpointError):
                sf.read_state(self.path)
        self.path.write_bytes(data + b"trailer")
        with self.assertRaises(CheckpointError):
            sf.read_state(self.path)
        bad = bytearray(data)
        struct.pack_into("<Q", bad, chunks[2][1] + 8, sf.BLOCK + 1)
        self.path.write_bytes(bad)
        with self.assertRaises(CheckpointError):
            sf.read_state(self.path)
        for count in (0, sf.MAX_CHUNKS + 1):
            self.path.write_bytes(sf.HEADER.pack(sf.MAGIC, sf.VERSION, count))
            with self.assertRaises(CheckpointError):
                sf.read_state(self.path)

    def test_missing_exact_context_and_unbound_slots_never_write(self):
        for changes in (dict(exact_context=None), dict(binding=sf.SaveBinding("", "save", "a")),
                        dict(binding=sf.SaveBinding("profile", "../save", "a")),
                        dict(exact_context=replace(self.context, code_anchor=0)),
                        dict(exact_blocks=(bytearray(b"mutable"),)),
                        dict(portable={"bad": float("nan")})):
            with self.assertRaises(CheckpointError):
                self.write(**changes)
            self.assertFalse(self.path.exists())
        info = self.write(exact_context=None, exact_blocks=())
        self.assertEqual(self.plan(info).mode, "portable")

    def test_streamed_capture_and_inspection_have_bounded_reads(self):
        def blocks():
            for index in range(3):
                yield bytes([index]) * sf.BLOCK
        info = self.write(exact_blocks=blocks())
        original = sf._read
        reads = []
        def bounded(stream, size):
            reads.append(size)
            self.assertLessEqual(size, sf.BLOCK)
            return original(stream, size)
        with patch.object(sf, "_read", side_effect=bounded):
            self.assertEqual(sf.read_state(self.path), info)
        self.assertEqual(info.exact_bytes, 3 * sf.BLOCK)
        self.assertEqual(reads.count(sf.BLOCK), 3)

    def test_complete_portable_progress_can_exceed_legacy_limit(self):
        progress = {"native-progress": "x" * (128 * 1024)}
        info = self.write(portable=progress, exact_context=None, exact_blocks=())
        self.assertEqual(info.portable, progress)
        self.assertEqual(self.plan(info).mode, "portable")
        with patch.object(sf, "MAX_PORTABLE", 32):
            with self.assertRaises(CheckpointError):
                self.write(portable=progress)

    def test_failed_capture_and_atomic_replace_preserve_previous_state(self):
        self.write()
        previous = self.path.read_bytes()
        def broken():
            yield b"owned"
            raise OSError("injected capture error")
        with self.assertRaises(OSError):
            self.write(exact_blocks=broken())
        self.assertEqual(self.path.read_bytes(), previous)
        with patch.object(sf.os, "replace", side_effect=OSError("injected atomic rename failure")):
            with self.assertRaises(OSError):
                self.write(portable={"different": "state"})
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob(".hookshot-state-*")), [])

    def test_exact_block_reordering_disables_exact_restore(self):
        self.write()
        data, chunks = self.chunks()
        first, second = chunks[2], chunks[3]
        swapped = data[:first[1]] + data[second[1]:] + data[first[1]:second[1]]
        self.path.write_bytes(swapped)
        info = sf.read_state(self.path)
        self.assertIsNotNone(info.exact_error)
        self.assertEqual(self.plan(info).mode, "portable")

    def test_post_commit_durability_failure_is_distinct(self):
        with patch.object(sf, "_parent_sync", side_effect=OSError("injected directory flush failure")):
            with self.assertRaises(sf.CommittedStateError) as error:
                self.write()
        self.assertTrue(error.exception.committed)
        self.assertEqual(sf.read_state(self.path).binding, self.binding)

    def test_background_writer_is_single_flight_and_freezes_portable_values(self):
        entered, release = threading.Event(), threading.Event()
        original = sf.write_state
        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("fixture worker timed out")
            return original(*args, **kwargs)
        writer = sf.StateWriter()
        try:
            with patch.object(sf, "write_state", side_effect=slow):
                self.assertTrue(writer.submit(self.path, **self.capture))
                self.assertTrue(entered.wait(5))
                self.assertEqual(writer.poll(), "writing")
                self.assertFalse(writer.submit(self.path, **self.capture))
                self.capture["portable"]["scene"] = "changed-after-capture"
                release.set()
                deadline = time.monotonic() + 5
                result = writer.poll()
                while result == "writing" and time.monotonic() < deadline:
                    time.sleep(0.01)
                    result = writer.poll()
                self.assertEqual(result, "saved")
                self.assertEqual(sf.read_state(self.path).portable["scene"], "fixture")
                self.assertIsNone(writer.poll())
        finally:
            release.set()
            writer.close()
        self.assertFalse(writer.submit(self.path, **self.capture))

    def test_worker_errors_are_reported_and_close_drains_ownership(self):
        writer = sf.StateWriter()
        with patch.object(sf, "write_state", side_effect=OSError("injected write failure")):
            self.assertTrue(writer.submit(self.path, **self.capture))
            writer.close()
        self.assertIsInstance(writer.poll(), OSError)
        self.assertIsNone(writer.poll())
        self.assertFalse(self.path.exists())

    def test_cli_inspects_v2_without_exposing_a_restore_command(self):
        self.write()
        result = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/hookshot_dev.py"),
                                 "checkpoint-inspect", str(self.path)], capture_output=True, text=True, check=True)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], 2)
        self.assertEqual(output["binding"]["slot"], "slot-a")
        self.assertEqual(output["exact_blocks"], 2)


if __name__ == "__main__":
    unittest.main()
