"""Companion state transitions, waypoint durability and read-only transport."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import longshot_journal as journal


def event(frame=1, **changes):
    sample = dict(map="KokiriForest", pos=[1, 2, 3], age="child", frame=frame,
                  life=12, max_life=12, rupees=10, facing=45, loading=False, event=False,
                  flags={journal.TOKEN: 3, journal.PIECES: 1})
    sample.update(changes)
    return dict(event="oot", game=sample)


class JournalTests(unittest.TestCase):
    def test_unknown_fields_stay_unknown_and_invalid_samples_do_not_become_live(self):
        self.assertIsNone(journal.sample_of(event(loading=True)))
        self.assertIsNone(journal.sample_of(event(event=None)))
        self.assertIsNone(journal.sample_of(event(pos=[0, float("nan"), 1])))
        self.assertIsNone(journal.sample_of(event(map="../outside")))
        self.assertIsNone(journal.sample_of(event(frame=True)))
        sample = journal.sample_of(event(life=None, rupees=float("inf"), flags={journal.TOKEN: True}))
        self.assertIsNone(sample["life"])
        self.assertIsNone(sample["rupees"])
        self.assertIsNone(sample["tokens"])
        self.assertAlmostEqual(journal.sample_of(event(facing=-57.6))["facing"], 302.4)

    def test_stale_duplicate_and_rewind(self):
        model = journal.Journal()
        model.ingest(event(), now=1)
        self.assertTrue(model.live(now=2))
        self.assertFalse(model.ingest(event(), now=4))
        self.assertFalse(model.live(now=4))
        model.ingest(event(5, flags={journal.TOKEN: 4}), now=5)
        self.assertFalse(any("tokens: 4" in f for f in model.feed))
        model.ingest(event(2, flags={journal.TOKEN: 5}), now=6)
        self.assertEqual(len(model.feed), 1)
        self.assertTrue(model.live(now=6))

    def test_pickups_drop_and_pause_do_not_guess_locations(self):
        model = journal.Journal()
        model.ingest(event(), now=1)
        model.ingest(event(2, flags={journal.TOKEN: 4}), now=1.1)
        self.assertIn("Gold Skulltula tokens: 4", model.feed)
        model.ingest(event(3, flags={journal.TOKEN: 2}), now=1.2)
        self.assertIn("previous save", model.feed[0])
        model.ingest(event(4, loading=True), now=1.3)
        self.assertFalse(model.live(now=1.3))
        model.ingest(event(5, flags={journal.TOKEN: 10}), now=1.4)
        self.assertFalse(any("tokens: 10" in f for f in model.feed))

    def test_area_age_teleport_and_floor_changes_break_trail(self):
        model = journal.Journal()
        for frame, pos in enumerate(([1, 2, 3], [2, 2, 3], [100, 2, 3], [101, 12, 3]), 1):
            model.ingest(event(frame, pos=list(pos)), now=frame / 10)
        route = list(model.trails[("KokiriForest", "child")])
        self.assertEqual(route.count(None), 2)
        model.ingest(event(5, age="adult"), now=.5)
        self.assertEqual(len(model.trails), 2)
        model.ingest(event(6), now=.6)
        self.assertIsNone(list(model.trails[("KokiriForest", "child")])[-2])
        model.disconnect()
        self.assertFalse(model.live(now=.7))
        self.assertFalse(model.trails)

    def test_memory_is_bounded(self):
        model = journal.Journal()
        for i in range(1500):
            model.ingest(event(i, pos=[i, 0, 0]), now=i / 10)
        self.assertEqual(len(model.trails[("KokiriForest", "child")]), 1200)
        for i in range(12):
            model.ingest(event(2000 + i, map=f"Area{i}"), now=200 + i / 10)
        self.assertEqual(len(model.trails), 8)
        self.assertLessEqual(len(model.feed), 24)

    def test_waypoints_profile_isolation_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            first = journal.Waypoints(Path(folder) / "profile-3.json")
            second = journal.Waypoints(Path(folder) / "profile-4.json")
            sample = journal.sample_of(event())
            first.add(sample, "Return with the bow")
            reloaded = journal.Waypoints(first.path)
            self.assertEqual(reloaded.items, first.items)
            self.assertEqual(second.items, [])
            reloaded.remove(first.items[0]["id"])
            self.assertEqual(journal.Waypoints(first.path).items, [])

    def test_failed_write_preserves_previous_file_and_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            notes = journal.Waypoints(Path(folder) / "notes.json")
            notes.add(journal.sample_of(event()), "First")
            old_bytes, old_items = notes.path.read_bytes(), deepcopy(notes.items)
            with patch.object(journal.os, "replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    notes.add(journal.sample_of(event()), "Second")
            self.assertEqual(notes.path.read_bytes(), old_bytes)
            self.assertEqual(notes.items, old_items)
            self.assertEqual(list(Path(folder).iterdir()), [notes.path])

    def test_second_window_cannot_overwrite_newer_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.json"
            first, second = journal.Waypoints(path), journal.Waypoints(path)
            first.add(journal.sample_of(event()), "First window")
            with self.assertRaisesRegex(ValueError, "another window"):
                second.add(journal.sample_of(event()), "Stale window")
            self.assertEqual(journal.Waypoints(path).items[0]["label"], "First window")

    def test_corrupt_file_not_overwritten_and_labels_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.json"
            path.write_text('{"schema":99}', encoding="utf-8")
            with self.assertRaises(ValueError):
                journal.Waypoints(path)
            self.assertEqual(path.read_text(), '{"schema":99}')
            notes = journal.Waypoints(Path(folder) / "new.json")
            for label in ("", "a" * 81, "line\nbreak"):
                with self.assertRaises(ValueError):
                    notes.add(journal.sample_of(event()), label)
            self.assertFalse(notes.path.exists())

    def test_reader_only_subscribes_and_closes_its_connection(self):
        sent, closed = [], []
        reader = journal.Reader("private-test")
        class FakeBridge:
            def __init__(self, endpoint, timeout):
                self.calls = 0
                self.endpoint = endpoint
            def send(self, message):
                sent.append(message)
            def line(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    return dict(id=1, ok=True)
                if self.calls == 2:
                    return event()
                reader.stop.set()
                return None
            def close(self):
                closed.append(self.endpoint)
        with patch.object(journal, "Bridge", FakeBridge):
            reader.run()
        self.assertEqual([m["cmd"] for m in sent], ["subscribe"])
        self.assertEqual(sent[0]["events"], ["oot"])
        self.assertNotIn("changes", sent[0])
        self.assertEqual(closed, ["private-test"])
        sample = reader.messages.get_nowait()
        self.assertLessEqual(sample["_received"], time.monotonic())
        model = journal.Journal()
        model.ingest(sample, now=sample["_received"])
        self.assertFalse(model.live(now=sample["_received"] + 10))


if __name__ == "__main__":
    unittest.main()
