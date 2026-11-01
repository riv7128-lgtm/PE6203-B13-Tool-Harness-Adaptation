"""Read-only reproduction of the upstream MCPEvol DESC metadata rules.

Only tool.modified_description and parameters[].modified_description are read.
Flat modified_description fields are deliberately ignored because the pinned
upstream implementation ignores them. No tool identity or schema contract is
invented. The caller applies this environment intervention before constructing
strategy-specific stored knowledge, so it is independent of the tested method.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

UPSTREAM_COMMIT = "888c779a0fe735f612ca62bdd1fdd7c9e6bf8701"
UPSTREAM_FILE = "src/custom/real_mcp/tool_level_test.py"
UPSTREAM_RULES = ("get_all_evolution_status", "return_involved_mutated_tool_status")
OFFICIAL_LAYER_PATHS = ["src/custom/data/mutation/" + "/".join(["HYBRID"] * depth) + "/evolution.json"
                        for depth in range(1, 5)]
_SPECIAL_PARAMETERS = {
    ("@sylphlab/pdf-reader-mcp", "read_pdf"): ("sources", {"path", "url", "pages"}),
    ("@tsmztech/mcp-server-salesforce", "salesforce_search_all"): ("objects", {"name", "where", "orderBy", "limit"}),
    ("@itseasy21/mcp-knowledge-graph", "create_relations"): ("relations", {"from", "to", "relationType"}),
}


class DescriptionOverlayError(ValueError):
    """A malformed or incompatible record would make the upstream rule fail."""
    def __init__(self, message: str, audit: dict):
        super().__init__(message)
        self.audit = deepcopy(audit)


def _digest(value: Any, *, preserve_key_order: bool = False) -> str:
    # Upstream selects the first non-metadata key, so layer key order is part of
    # the logical provenance and must not disappear from the layer hash.
    payload = json.dumps(value, sort_keys=not preserve_key_order, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _layers(evolutions: list[dict]) -> None:
    if not isinstance(evolutions, list) or any(not isinstance(layer, dict) for layer in evolutions):
        raise ValueError("evolutions must be a list of metadata objects ordered root to deepest")


def select_official_description_layers(evolutions: list[dict], version: str) -> tuple[list[dict], dict]:
    """Select the explicitly frozen stage overlay and return its provenance.

    Middle uses the root metadata once. Late uses the four supplied official
    layers in root-to-deep order. This stage choice is a documented protocol
    mapping, not an inference from mutation-file depth or benchmark scores.
    """
    _layers(evolutions)
    stage = str(version).lower()
    if stage == "early":
        selected = []
    elif stage == "middle":
        if not evolutions:
            raise ValueError("Middle requires the root HYBRID metadata")
        selected = evolutions[:1]
    elif stage == "late":
        if len(evolutions) != 4:
            raise ValueError("Late requires exactly four pinned layers in root-to-deep order")
        selected = evolutions[:]
    else:
        raise ValueError("version must be Early, Middle or Late")
    provenance = {
        "stage": stage.title(), "intervention": "OFFICIAL_DESC_METADATA_OVERLAY",
        "upstream_commit": UPSTREAM_COMMIT, "upstream_file": UPSTREAM_FILE,
        "upstream_functions": list(UPSTREAM_RULES), "layer_order": "root_to_deep",
        "layer_count": len(selected),
        "layers": [{"index": i, "source_path": OFFICIAL_LAYER_PATHS[i],
                    "ordered_json_sha256": _digest(layer, preserve_key_order=True)}
                   for i, layer in enumerate(selected)],
        "stage_mapping": "Early none, Middle root once, Late all four root to deep",
        "source_hash_note": "These hashes cover ordered JSON objects. Record raw source-file SHA256 separately.",
        "permitted_fields": ["description", "inputSchema property description"],
        "strategy_independent": True,
    }
    return deepcopy(selected), provenance


def version_overlay_provenance(evolutions: list[dict]) -> dict[str, dict]:
    """Provenance records for all three frozen stage overlay selections."""
    return {v: select_official_description_layers(evolutions, v)[1]
            for v in ("Early", "Middle", "Late")}


def _pointer(parts: list[str]) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def apply_official_description_overlay(tool: dict, server_id: str,
                                       evolutions: list[dict]) -> tuple[dict, dict]:
    """Apply exactly the pinned upstream description-field lookup rules.

    The input tool and metadata remain untouched. Qualified tool identities are
    accepted only with the exact supplied server prefix. The first non-meta
    tool record is selected, matching upstream insertion-order behaviour.
    Ordinary absent parameters are skipped as upstream does. Missing special
    nested paths raise with an audit rather than constructing schema nodes.

    The upstream function loops over a combined unqualified tool list, which can
    accidentally touch another server's same-named tool. This one-tool interface
    deliberately respects server_id and reports that scoped boundary.
    """
    _layers(evolutions)
    if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
        raise ValueError("tool must contain its existing string name")
    if not isinstance(server_id, str) or not server_id:
        raise ValueError("server_id must be the exact nonempty metadata server identity")
    updated = deepcopy(tool)
    prefix = server_id + "_1mcp_"
    short_name = tool["name"][len(prefix):] if tool["name"].startswith(prefix) else tool["name"]
    audit = {
        "intervention": "OFFICIAL_DESC_METADATA_OVERLAY", "upstream_commit": UPSTREAM_COMMIT,
        "upstream_file": UPSTREAM_FILE, "upstream_functions": list(UPSTREAM_RULES),
        "server_id": server_id, "tool_identity": tool["name"], "lookup_tool_name": short_name,
        "layer_order": "root_to_deep", "layers": [], "edits": [], "ignored_fields": [],
        "input_sha256": _digest(tool), "status": "APPLIED_OR_UNCHANGED",
        "limitations": [
            "Only nested tool.modified_description and parameters[].modified_description are read.",
            "Flat modified_description fields are ignored exactly as in the pinned upstream code.",
            "The first non-metadata tool key is selected in each DESC server record.",
            "Special nested paths fail when missing; ordinary missing parameters are skipped.",
            "The interface scopes a tool to server_id and does not reproduce the upstream cross-server same-name overwrite bug.",
            "Only description text changes. Tool names, schema types, required fields and task labels are never rewritten.",
        ],
    }

    def fail(message: str) -> None:
        audit["status"] = "UPSTREAM_RULE_INCOMPATIBLE_NOT_APPLIED"
        audit["error"] = message
        raise DescriptionOverlayError(message, audit)

    def ignored(layer_index: int, path: str, reason: str) -> None:
        audit["ignored_fields"].append({"layer_index": layer_index, "path": path, "reason": reason})

    def edit(layer_index: int, parts: list[str], description: Any) -> None:
        if not isinstance(description, str):
            fail("Official modified_description must be a string")
        node = updated
        try:
            for part in parts[:-1]:
                node = node[part]
            if not isinstance(node, dict):
                fail("Official description destination is not a schema object")
        except (KeyError, TypeError):
            fail("Missing special inputSchema path required by upstream: " + _pointer(parts))
        present = parts[-1] in node
        before = deepcopy(node.get(parts[-1]))
        node[parts[-1]] = description
        audit["edits"].append({"layer_index": layer_index, "path": _pointer(parts),
                               "before_present": present, "before": before, "after": description,
                               "value_changed": not present or before != description})

    for index, layer in enumerate(evolutions):
        entry = {"index": index, "ordered_json_sha256": _digest(layer, preserve_key_order=True)}
        audit["layers"].append(entry)
        server = layer.get(server_id)
        if server is None:
            entry["status"] = "server_absent"
            continue
        if not isinstance(server, dict):
            fail("Official server mutation record must be an object")
        entry["mutation_type"] = server.get("mutation_type")
        if server.get("mutation_type") != "DESC":
            entry["status"] = "non_DESC_not_applied"
            continue
        names = [key for key in server if key not in ("mutation_type", "task_idx")]
        if not names:
            fail("DESC server record has no tool key")
        selected_name = names[0]
        entry["selected_tool"] = selected_name
        entry["ignored_tool_keys"] = names[1:]
        if selected_name != short_name:
            entry["status"] = "different_tool_not_applied"
            continue
        record = server[selected_name]
        if not isinstance(record, dict):
            fail("Selected official DESC tool record must be an object")
        entry["status"] = "matched_DESC_tool"
        for key in record:
            if key not in ("tool", "parameters"):
                ignored(index, "/" + str(key), "upstream_does_not_read_flat_tool_record_field")
        if "tool" in record:
            description = record["tool"]
            if not isinstance(description, dict) or "modified_description" not in description:
                fail("Official nested tool.modified_description is missing")
            for key in description:
                if key != "modified_description":
                    ignored(index, "/tool/" + str(key), "upstream_reads_only_modified_description")
            edit(index, ["description"], description["modified_description"])
        if "parameters" in record:
            parameters = record["parameters"]
            if not isinstance(parameters, list):
                fail("Official parameters must be a list")
            for parameter_index, parameter in enumerate(parameters):
                if not isinstance(parameter, dict) or not isinstance(parameter.get("parameter_name"), str):
                    fail("Official parameter requires parameter_name")
                name = parameter["parameter_name"]
                for key in parameter:
                    if key not in ("parameter_name", "modified_description"):
                        ignored(index, f"/parameters/{parameter_index}/{key}", "upstream_does_not_read_parameter_provenance_field")
                nested = _SPECIAL_PARAMETERS.get((server_id, short_name))
                if nested and name in nested[1]:
                    parts = ["inputSchema", "properties", nested[0], "items", "properties", name, "description"]
                else:
                    try:
                        properties = updated["inputSchema"]["properties"]
                    except (KeyError, TypeError):
                        fail("inputSchema.properties required by upstream is missing")
                    if not isinstance(properties, dict):
                        fail("inputSchema.properties must be an object")
                    if name not in properties:
                        ignored(index, f"/parameters/{parameter_index}", "parameter_absent_upstream_prints_and_skips")
                        continue
                    parts = ["inputSchema", "properties", name, "description"]
                if "modified_description" not in parameter:
                    fail("Official applied parameter.modified_description is missing")
                edit(index, parts, parameter["modified_description"])
    audit["output_sha256"] = _digest(updated)
    audit["description_edit_count"] = len(audit["edits"])
    audit["changed_description_count"] = sum(bool(row["value_changed"]) for row in audit["edits"])
    audit["input_unmodified"] = _digest(tool) == audit["input_sha256"]
    return updated, audit
