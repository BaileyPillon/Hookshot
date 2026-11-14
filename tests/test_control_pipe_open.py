"""Windows control-client busy-pipe races, deadlines and handle ownership; no game or real pipe needed."""
import ctypes
import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock

RUN_ALL_SKIP = {"linux": "Win32 named-pipe open contract; Unix sockets are covered by the client/bridge tests"}
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pipe_client', ROOT / 'scripts/hookshot_ctl.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


@unittest.skipUnless(os.name == 'nt', 'Win32 API contract')
class PipeOpen(unittest.TestCase):
    def setUp(self):
        self.kernel = mock.Mock()
        self.kernel.CreateFileW.return_value = 123
        self.kernel.WaitNamedPipeW.return_value = True
        self.stream = object()
        self.invalid = ctypes.c_void_p(-1).value
        for target, options in [
            ('ctypes.WinDLL', {'return_value': self.kernel}),
            ('ctypes.get_last_error', {'return_value': 231}),
            ('msvcrt.open_osfhandle', {'return_value': 77}),
            ('os.fdopen', {'return_value': self.stream}),
            ('os.close', {}),
        ]:
            patcher = mock.patch(target, **options)
            setattr(self, target.rsplit('.', 1)[-1], patcher.start())
            self.addCleanup(patcher.stop)

    def test_available_pipe_transfers_ownership_once(self):
        self.assertIs(client.open_windows_pipe(r'\\.\pipe\fixture', 1), self.stream)
        self.kernel.WaitNamedPipeW.assert_not_called()
        self.kernel.CloseHandle.assert_not_called()
        self.open_osfhandle.assert_called_once_with(123, os.O_RDWR | os.O_BINARY)
        self.fdopen.assert_called_once_with(77, 'r+b', buffering=0)

    def test_busy_pipe_and_another_client_winning_the_first_wait(self):
        self.kernel.CreateFileW.side_effect = [self.invalid, self.invalid, 123]
        self.assertIs(client.open_windows_pipe(r'\\.\pipe\fixture', 1), self.stream)
        self.assertEqual(self.kernel.WaitNamedPipeW.call_count, 2)
        self.assertEqual(self.open_osfhandle.call_count, 1)

    def test_missing_and_denied_pipes_do_not_wait(self):
        self.kernel.CreateFileW.return_value = self.invalid
        for code in (2, 5, 123):
            self.get_last_error.return_value = code
            with self.assertRaises(OSError) as raised:
                client.open_windows_pipe(r'\\.\pipe\fixture', 1)
            self.assertEqual(raised.exception.winerror, code)
        self.kernel.WaitNamedPipeW.assert_not_called()

    def test_busy_pipe_deadline_is_bounded(self):
        self.kernel.CreateFileW.return_value = self.invalid
        self.kernel.WaitNamedPipeW.return_value = False
        self.get_last_error.side_effect = [231, 121, 231]
        with mock.patch.object(client.time, 'monotonic', side_effect=[0, 0.2, 1.1]):
            with self.assertRaises(OSError) as raised:
                client.open_windows_pipe(r'\\.\pipe\fixture', 1)
        self.assertEqual(raised.exception.winerror, 121)
        self.kernel.WaitNamedPipeW.assert_called_once_with(r'\\.\pipe\fixture', 800)

    def test_disappearing_pipe_after_busy_is_not_retried(self):
        self.kernel.CreateFileW.return_value = self.invalid
        self.kernel.WaitNamedPipeW.return_value = False
        self.get_last_error.side_effect = [231, 2]
        with self.assertRaises(OSError) as raised:
            client.open_windows_pipe(r'\\.\pipe\fixture', 1)
        self.assertEqual(raised.exception.winerror, 2)
        self.assertEqual(self.kernel.CreateFileW.call_count, 1)

    def test_failed_descriptor_conversion_closes_native_handle(self):
        self.open_osfhandle.side_effect = OSError('no descriptors')
        with self.assertRaises(OSError):
            client.open_windows_pipe(r'\\.\pipe\fixture', 1)
        self.kernel.CloseHandle.assert_called_once_with(123)
        self.close.assert_not_called()

    def test_failed_stream_creation_closes_descriptor_only(self):
        self.fdopen.side_effect = OSError('stream failed')
        with self.assertRaises(OSError):
            client.open_windows_pipe(r'\\.\pipe\fixture', 1)
        self.close.assert_called_once_with(77)
        self.kernel.CloseHandle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
