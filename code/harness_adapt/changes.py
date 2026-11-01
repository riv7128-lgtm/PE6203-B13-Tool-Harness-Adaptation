"""Exact metadata differencing for tool knowledge snapshots.

Tool identities are explicit names. A deletion plus an addition is not guessed
to be a rename; an optional externally supplied rename map documents identity.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .validation import validate_harness


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pointer(key: Any) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _diff(before: Any, after: Any, path: str = "") -> list[dict]:
    if canonical_digest(before) == canonical_digest(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{_pointer(key)}"
            if key not in before:
                changes.append({"path": child, "operation": "add", "after": after[key]})
            elif key not in after:
                changes.append({"path": child, "operation": "remove", "before": before[key]})
            else:
                changes.extend(_diff(before[key], after[key], child))
        return changes
    return [{"path": path or "/", "operation": "replace", "before": before, "after": after}]


def _knowledge(harness: dict, name: str, tools: dict) -> dict:
    tool = tools[name]
    record = {"tool": tool}
    for field in ("usage_rules", "routing"):
        if name in harness.get(field, {}):
            record[field] = harness[field][name]
    return record


def _levels(deltas: list[dict]) -> list[str]:
    levels = set()
    for delta in deltas:
        path = delta["path"]
        if path.startswith("/tool/inputSchema") or path.startswith("/tool/outputSchema"):
            levels.add("Parameter")
        elif path.startswith("/tool/description"):
            levels.add("Description")
        elif path.startswith("/usage_rules"):
            levels.add("Usage")
        elif path.startswith("/routing"):
            levels.add("Routing")
        else:
            levels.add("Tool")
    return sorted(levels)


def detect_changes(old_harness: dict, new_harness: dict, rename_map: dict[str, str] | None = None) -> dict:
    """Return reproducible added/removed/changed/unchanged tool identities.

    A changed identity includes changes in its tool record, keyed usage rules,
    or route. Global changes are reported but are outside selective scope.
    """
    validate_harness(old_harness)
    validate_harness(new_harness)
    old_tools = {tool["name"]: tool for tool in old_harness["tools"]}
    new_tools = {tool["name"]: tool for tool in new_harness["tools"]}
    old_names = set(old_tools)
    new_names = set(new_tools)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    if rename_map is None:
        rename_map = {}
    if not isinstance(rename_map, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in rename_map.items()):
        raise ValueError("rename_map must map old tool names to new tool names")
    if len(set(rename_map.values())) != len(rename_map):
        raise ValueError("rename_map destinations must be unique")
    for source, destination in rename_map.items():
        if source not in removed or destination not in added:
            raise ValueError("explicit renames must map a removed tool to an added tool")
    details: dict[str, dict] = {}
    changed = []
    unchanged = []
    for name in sorted(old_names & new_names):
        deltas = _diff(_knowledge(old_harness, name, old_tools), _knowledge(new_harness, name, new_tools))
        if deltas:
            changed.append(name)
            details[name] = {"kind": "changed", "levels": _levels(deltas), "changes": deltas}
        else:
            unchanged.append(name)
    inverse_renames = {destination: source for source, destination in rename_map.items()}
    for name in added:
        details[name] = {"kind": "added", "levels": ["Tool"], "changes": [{"path": "/", "operation": "add", "after": _knowledge(new_harness, name, new_tools)}]}
        if name in inverse_renames:
            details[name]["renamed_from"] = inverse_renames[name]
    for name in removed:
        details[name] = {"kind": "removed", "levels": ["Tool"], "changes": [{"path": "/", "operation": "remove", "before": _knowledge(old_harness, name, old_tools)}]}
        if name in rename_map:
            details[name]["renamed_to"] = rename_map[name]
    global_deltas = _diff(old_harness.get("global_rules", []), new_harness.get("global_rules", []), "/global_rules")
    unknown_fields = sorted(
        field for field in (set(old_harness) | set(new_harness)) - {"tools", "usage_rules", "routing", "global_rules"}
        if (field in old_harness) != (field in new_harness) or old_harness.get(field) != new_harness.get(field)
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "affected": sorted(set(added + removed + changed)),
        "unchanged": unchanged,
        "renamed": [{"from": source, "to": destination} for source, destination in sorted(rename_map.items())],
        "details": details,
        "global_rules_changed": bool(global_deltas),
        "global_rule_changes": global_deltas,
        "unhandled_top_level_changes": unknown_fields,
        "old_digest": canonical_digest(old_harness),
        "new_digest": canonical_digest(new_harness),
    }
