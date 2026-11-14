"""Native save copy failure recovery on Windows and Linux; synthetic files only."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('save_transactions_subject', ROOT / 'scripts/oot_saves.py')
oot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oot)


def contents(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class Transactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='longshot-save-transaction-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target, self.backup = [self.root / n for n in ('source', 'target', 'backups/old')]
        for folder, tag in ((self.source, b'new'), (self.target, b'old')):
            (folder / 'slot_00').mkdir(parents=True)
            (folder / 'slot_00/progress.sav').write_bytes(tag + b'-progress')
            (folder / 'slot_00/caption.sav').write_bytes(tag + b'-caption')
            (folder / 'account.sav').write_bytes(tag + b'-account')
            (folder / 'option.sav').write_bytes(tag + b'-options')
        self.before = contents(self.target)

    def copy(self, keep_settings=False, dry_run=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            oot.copy_saves(str(self.source), str(self.target), str(self.backup), keep_settings, dry_run)
        return output.getvalue()

    def assert_old_intact(self):
        self.assertEqual(contents(self.target), self.before)
        self.assertFalse(any(p.name.startswith('.') for p in self.target.iterdir()))
        self.assertEqual(contents(self.backup), self.before)

    def test_partial_slot_copy_preserves_old_save(self):
        original = shutil.copytree
        def fail(source, destination, *args, **kw):
            if Path(source).parent == self.source:
                Path(destination).mkdir(parents=True)
                (Path(destination) / 'progress.sav').write_bytes(b'partial')
                raise OSError(28, 'disk full')
            return original(source, destination, *args, **kw)
        with mock.patch.object(oot.shutil, 'copytree', side_effect=fail), self.assertRaises(OSError):
            self.copy()
        self.assert_old_intact()

    def test_loose_file_copy_preserves_old_save(self):
        original = shutil.copy2
        def fail(source, destination, *args, **kw):
            if Path(source) == self.source / 'account.sav':
                raise OSError(28, 'disk full')
            return original(source, destination, *args, **kw)
        with mock.patch.object(oot.shutil, 'copy2', side_effect=fail), self.assertRaises(OSError):
            self.copy()
        self.assert_old_intact()

    def test_failed_last_rename_rolls_back_all_entries(self):
        original = os.replace
        def fail(source, destination):
            if '-incoming-' in Path(source).parent.name and Path(source).name == 'option.sav':
                raise PermissionError('locked new settings')
            return original(source, destination)
        with mock.patch.object(oot.os, 'replace', side_effect=fail), self.assertRaises(OSError):
            self.copy()
        self.assert_old_intact()

    def test_rollback_failure_keeps_recoverable_old_files(self):
        original = os.replace
        def fail(source, destination):
            path = Path(source)
            if '-incoming-' in path.parent.name and path.name == 'option.sav':
                raise PermissionError('forward failure')
            if '-old-' in path.parent.name and path.name == 'slot_00':
                raise PermissionError('rollback failure')
            return original(source, destination)
        with mock.patch.object(oot.os, 'replace', side_effect=fail), self.assertRaises(oot.Fail) as raised:
            self.copy()
        aside, = self.target.glob('.*-old-*')
        self.assertEqual((aside / 'slot_00/progress.sav').read_bytes(), self.before['slot_00/progress.sav'])
        self.assertEqual((self.target / 'account.sav').read_bytes(), self.before['account.sav'])
        self.assertEqual(contents(self.backup), self.before)
        self.assertIn(str(aside), str(raised.exception))
        self.assertIn(str(self.backup), str(raised.exception))

    def test_read_only_old_file_can_be_cleaned(self):
        path = self.target / 'slot_00/progress.sav'
        path.chmod(stat.S_IREAD)
        # Also clear the backup's bit before TemporaryDirectory cleans it on Windows.
        self.addCleanup(lambda: [p.chmod(stat.S_IWRITE) for p in self.root.rglob('*') if p.is_file()])
        self.copy()
        self.assertEqual(contents(self.target), contents(self.source))
        self.assertFalse(any(p.name.startswith('.') for p in self.target.iterdir()))

    def test_success_and_keep_settings(self):
        self.copy(keep_settings=True)
        expected = contents(self.source)
        expected['option.sav'] = self.before['option.sav']
        self.assertEqual(contents(self.target), expected)
        self.assertEqual(contents(self.backup), self.before)

    def test_backup_failure_does_not_modify_target(self):
        with mock.patch.object(oot.shutil, 'copytree', side_effect=PermissionError('backup denied')):
            with self.assertRaises(OSError):
                self.copy()
        self.assertEqual(contents(self.target), self.before)

    def test_backup_inside_target_is_refused(self):
        self.backup = self.target / 'backup'
        with self.assertRaises(oot.Fail):
            self.copy()
        self.assertEqual(contents(self.target), self.before)

    def test_dry_run_writes_nothing(self):
        self.copy(dry_run=True)
        self.assertEqual(contents(self.target), self.before)
        self.assertFalse(self.backup.exists())


if __name__ == '__main__':
    unittest.main()
