import json
import unittest
from io import StringIO
from unittest.mock import Mock, patch

from agentref.agent_menu import AgentMenuServer, installed_agents
from agentref.cli import main


class AgentMenuTests(unittest.TestCase):
    def call(self, server, **args):
        return server.dispatch("tools/call", {"name": "search_mentions", "arguments": args})

    def test_completion_contract_and_filter(self):
        server = AgentMenuServer(lambda: ["claude", "dsh", "unrelated"])
        result = self.call(server, query="", path=[])
        self.assertEqual(set(result["structuredContent"]), {"items"})
        items = result["structuredContent"]["items"]
        self.assertEqual([i["insertText"] for i in items], ["@claude", "@dsh"])
        for item in items:
            self.assertEqual(set(item), {"type", "title", "detail", "insertText"})
            self.assertEqual(item["type"], "completion")
        self.assertEqual(self.call(server, query="@DSH")["structuredContent"]["items"], items[1:])
        self.assertEqual(self.call(server, query="missing")["structuredContent"]["items"], [])

    def test_invalid_calls_and_resources_fail_closed(self):
        server = AgentMenuServer(lambda: self.fail("Invalid request reached inventory"))
        for args in ({"query": 1}, {"path": [1]}, {"path": ["claude"]}, {"unexpected": "x"}):
            self.assertTrue(self.call(server, **args)["isError"])
        with self.assertRaises(LookupError):
            server.dispatch("resources/read", {"uri": "agentref://session/claude:any"})

    @patch("agentref.agent_menu.shutil.which", return_value="codex")
    @patch("agentref.agent_menu.subprocess.run")
    def test_live_inventory_filters_disabled_missing_and_foreign(self, run, which):
        def plugin(name, enabled=True, installed=True, marketplace="personal"):
            return dict(name=name, pluginId=name + "@" + marketplace, enabled=enabled, installed=installed)
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps({"installed": [
            plugin("claude"), plugin("dsh", enabled=False), plugin("grok", installed=False),
            plugin("opencode", marketplace="other"), plugin("unknown"),
        ]})
        self.assertEqual(installed_agents(), ["claude"])
        run.return_value.stdout = json.dumps({"installed": [plugin("dsh")]})
        self.assertEqual(installed_agents(), ["dsh"])

    def test_inventory_failure_is_not_empty_success(self):
        def unavailable():
            raise OSError("not available")
        self.assertTrue(self.call(AgentMenuServer(unavailable))["isError"])

    def test_inventory_cache_expires_and_failures_never_reuse_stale_entries(self):
        clock = Mock(return_value=0)
        catalog = Mock(side_effect=[["claude"], OSError("unavailable"), ["dsh"]])
        server = AgentMenuServer(catalog, clock=clock)
        self.assertEqual(len(self.call(server)["structuredContent"]["items"]), 1)
        clock.return_value = 1.9
        self.assertEqual(self.call(server, query="dsh")["structuredContent"]["items"], [])
        self.assertEqual(catalog.call_count, 1)
        clock.return_value = 2
        self.assertTrue(self.call(server)["isError"])
        items = self.call(server)["structuredContent"]["items"]
        self.assertEqual([item["insertText"] for item in items], ["@dsh"])
        self.assertEqual(catalog.call_count, 3)

    def test_cli_and_transport_never_open_session_index(self):
        with patch("agentref.cli.default_adapters", side_effect=AssertionError("source discovery")), \
             patch("agentref.cli.Index", side_effect=AssertionError("index creation")), \
             patch("agentref.agent_menu.AgentMenuServer.serve") as serve:
            self.assertEqual(main(["agent-menu"]), 0)
            serve.assert_called_once()
        sink = StringIO()
        AgentMenuServer(lambda: ["dsh"]).serve(StringIO(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_mentions", "arguments": {"query": "", "path": []}}}) + "\n"), sink)
        self.assertEqual(json.loads(sink.getvalue())["result"]["structuredContent"]["items"][0]["insertText"], "@dsh")
