from copy import deepcopy
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from harness_adapt.description_overlay import (DescriptionOverlayError,
    apply_official_description_overlay, select_official_description_layers, version_overlay_provenance)


def tool(name="convert_time"):
    return {"name": name, "description": "old tool description", "inputSchema": {"type": "object",
            "properties": {"sourceTimezone": {"type": "string"}, "targetTimezone": {"type": "string"},
                           "time": {"type": "string"}}, "required": ["sourceTimezone", "targetTimezone", "time"]}}


def layer(description="new description"):
    return {"time-mcp": {"convert_time": {"tool": {"original_description": "old", "modified_description": description},
        "parameters": [{"parameter_name": "targetTimezone", "modified_description": "target zone", "original_description": ""}]},
        "mutation_type": "DESC", "task_idx": 123}}


class DescriptionOverlayTests(unittest.TestCase):
    def test_nested_fields_apply_without_mutating_inputs_or_contract(self):
        before, metadata = tool(), [layer()]
        old_tool, old_metadata = deepcopy(before), deepcopy(metadata)
        updated, audit = apply_official_description_overlay(before, "time-mcp", metadata)
        self.assertEqual(updated["description"], "new description")
        self.assertEqual(updated["inputSchema"]["properties"]["targetTimezone"]["description"], "target zone")
        self.assertEqual(updated["name"], before["name"])
        self.assertEqual(updated["inputSchema"]["required"], before["inputSchema"]["required"])
        self.assertEqual(updated["inputSchema"]["type"], "object")
        self.assertEqual(before, old_tool)
        self.assertEqual(metadata, old_metadata)
        self.assertTrue(audit["input_unmodified"])
        self.assertEqual(audit["description_edit_count"], 2)

    def test_later_layers_override_earlier_descriptions(self):
        updated, audit = apply_official_description_overlay(tool(), "time-mcp", [layer("root"), layer("deep")])
        self.assertEqual(updated["description"], "deep")
        self.assertEqual([e["layer_index"] for e in audit["edits"] if e["path"] == "/description"], [0, 1])

    def test_flat_description_is_ignored_like_upstream(self):
        source = {"time-mcp": {"convert_time": {"modified_description": "must stay ignored", "original_description": "old"},
                               "mutation_type": "DESC", "task_idx": 2}}
        updated, audit = apply_official_description_overlay(tool(), "time-mcp", [source])
        self.assertEqual(updated, tool())
        self.assertEqual(audit["description_edit_count"], 0)
        self.assertTrue(any(row["path"] == "/modified_description" for row in audit["ignored_fields"]))

    def test_non_desc_and_different_server_or_tool_are_unchanged(self):
        metadata = layer(); metadata["time-mcp"]["mutation_type"] = "PARAM"
        self.assertEqual(apply_official_description_overlay(tool(), "time-mcp", [metadata])[0], tool())
        self.assertEqual(apply_official_description_overlay(tool(), "other-server", [layer()])[0], tool())
        other = tool("current_time")
        self.assertEqual(apply_official_description_overlay(other, "time-mcp", [layer()])[0], other)

    def test_qualified_identity_is_preserved(self):
        original = tool("time-mcp_1mcp_convert_time")
        updated, _ = apply_official_description_overlay(original, "time-mcp", [layer()])
        self.assertEqual(updated["name"], original["name"])
        self.assertEqual(updated["description"], "new description")

    def test_absent_ordinary_parameter_is_skipped_without_creation(self):
        metadata = layer()
        metadata["time-mcp"]["convert_time"]["parameters"].append({"parameter_name": "absent", "modified_description": "ignored"})
        updated, audit = apply_official_description_overlay(tool(), "time-mcp", [metadata])
        self.assertNotIn("absent", updated["inputSchema"]["properties"])
        self.assertTrue(any(row["reason"] == "parameter_absent_upstream_prints_and_skips" for row in audit["ignored_fields"]))
        # Upstream checks ordinary parameter membership before reading its new
        # description. A missing unused description must not invent a field.
        metadata["time-mcp"]["convert_time"]["parameters"][-1].pop("modified_description")
        self.assertNotIn("absent", apply_official_description_overlay(tool(), "time-mcp", [metadata])[0]["inputSchema"]["properties"])

    def test_three_official_special_nested_parameter_paths(self):
        examples = [("@sylphlab/pdf-reader-mcp", "read_pdf", "sources", "pages"),
                    ("@tsmztech/mcp-server-salesforce", "salesforce_search_all", "objects", "where"),
                    ("@itseasy21/mcp-knowledge-graph", "create_relations", "relations", "relationType")]
        for server, name, container, parameter in examples:
            with self.subTest(server=server):
                before = {"name": name, "description": "old", "inputSchema": {"type": "object", "properties": {
                    container: {"type": "array", "items": {"type": "object", "properties": {parameter: {"type": "string"}}, "required": [parameter]}}}}}
                metadata = [{server: {name: {"parameters": [{"parameter_name": parameter, "modified_description": "new nested text"}]}, "mutation_type": "DESC"}}]
                updated, audit = apply_official_description_overlay(before, server, metadata)
                self.assertEqual(updated["inputSchema"]["properties"][container]["items"]["properties"][parameter]["description"], "new nested text")
                self.assertEqual(audit["edits"][0]["path"], f"/inputSchema/properties/{container}/items/properties/{parameter}/description")

    def test_missing_special_nested_path_fails_without_schema_repair(self):
        before = {"name": "read_pdf", "description": "old", "inputSchema": {"type": "object", "properties": {}}}
        metadata = [{"@sylphlab/pdf-reader-mcp": {"read_pdf": {"parameters": [{"parameter_name": "pages", "modified_description": "new"}]}, "mutation_type": "DESC"}}]
        with self.assertRaises(DescriptionOverlayError) as caught:
            apply_official_description_overlay(before, "@sylphlab/pdf-reader-mcp", metadata)
        self.assertEqual(before["inputSchema"]["properties"], {})
        self.assertEqual(caught.exception.audit["status"], "UPSTREAM_RULE_INCOMPATIBLE_NOT_APPLIED")

    def test_first_tool_key_selection_matches_upstream_order(self):
        metadata = {"time-mcp": {"other_tool": {"tool": {"modified_description": "first"}},
                                 "convert_time": {"tool": {"modified_description": "ignored second"}}, "mutation_type": "DESC"}}
        updated, audit = apply_official_description_overlay(tool(), "time-mcp", [metadata])
        self.assertEqual(updated, tool())
        self.assertEqual(audit["layers"][0]["ignored_tool_keys"], ["convert_time"])

    def test_version_selection_and_provenance(self):
        roots = [layer(str(i)) for i in range(4)]
        self.assertEqual(select_official_description_layers(roots, "Early")[0], [])
        self.assertEqual(len(select_official_description_layers(roots, "Middle")[0]), 1)
        self.assertEqual(len(select_official_description_layers(roots, "Late")[0]), 4)
        provenance = version_overlay_provenance(roots)
        self.assertEqual(provenance["Late"]["layer_order"], "root_to_deep")
        self.assertEqual(len(provenance["Late"]["layers"][0]["ordered_json_sha256"]), 64)
        with self.assertRaises(ValueError): select_official_description_layers(roots[:2], "Late")

    def test_actual_official_time_mcp_metadata(self):
        root = Path(__file__).resolve().parents[5] / "work/official/MCPEvol-Bench"
        if not root.exists(): self.skipTest("Official source checkout is not bundled")
        paths = [root / ("src/custom/data/mutation/" + "/".join(["HYBRID"] * depth) + "/evolution.json") for depth in range(1, 5)]
        metadata = [json.loads(path.read_text()) for path in paths]
        middle_layers, _ = select_official_description_layers(metadata, "Middle")
        late_layers, _ = select_official_description_layers(metadata, "Late")
        middle, _ = apply_official_description_overlay(tool(), "time-mcp", middle_layers)
        late, audit = apply_official_description_overlay(tool(), "time-mcp", late_layers)
        self.assertEqual(middle["description"], metadata[0]["time-mcp"]["convert_time"]["tool"]["modified_description"])
        self.assertEqual(late["description"], metadata[-1]["time-mcp"]["convert_time"]["tool"]["modified_description"])
        self.assertEqual(late["inputSchema"]["properties"]["targetTimezone"]["description"], "The timezone to convert the input time to.")
        self.assertEqual(audit["description_edit_count"], 12)
        current = {"name": "current_time", "description": "old current", "inputSchema": {"type": "object", "properties": {}}}
        current, _ = apply_official_description_overlay(current, "time-mcp", late_layers)
        self.assertEqual(current["description"], metadata[2]["time-mcp"]["current_time"]["tool"]["modified_description"])

    def test_actual_rules_match_pinned_upstream_pure_function(self):
        root = Path(__file__).resolve().parents[5] / "work/official/MCPEvol-Bench"
        source = root / "src/custom/real_mcp/tool_level_test.py"
        if not source.exists(): self.skipTest("Official source checkout is not bundled")
        # Extract only the inspected pure rule function. Importing the original
        # module would perform unrelated benchmark setup and dependency imports.
        parsed = ast.parse(source.read_text())
        function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef)
                        and node.name == "return_involved_mutated_tool_status")
        code = compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec")
        metadata = [json.loads((root / ("src/custom/data/mutation/" + "/".join(["HYBRID"] * depth) + "/evolution.json")).read_text())
                    for depth in range(1, 5)]
        namespace = {"get_all_evolution_status": lambda path: list(reversed(metadata)),
                     "return_involved_tool_status": lambda servers, original: [deepcopy(original)]}
        exec(code, namespace)
        before = tool()
        upstream = namespace["return_involved_mutated_tool_status"](
            {"time-mcp": ["convert_time"]}, before, SimpleNamespace(mutation_path="not_used"))[0]
        updated, _ = apply_official_description_overlay(before, "time-mcp", metadata)
        self.assertEqual(updated, upstream)


if __name__ == "__main__":
    unittest.main()
