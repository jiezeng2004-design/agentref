import unittest
from scripts.configure_receiving_hosts import json_entry, toml_entry


class ReceivingHostConfigTests(unittest.TestCase):
    entry = {"command": "C:\\Agent's tools\\agentref.exe", "args": ["mcp"]}

    def test_json_preserves_other_servers_and_provider(self):
        raw = b'{"provider":{"custom":"keep"},"mcp":{"existing":{"enabled":false}}}'
        result = json_entry(raw, "mcp", self.entry)
        self.assertEqual(json_entry(result, "mcp", self.entry), result)
        import json
        self.assertEqual(json.loads(json_entry(result, "mcp", self.entry, True)), json.loads(raw))

    def test_toml_preserves_comments_and_handles_windows_path(self):
        raw = b'# user comment\n[model.custom]\nenabled = true\n'
        result = toml_entry(raw, self.entry)
        self.assertTrue(result.startswith(raw))
        self.assertEqual(toml_entry(result, self.entry), result)
        self.assertEqual(toml_entry(result, self.entry, True).strip(), raw.strip())

    def test_conflicting_values_fail_closed(self):
        with self.assertRaises(ValueError):
            json_entry(b'{"mcp":{"agentref":{"command":"other"}}}', "mcp", self.entry)
        with self.assertRaises(ValueError):
            toml_entry(b'[mcp_servers.agentref]\ncommand="other"\n', self.entry)
        with self.assertRaises(ValueError):
            toml_entry(toml_entry(b'', self.entry).replace(b'enabled = true', b'enabled = false'), self.entry, True)

    def test_grok_reformat_keeps_neighbor_comments_during_rollback(self):
        import tomllib
        result = toml_entry(b'', self.entry).replace(b'# BEGIN AgentRef receiving host v1\n', b'')
        result = result.replace(b'enabled = true', b'enabled=true').replace(b'args = ["mcp"]', b'args = [\n"mcp",\n]')
        result += b'\n# other manager owns this comment\n[model.custom]\nenabled=true\n'
        restored = toml_entry(result, self.entry, True)
        self.assertIn(b'# other manager owns this comment', restored)
        self.assertNotIn(b'AgentRef receiving host', restored)
        self.assertEqual(tomllib.loads(restored.decode()), {'model': {'custom': {'enabled': True}}})

    def test_jsonc_refused_without_reformatting_comments(self):
        with self.assertRaises(ValueError):
            json_entry(b'{/*preserve*/"mcp":{}}', "mcp", self.entry)


if __name__ == '__main__':
    unittest.main()
