import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('opencode_config', Path(__file__).resolve().parents[1] / 'scripts/configure_opencode_tui.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TuiConfigTests(unittest.TestCase):
    def test_install_idempotent_rollback_preserves_other_entries(self):
        original = {'theme': 'existing', 'plugin': ['other-plugin', ['other', {'option': True}]], 'keybinds': {'leader': 'ctrl+x'}}
        raw = json.dumps(original).encode()
        entry = ['file:///fixture/tui.mjs', {'command': 'fixture-agentref'}]
        installed = module.update(raw, entry)
        self.assertEqual(module.update(installed, entry), installed)
        self.assertEqual(json.loads(module.update(installed, entry, True)), original)
        self.assertEqual(module.update(raw, entry, True), raw)

    def test_conflicts_and_non_json_are_rejected(self):
        entry = ['file:///fixture/tui.mjs', {'command': 'fixture-agentref'}]
        for raw in [b'{ // comment\n}', b'{"plugin":{}}', b'[]', json.dumps({'plugin': [[entry[0], {'command': 'user-edit'}]]}).encode()]:
            with self.assertRaises(ValueError):
                module.update(raw, entry)


if __name__ == '__main__':
    unittest.main()
