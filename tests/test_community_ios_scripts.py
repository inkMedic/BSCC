"""iOS builds must replace stale staged gameplay and settings scripts."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class IOSScriptStagingTest(unittest.TestCase):
    def test_refresh_replaces_old_scripts_and_removes_deleted_modules(self):
        path = (
            Path(__file__).resolve().parents[1]
            / 'tools/community-ios/build.py'
        )
        spec = importlib.util.spec_from_file_location('community_ios_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def write(relative, text):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)

            write('src/assets/ba_data/python/gameplay.py', 'NEW_RULES = True\n')
            write('src/assets/ba_data/python/__pycache__/stale.pyc', 'stale')
            write('tools/efro/__init__.py', '')
            write('tools/bacommon/__init__.py', '')
            site = '.venv/lib/python3.14/site-packages'
            for name in (
                'urllib3', 'requests', 'certifi', 'idna',
                'charset_normalizer', 'websockets',
            ):
                write(f'{site}/{name}/__init__.py', '')
            write(f'{site}/typing_extensions.py', '')
            write('stage/ba_data/python/gameplay.py', 'NEW_RULES = False\n')
            write('stage/ba_data/python/deleted.py', 'stale')
            write('stage/ba_data/assets/keep.bin', 'asset')

            with patch.object(module, 'ROOT', root):
                module.stage_scripts(root / 'stage')
                write('src/assets/ba_data/python/gameplay.py', 'NEW_RULES = 2\n')
                module.stage_scripts(root / 'stage')

            scripts = root / 'stage/ba_data/python'
            self.assertEqual(
                (scripts / 'gameplay.py').read_text(), 'NEW_RULES = 2\n'
            )
            self.assertFalse((scripts / 'deleted.py').exists())
            self.assertFalse((scripts / '__pycache__').exists())
            self.assertTrue((scripts / 'bacommon/__init__.py').is_file())
            self.assertEqual(
                (root / 'stage/ba_data/assets/keep.bin').read_text(), 'asset'
            )


if __name__ == '__main__':
    unittest.main()
