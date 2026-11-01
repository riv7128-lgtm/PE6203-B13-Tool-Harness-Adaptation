from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from harness_adapt.official import (
    normalize_mcp_tools, task_harness, prepare_subset, read_json,
    fingerprint, check_config, alias_for, judge_trajectory, agent_tools,
)


class OfficialTests(unittest.TestCase):
    def test_normalization_keeps_output_schema_and_unique_identity(self):
        tools = [{"name": "server_1mcp_lookup", "description": "d", "inputSchema": {}, "outputSchema": {"type": "string"}}]
        h = normalize_mcp_tools(tools)
        self.assertEqual(h["tools"][0]["server"], "server")
        self.assertEqual(h["tools"][0]["outputSchema"], {"type": "string"})
        with self.assertRaises(ValueError):
            normalize_mcp_tools(tools + tools)

    def test_fixed_server_context_includes_new_tools(self):
        h = normalize_mcp_tools([{"name": "a_1mcp_old", "inputSchema": {}}, {"name": "a_1mcp_new", "inputSchema": {}}, {"name": "b_1mcp_other", "inputSchema": {}}])
        result = task_harness(h, {"idx": 0, "servers": {"a": ["old"]}})
        self.assertEqual([t["name"] for t in result["tools"]], ["a_1mcp_new", "a_1mcp_old"])

    def test_alias_is_api_safe_and_qualified(self):
        self.assertNotEqual(alias_for("a_1mcp_find"), alias_for("b_1mcp_find"))
        self.assertRegex(alias_for("@a/b_1mcp_find"), r"^[a-z0-9_]+$")

    def test_harness_output_schema_is_visible_without_live_refresh(self):
        old = normalize_mcp_tools([{"name": "s_1mcp_t", "inputSchema": {}, "outputSchema": {"type": "string"}}])
        new = deepcopy(old); new["tools"][0]["outputSchema"] = {"type": "object"}
        old_description = agent_tools(old)[0][0]["function"]["description"]
        new_description = agent_tools(new)[0][0]["function"]["description"]
        self.assertIn('"string"', old_description)
        self.assertNotIn('"object"', old_description)
        self.assertIn('"object"', new_description)

    def test_preflight_fails_without_creds_and_config(self):
        report = check_config({}, require_live=False)
        self.assertEqual(report["status"], "BLOCKED_NOT_EXECUTED")
        self.assertIn("Configure model", report["errors"])
        self.assertFalse(report["credential_values_logged"])
        self.assertIn("Configure file_tree", report["errors"])

    def test_judge_decodes_alias_only_in_copied_evidence(self):
        identity = "a_1mcp_lookup"
        alias = alias_for(identity)
        current = normalize_mcp_tools([{"name": identity, "inputSchema": {}}])
        case = {"question": "q", "answer": "done", "involved_tools": current["tools"], "trajectory_messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}, {"role": "assistant", "tool_calls": [{"function": {"name": alias, "arguments": "{}"}}]}]}
        original = deepcopy(case)
        builder = Mock(return_value="judge prompt")
        response = {"choices": [{"message": {"content": '{"task_fulfillment":8,"planning_and_efficiency":9}'}}]}
        with patch("harness_adapt.official.load_official_rubric", return_value=builder), patch("harness_adapt.official.completion", return_value=response):
            result = judge_trajectory(case, current, {"judge_runs": 1}, ".")
        self.assertEqual(case, original)
        self.assertIn(identity, builder.call_args.args[2])
        self.assertEqual(json.loads(builder.call_args.args[2])[0]["tool_calls"][0]["function"]["name"], identity)
        self.assertEqual(result["aggregate"]["task_fulfillment_mean"], 8)

    def test_prepared_subset_preserves_all_original_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            data = repo / "src/custom/data/test_cases"; data.mkdir(parents=True)
            mutation = repo / "src/custom/data/mutation/HYBRID"; mutation.mkdir(parents=True)
            tasks = [{"idx": i, "question": "q" + str(i), "servers": {"s" + str(i): ["t"]}, "tool_calls": [{"tool_name": "t", "label": i}], "response": "original"} for i in range(3)]
            (data / "test_cases.json").write_text(json.dumps(tasks))
            (data / "chosen_idx.json").write_text(json.dumps({"samples": [{"idx": i} for i in range(3)]}))
            (mutation / "evolution.json").write_text(json.dumps({"s0": {"mutation_type": "TOOL"}, "s1": {"mutation_type": "PARAM"}, "s2": {"mutation_type": "DESC"}}))
            output = Path(tmp) / "prepared"
            manifest = prepare_subset(repo, output, 3)
            prepared = read_json(output / "tasks.json")
            self.assertEqual(prepared, tasks)
            self.assertEqual(manifest["tasks_sha256"], fingerprint(tasks))
            self.assertEqual(manifest["status"], "PREPARED_NOT_EXECUTED")
            self.assertFalse(manifest["selection_uses_scores"])


if __name__ == "__main__":
    unittest.main()
