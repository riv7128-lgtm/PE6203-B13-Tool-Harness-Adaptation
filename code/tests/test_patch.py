"""Local contract checks only. These are not MCPEvol-Bench task scores."""

import copy
import unittest

from harness_adapt.changes import canonical_digest, detect_changes
from harness_adapt.patch import patch_with_audit, selective_patch
from harness_adapt.validation import (
    HarnessValidationError, harness_errors, preservation_report,
    validate_harness, validate_tool_call,
)


def tool(name="weather.forecast"):
    return {
        "name": name,
        "description": "Return the forecast for a city.",
        "inputSchema": {
            "type": "object", "properties": {"city": {"type": "string"}},
            "required": ["city"], "additionalProperties": False,
        },
        "server": "weather",
    }


def snapshot():
    return {
        "tools": [tool(), tool("files.read")],
        "usage_rules": {"weather.forecast": ["Use city names."], "files.read": ["Use absolute paths."]},
        "routing": {"weather.forecast": "weather", "files.read": "filesystem"},
        "global_rules": ["Return grounded answers."],
        "project_note": {"owner": "local fixture"},
    }


class DetectionTests(unittest.TestCase):
    def test_identical_and_tool_reorder_are_not_changes(self):
        old = snapshot()
        new = copy.deepcopy(old)
        new["tools"].reverse()
        changes = detect_changes(old, new)
        self.assertEqual(changes["affected"], [])
        self.assertEqual(len(changes["unchanged"]), 2)

    def test_nested_parameter_and_output_changes_are_localized(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["inputSchema"]["properties"]["city"]["type"] = "integer"
        new["tools"][0]["outputSchema"] = {"type": "object"}
        changes = detect_changes(old, new)
        self.assertEqual(changes["changed"], ["weather.forecast"])
        detail = changes["details"]["weather.forecast"]
        self.assertEqual(detail["levels"], ["Parameter"])
        self.assertTrue(any(x["path"].endswith("/city/type") for x in detail["changes"]))

    def test_description_usage_and_route_changes_are_detected(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["description"] = "Return Celsius forecast for a canonical city identifier."
        new["usage_rules"]["weather.forecast"] = ["Resolve the identifier first."]
        new["routing"]["weather.forecast"] = "weather-v2"
        changes = detect_changes(old, new)
        self.assertEqual(changes["details"]["weather.forecast"]["levels"], ["Description", "Routing", "Usage"])

    def test_usage_only_change_is_affected(self):
        old, new = snapshot(), snapshot()
        new["usage_rules"]["weather.forecast"] = ["A new rule."]
        self.assertEqual(detect_changes(old, new)["changed"], ["weather.forecast"])

    def test_rename_is_not_inferred(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["name"] = "weather.lookup"
        for field in ("usage_rules", "routing"):
            new[field]["weather.lookup"] = new[field].pop("weather.forecast")
        changes = detect_changes(old, new)
        self.assertEqual(changes["added"], ["weather.lookup"])
        self.assertEqual(changes["removed"], ["weather.forecast"])
        self.assertEqual(changes["renamed"], [])
        mapped = detect_changes(old, new, {"weather.forecast": "weather.lookup"})
        self.assertEqual(mapped["details"]["weather.lookup"]["renamed_from"], "weather.forecast")

    def test_invalid_rename_fails(self):
        with self.assertRaises(ValueError):
            detect_changes(snapshot(), snapshot(), {"weather.forecast": "files.read"})

    def test_json_boolean_and_number_are_not_identical(self):
        old, new = snapshot(), snapshot()
        old["tools"][0]["metadata"] = {"x": True}
        new["tools"][0]["metadata"] = {"x": 1}
        self.assertEqual(detect_changes(old, new)["changed"], ["weather.forecast"])
        self.assertNotEqual(canonical_digest(old), canonical_digest(new))


class PatchTests(unittest.TestCase):
    def test_patch_restores_changed_call_and_preserves_unrelated_tool(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["inputSchema"] = {
            "type": "object", "properties": {"location": {"type": "string"}},
            "required": ["location"], "additionalProperties": False,
        }
        new["usage_rules"]["weather.forecast"] = ["Use the location key."]
        self.assertTrue(validate_tool_call(new, "weather.forecast", {"city": "Singapore"}))
        patched, audit = patch_with_audit(old, new)
        self.assertEqual(validate_tool_call(patched, "weather.forecast", {"location": "Singapore"}), [])
        self.assertEqual(patched["tools"][1], old["tools"][1])
        self.assertTrue(audit["preservation"]["preserved"])
        self.assertTrue(audit["affected_knowledge_matches_target"])

    def test_add_remove_and_cleanup_keyed_knowledge(self):
        old, new = snapshot(), snapshot()
        new["tools"][0] = tool("weather.lookup")
        for field in ("usage_rules", "routing"):
            new[field]["weather.lookup"] = new[field].pop("weather.forecast")
        patched = selective_patch(old, new)
        self.assertEqual([t["name"] for t in patched["tools"]], ["files.read", "weather.lookup"])
        self.assertNotIn("weather.forecast", patched["routing"])
        self.assertNotIn("weather.forecast", patched["usage_rules"])
        self.assertEqual(patched["tools"][0], old["tools"][1])

    def test_does_not_mutate_inputs_or_alias_outputs(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["description"] = "Changed."
        old_before, new_before = copy.deepcopy(old), copy.deepcopy(new)
        patched = selective_patch(old, new)
        patched["tools"][0]["description"] = "Output mutation."
        patched["usage_rules"]["files.read"].append("Output mutation.")
        self.assertEqual(old, old_before)
        self.assertEqual(new, new_before)

    def test_global_change_is_preserved_and_flagged_as_unsupported(self):
        old, new = snapshot(), snapshot()
        new["global_rules"] = ["A new global policy."]
        new["project_note"] = {"owner": "different"}
        patched, audit = patch_with_audit(old, new)
        self.assertEqual(patched["global_rules"], old["global_rules"])
        self.assertTrue(audit["unsupported_global_change"])
        self.assertEqual(audit["unsupported_top_level_changes"], ["project_note"])
        self.assertEqual(patched["project_note"], old["project_note"])

    def test_optional_maps_absent_are_not_introduced(self):
        old = {"tools": [tool()]}
        self.assertEqual(selective_patch(old, copy.deepcopy(old)), old)

    def test_rule_removal_does_not_leave_stale_rule(self):
        old, new = snapshot(), snapshot()
        del new["usage_rules"]["weather.forecast"]
        patched = selective_patch(old, new)
        self.assertNotIn("weather.forecast", patched["usage_rules"])

    def test_detects_injected_over_update(self):
        old, new = snapshot(), snapshot()
        new["tools"][0]["description"] = "New description."
        patched = selective_patch(old, new)
        patched["tools"][1]["description"] = "Accidental corruption."
        report = preservation_report(old, new, patched)
        self.assertFalse(report["preserved"])
        self.assertIn("tools/files.read", report["violations"])


class ValidationTests(unittest.TestCase):
    def test_duplicate_tool_names_rejected(self):
        harness = snapshot()
        harness["tools"].append(copy.deepcopy(harness["tools"][0]))
        with self.assertRaises(HarnessValidationError):
            validate_harness(harness)

    def test_dangling_rule_rejected(self):
        harness = snapshot()
        harness["usage_rules"]["missing.tool"] = ["stale"]
        self.assertTrue(any("unknown tool" in error for error in harness_errors(harness)))

    def test_unknown_tool_and_missing_parameter(self):
        harness = snapshot()
        self.assertTrue(validate_tool_call(harness, "unknown", {}))
        self.assertTrue(validate_tool_call(harness, "weather.forecast", {}))
        self.assertEqual(validate_tool_call(harness, "weather.forecast", {"city": "Singapore"}), [])

    def test_integer_rejects_boolean(self):
        harness = snapshot()
        harness["tools"][0]["inputSchema"]["properties"]["city"] = {"type": "integer"}
        self.assertTrue(validate_tool_call(harness, "weather.forecast", {"city": True}))
        self.assertEqual(validate_tool_call(harness, "weather.forecast", {"city": 1}), [])

    def test_unsupported_json_schema_features_are_reported(self):
        harness = snapshot()
        harness["tools"][0]["inputSchema"]["properties"]["city"]["pattern"] = "^[A-Z]+$"
        errors = validate_tool_call(harness, "weather.forecast", {"city": "Singapore"})
        self.assertTrue(any("unsupported schema keywords" in error for error in errors))

    def test_nonfinite_json_rejected(self):
        harness = snapshot()
        harness["metadata"] = float("nan")
        with self.assertRaises(HarnessValidationError):
            validate_harness(harness)


if __name__ == "__main__":
    unittest.main()
