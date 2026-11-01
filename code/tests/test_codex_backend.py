from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness_adapt.official import (
    check_config, cli_command, cli_output_schema, codex_cli_completion,
    parse_cli_events, read_json,
)

TOOLS = [{"type": "function", "function": {"name": "allowed_lookup", "description": "Only allowed lookup", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}}]


def events(item_type="agent_message", include_usage=True):
    rows = [{"type": "thread.started", "thread_id": "fixture-session"}, {"type": "item.completed", "item": {"type": item_type, "text": "fixture response"}}]
    if include_usage:
        rows.append({"type": "turn.completed", "usage": {"input_tokens": 23, "cached_input_tokens": 0, "output_tokens": 7}})
    return "\n".join(json.dumps(x) for x in rows)


class CodexBackendTests(unittest.TestCase):
    def test_schema_limits_call_names(self):
        schema = cli_output_schema(TOOLS)
        self.assertEqual(schema["properties"]["tool_calls"]["items"]["properties"]["name"]["enum"], ["allowed_lookup"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(cli_output_schema([])["properties"]["tool_calls"]["maxItems"], 0)

    def test_command_disables_unrelated_action_surfaces(self):
        command = cli_command({}, "frozen-model", Path("s.json"), Path("r.json"))
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("shell_tool", command)
        self.assertIn("apps", command)
        self.assertIn("plugins", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_reject_builtin_tool_or_missing_measured_usage(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            parse_cli_events(events("command_execution"))
        with self.assertRaisesRegex(RuntimeError, "measured"):
            parse_cli_events(events(include_usage=False))

    def test_transport_warnings_are_not_actions_but_ignored_flags_fail(self):
        warning = json.dumps({"type": "item.completed", "item": {"type": "error", "message": "Falling back from WebSockets to HTTPS transport"}})
        self.assertEqual(parse_cli_events(warning + "\n" + events())[1]["input_tokens"], 23)
        ignored = json.dumps({"type": "item.completed", "item": {"type": "error", "message": "Codex is ignoring 1 unrecognized configuration setting"}})
        with self.assertRaisesRegex(RuntimeError, "ignored"):
            parse_cli_events(ignored + "\n" + events())

    def test_agent_response_is_openai_shaped_and_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"model": "frozen-model", "judge_model": "frozen-judge", "codex_cli_log_dir": tmp}
            def fake_run(command, **kwargs):
                if "--version" in command:
                    return subprocess.CompletedProcess(command, 0, stdout="codex-cli test-version\n", stderr="")
                self.assertEqual(list(Path(kwargs["cwd"]).iterdir()), [])
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                response_path = Path(command[command.index("--output-last-message") + 1])
                response_path.write_text(json.dumps({"content": "", "tool_calls": [{"name": "allowed_lookup", "arguments": '{"id":"x"}'}]}))
                return subprocess.CompletedProcess(command, 0, stdout=events(), stderr="")
            with patch("harness_adapt.official.subprocess.run", side_effect=fake_run):
                result = codex_cli_completion(config, [{"role": "user", "content": "lookup x"}], TOOLS)
            message = result["choices"][0]["message"]
            self.assertEqual(message["tool_calls"][0]["function"]["name"], "allowed_lookup")
            self.assertEqual(result["usage"]["prompt_tokens"], 23)
            metadata = read_json(result["backend_metadata"]["path"])
            self.assertEqual(metadata["status"], "COMPLETED_WITHOUT_BUILTIN_ACTIONS")
            self.assertEqual(metadata["unsupported_parameters"], ["temperature", "seed", "max_tokens"])
            self.assertIsNone(metadata["api_cost_usd"])
            self.assertTrue(Path(result["backend_metadata"]["path"]).with_name("events.jsonl").exists())

    def test_final_and_judge_use_separate_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"model": "frozen-model", "judge_model": "frozen-judge", "codex_cli_log_dir": tmp}
            def fake_run(command, **kwargs):
                if "--version" in command:
                    return subprocess.CompletedProcess(command, 0, stdout="codex-cli test\n", stderr="")
                model = command[command.index("--model") + 1]
                payload = {"task_fulfillment": 8, "grounding": 8, "planning_and_efficiency": 9} if model == "frozen-judge" else {"content": "Done", "tool_calls": []}
                Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(payload))
                return subprocess.CompletedProcess(command, 0, stdout=events(), stderr="")
            with patch("harness_adapt.official.subprocess.run", side_effect=fake_run):
                a = codex_cli_completion(config, [{"role": "user", "content": "task"}], [])
                j = codex_cli_completion(config, [{"role": "user", "content": "judge evidence"}], judge=True)
            self.assertTrue(a["choices"][0]["message"]["content"].startswith("[FINISH]"))
            self.assertNotEqual(a["backend_metadata"]["call_id"], j["backend_metadata"]["call_id"])
            self.assertEqual(json.loads(j["choices"][0]["message"]["content"])["task_fulfillment"], 8)

    def test_cli_preflight_does_not_demand_api_keys(self):
        config = {"backend": "codex_cli", "runs": 1, "cli_unsupported_parameters": ["temperature", "seed", "max_tokens"]}
        report = check_config(config, require_live=False)
        self.assertFalse(any("api_base_url" in e or "credential environment" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
