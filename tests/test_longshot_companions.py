"""Optional companion boundaries: ordinary saves, mod folders and process targeting."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import longshot_companions as companions


class CompanionTests(unittest.TestCase):
    def test_full_randomizer_requires_separate_mode_game(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'romfs').mkdir()
            (root / 'image.bin').touch()
            (root / 'hookshot.exe').touch()
            with self.assertRaises(ValueError):
                companions.launch_plan('ootrr', root, game=root)

    def test_full_randomizer_plan_binds_only_its_mode_and_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / 'game'
            mode = game / 'longshot-modes/ootrr'
            (mode / 'romfs').mkdir(parents=True)
            (mode / 'image.bin').touch()
            (mode / 'hookshot.exe').touch()
            (mode / 'longshot-mode.json').write_text(json.dumps({'schema': 1, 'mode': 'ootrr'}))
            python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.dict(os.environ, {'HOS_COOP': '1', 'HOS_FS_OVERLAY': 'old-seed'}):
                command, env = companions.launch_plan('ootrr', root, game=game)
            self.assertEqual(Path(env['LONGSHOT_OOTRR_GAME']), mode.resolve())
            self.assertEqual(env['HOS_COOP'], '0')
            self.assertNotIn('HOS_FS_OVERLAY', env)
            self.assertTrue(Path(env['LONGSHOT_OOTRR_DATA']).is_relative_to(root))
            self.assertEqual(command[-2:], ['-m', 'oot_rando'])
            self.assertFalse((mode / 'user').exists())

    @unittest.skipUnless((ROOT / 'integrations/ootrr/.git').exists(), 'optional source submodule unavailable')
    def test_patched_companion_rejects_other_game_and_mod_paths(self):
        directory = companions.prepare('ootrr')
        spec = importlib.util.spec_from_file_location('ootrr_longshot_guard', directory / 'src/oot_rando/longshot.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LONGSHOT_OOTRR_GAME': temp}):
            game = Path(temp)
            self.assertTrue(helper.allowed_process(str(game / 'hookshot.exe')))
            self.assertFalse(helper.allowed_process(''))
            self.assertFalse(helper.allowed_process(str(game.parent / 'regular/hookshot.exe')))
            helper.validate_mod_target(game / 'mods')
            with self.assertRaises(ValueError):
                helper.validate_mod_target(game.parent / 'regular/mods')

    @unittest.skipUnless((ROOT / 'integrations/ootrr/.git').exists(), 'optional source submodule unavailable')
    def test_managed_gui_does_not_start_turbo_or_touch_controller_bindings(self):
        directory = companions.prepare('ootrr')
        tree = ast.parse((directory / 'src/oot_rando/gui/randomizer_gui.py').read_text(encoding='utf-8'))
        application = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Application')
        method = next(n for n in application.body if isinstance(n, ast.FunctionDef) and n.name == 'start_turbo')
        namespace = {'os': os}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<start_turbo>', 'exec'), namespace)
        class Status:
            def set(self, value):
                self.value = value
        class App:
            turbo_status = Status()
        app = App()
        with patch.dict(os.environ, {'LONGSHOT_OOTRR_GAME': 'isolated'}):
            namespace['start_turbo'](app)
        self.assertIn('disabled', app.turbo_status.value)


if __name__ == '__main__':
    unittest.main()
