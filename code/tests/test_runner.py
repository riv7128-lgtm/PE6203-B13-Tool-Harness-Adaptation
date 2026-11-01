import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from harness_adapt.baselines import no_update, full_rewrite
from harness_adapt.runner import adaptation_record, main, task_cohort
from harness_adapt.official import agent_tools, run_agent


def harness(param="old"):
    name = "example_1mcp_lookup"
    return {"tools": [{"name": name, "server": "example", "description": "Look up a record", "inputSchema": {"type": "object", "properties": {param: {"type": "string"}}}}], "routing": {name: name}, "usage_rules": {}, "global_rules": []}


class RunnerTests(unittest.TestCase):
    def test_baselines_are_deep_copies(self):
        old, new = harness(), harness("new")
        kept, rewritten = no_update(old, new), full_rewrite(old, new)
        self.assertEqual(kept, old); self.assertEqual(rewritten, new)
        kept["tools"][0]["description"] = "changed"
        self.assertEqual(old["tools"][0]["description"], "Look up a record")

    def test_adaptation_cost_is_not_token_estimate(self):
        old, new = harness(), harness("new")
        _, cost = adaptation_record(old, new, "no_update")
        self.assertEqual(cost["serialized_update_bytes"], 0)
        self.assertEqual(cost["update_prompt_tokens"], 0)
        self.assertEqual(cost["llm_update_calls"], 0)

    def test_cohort_uses_required_tools(self):
        task = {"servers": {"example": ["lookup"]}}
        self.assertEqual(task_cohort(task, harness(), harness("new"))[0], "changed")
        task["servers"] = {"example": ["unrelated"]}
        self.assertEqual(task_cohort(task, harness(), harness("new"))[0], "retained")

    def test_cohort_resolves_benchmark_server_aliases(self):
        old, new = harness(), harness("new")
        for h in (old, new):
            h["tools"][0]["name"] = "@guanxiong/mcp-server-time_1mcp_lookup"
            h["tools"][0]["server"] = "@guanxiong/mcp-server-time"
        task = {"servers": {"mcp-server-time": ["lookup"]}}
        self.assertEqual(task_cohort(task, old, new)[0], "changed")

    def test_stale_schema_and_route_are_used_at_current_endpoint(self):
        old = harness()
        old["routing"]["example_1mcp_lookup"] = "example_1mcp_old_name"
        tools, aliases = agent_tools(old)
        alias = next(iter(aliases))
        replies = [
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": alias, "arguments": '{"old":"x"}'}}]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "[FINISH] done"}}]},
        ]
        calls = []
        async def executor(url, route, arguments):
            calls.append((url, route, arguments)); return {"content": "ok"}
        with patch("harness_adapt.official.completion", side_effect=replies) as client, patch("harness_adapt.official.execute_mcp_tool", side_effect=executor), patch("harness_adapt.official.load_official_system_prompt", return_value="fixed system"):
            output = run_agent({"idx": 1, "question": "look up", "servers": {}}, old, "http://current/mcp", {"max_rounds": 3, "fixed_time": "2026-10-27"}, ".")
        self.assertTrue(output["stop"])
        self.assertEqual(calls, [("http://current/mcp", "example_1mcp_old_name", {"old": "x"})])
        sent_tools = client.call_args_list[0].args[2]
        self.assertIn("old", sent_tools[0]["function"]["parameters"]["properties"])
        self.assertNotIn("new", sent_tools[0]["function"]["parameters"]["properties"])

    def test_cli_adapt_persists_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, h in (("old", harness()), ("new", harness("new"))):
                (root / (name + ".json")).write_text(json.dumps(h))
            target = root / "result.json"
            rc = main(["adapt", "--old", str(root / "old.json"), "--new", str(root / "new.json"), "--strategy", "full_rewrite", "--out", str(target)])
            self.assertEqual(rc, 0)
            self.assertTrue(Path(str(target) + ".adaptation.json").exists())


if __name__ == "__main__":
    unittest.main()
