"""Accepted task failures must stay separate from invalid infrastructure cells."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from harness_adapt.official import (BenchmarkInfrastructureError, agent_tools,
                                   classify_tool_exception, run_agent)


class McpError(Exception):
    def __init__(self, code, message):
        self.error = SimpleNamespace(code=code, message=message)
        super().__init__(message)


def fixture():
    name = "example_1mcp_old_tool"
    h = {"tools": [{"name": name, "server": "example", "description": "Old metadata",
                    "inputSchema": {"type": "object", "properties": {"old_param": {"type": "string"}}}}],
         "routing": {name: "example_1mcp_old_route"}, "usage_rules": {}, "global_rules": []}
    alias = next(iter(agent_tools(h)[1]))
    return h, alias


def replies(alias, arguments='{"old_param":"value"}'):
    return [
        {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call1", "type": "function", "function": {"name": alias, "arguments": arguments}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "[FINISH] observed result"}}]},
    ]


class InfrastructureTests(unittest.TestCase):
    def run_fixture(self, executor, *, arguments='{"old_param":"value"}', alias_override=None):
        harness, alias = fixture()
        with patch("harness_adapt.official.completion", side_effect=replies(alias_override or alias, arguments)), \
             patch("harness_adapt.official.execute_mcp_tool", side_effect=executor), \
             patch("harness_adapt.official.load_official_system_prompt", return_value="fixed"):
            return run_agent({"idx": 1, "question": "official question", "servers": {"example": ["old_tool"]}},
                             harness, "http://current/mcp", {"fixed_time": "2026-10-28", "max_rounds": 3,
                             "tool_result_max_chars": 500}, ".")

    def test_iserror_is_valid_failure_and_raw_observation_is_untruncated(self):
        async def executor(*args):
            return {"isError": True, "content": [{"type": "text", "text": "tool error " + "x" * 900}]}
        result = self.run_fixture(executor)
        obs = result["raw_tool_observations"][0]
        self.assertEqual(obs["status"], "VALID_TASK_FAILURE")
        self.assertEqual(obs["failure_category"], "mcp_isError_response")
        self.assertGreater(len(obs["raw_result"]["content"][0]["text"]), 900)
        shown = next(m["content"] for m in result["trajectory_messages"] if m["role"] == "tool")
        self.assertEqual(len(shown), 500)
        self.assertTrue(result["stop"])

    def test_old_route_and_parameter_are_not_repaired(self):
        calls = []
        async def executor(url, route, arguments):
            calls.append((url, route, arguments))
            raise McpError(-32602, "Unknown tool old_route or invalid old_param")
        result = self.run_fixture(executor)
        self.assertEqual(calls, [("http://current/mcp", "example_1mcp_old_route", {"old_param": "value"})])
        self.assertEqual(result["raw_tool_observations"][0]["failure_category"], "mcp_tool_rejection")

    def test_connection_refused_invalidates_attempt(self):
        async def executor(*args):
            raise ConnectionRefusedError("endpoint offline")
        with self.assertRaises(BenchmarkInfrastructureError) as caught:
            self.run_fixture(executor)
        error = caught.exception
        self.assertEqual(error.error_details["classification"], "infrastructure_error")
        self.assertEqual(error.error_details["leaves"][0]["exception_type"], "builtins.ConnectionRefusedError")
        self.assertEqual(error.raw_tool_observations[-1]["status"], "INFRASTRUCTURE_ERROR")
        self.assertIsInstance(error, RuntimeError)

    def test_mixed_nested_exceptiongroup_fails_closed(self):
        problem = ExceptionGroup("outer", [McpError(-32602, "invalid argument"),
            ExceptionGroup("inner", [TimeoutError("transport timed out"), ConnectionResetError("connection reset")])])
        details = classify_tool_exception(problem)
        self.assertEqual(details["classification"], "infrastructure_error")
        self.assertEqual(len(details["leaves"]), 3)
        self.assertEqual({x["exception_type"] for x in details["leaves"]},
                         {__name__ + ".McpError", "builtins.TimeoutError", "builtins.ConnectionResetError"})

    def test_all_tool_rejections_in_group_remain_observable(self):
        async def executor(*args):
            raise ExceptionGroup("rejections", [McpError(-32602, "required argument missing"),
                                                 McpError(-32601, "Unknown tool old_name")])
        result = self.run_fixture(executor)
        obs = result["raw_tool_observations"][0]
        self.assertEqual(obs["status"], "VALID_TASK_FAILURE")
        self.assertEqual(len(obs["error_details"]["leaves"]), 2)

    def test_broken_mcp_protocol_is_not_unknown_tool_failure(self):
        for exc in (McpError(-32601, "Method not found tools/call"),
                    McpError(-32603, "Internal server dependency missing"),
                    ValueError("Invalid transport response")):
            with self.subTest(error=exc):
                self.assertEqual(classify_tool_exception(exc)["classification"], "infrastructure_error")

    def test_invalid_model_json_is_valid_task_failure_without_transport(self):
        calls = []
        async def executor(*args):
            calls.append(args)
            return {}
        for args in ("{broken", "[]", "null"):
            with self.subTest(arguments=args):
                result = self.run_fixture(executor, arguments=args)
                self.assertEqual(result["raw_tool_observations"][0]["failure_category"], "invalid_model_arguments")
        self.assertEqual(calls, [])

    def test_unknown_model_alias_does_not_query_current_tools(self):
        calls = []
        async def executor(*args):
            calls.append(args)
            return {}
        result = self.run_fixture(executor, alias_override="not_in_old_harness")
        self.assertEqual(calls, [])
        self.assertEqual(result["raw_tool_observations"][0]["failure_category"], "unknown_model_tool_alias")

    def test_secret_values_removed_from_observations_and_error_evidence(self):
        marker = "EXAMPLE_PRIVATE_SENTINEL"
        async def result_executor(*args):
            return {"content": [{"text": f"Authorization: Bearer {marker}"}],
                    "api_key": marker, "nested": {"password": marker}, "safe": "full ordinary result"}
        result = self.run_fixture(result_executor)
        encoded = json.dumps(result["raw_tool_observations"])
        self.assertNotIn(marker, encoded)
        self.assertIn("full ordinary result", encoded)
        async def error_executor(*args):
            raise ConnectionRefusedError(f"https://user:{marker}@example.invalid password={marker}")
        with self.assertRaises(BenchmarkInfrastructureError) as caught:
            self.run_fixture(error_executor)
        self.assertNotIn(marker, json.dumps(caught.exception.error_details))

    def test_missing_harness_route_invalidates_before_execution(self):
        harness, alias = fixture()
        harness["routing"] = {}
        with patch("harness_adapt.official.completion", side_effect=replies(alias)), \
             patch("harness_adapt.official.load_official_system_prompt", return_value="fixed"), \
             patch("harness_adapt.official.execute_mcp_tool") as execute:
            with self.assertRaises(BenchmarkInfrastructureError):
                run_agent({"idx": 1, "question": "q", "servers": {}}, harness, "http://current/mcp",
                          {"fixed_time": "2026-10-28", "max_rounds": 3}, ".")
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
