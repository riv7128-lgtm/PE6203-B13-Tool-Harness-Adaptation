"""Selective tool-record patch with scope and preservation auditing."""

from __future__ import annotations

from copy import deepcopy

from .changes import canonical_digest, detect_changes
from .validation import _preservation_report_for_changes


def selective_patch(old_harness: dict, new_harness: dict, rename_map: dict[str, str] | None = None) -> dict:
    """Refresh affected tool records and their keyed rules/routes only.

    Existing unaffected tools retain their structure and relative position.
    New identities are appended in target snapshot order. Global rules and
    unrelated top-level knowledge are intentionally immutable under this method.
    """
    changes = detect_changes(old_harness, new_harness, rename_map)
    patched, _ = _apply_patch(old_harness, new_harness, changes)
    return patched


def _apply_patch(old_harness: dict, new_harness: dict, changes: dict) -> tuple[dict, dict]:
    """Apply an internal fresh diff and preserve every original safety check."""
    affected = set(changes["affected"])
    removed = set(changes["removed"])
    added = set(changes["added"])
    new_tools = {tool["name"]: tool for tool in new_harness["tools"]}
    patched = deepcopy(old_harness)
    patched["tools"] = [
        deepcopy(new_tools[tool["name"]]) if tool["name"] in affected else tool
        for tool in patched["tools"] if tool["name"] not in removed
    ]
    patched["tools"].extend(deepcopy(tool) for tool in new_harness["tools"] if tool["name"] in added)
    for field in ("usage_rules", "routing"):
        # Avoid adding even an empty optional field when it was absent and
        # there is no affected entry to introduce.
        target = new_harness.get(field, {})
        if field not in patched and not any(name in target for name in affected):
            continue
        values = patched.setdefault(field, {})
        for name in affected:
            if name in target:
                values[name] = deepcopy(target[name])
            else:
                values.pop(name, None)
    report = _preservation_report_for_changes(old_harness, patched, changes)
    if not report["preserved"]:
        raise AssertionError(f"selective patch violated preservation: {report['violations']}")
    return patched, report


def patch_with_audit(old_harness: dict, new_harness: dict, rename_map: dict[str, str] | None = None) -> tuple[dict, dict]:
    """Return the patch plus transparent update and preservation evidence."""
    changes = detect_changes(old_harness, new_harness, rename_map)
    patched, report = _apply_patch(old_harness, new_harness, changes)
    new_tools = {tool["name"]: tool for tool in new_harness["tools"]}
    patched_tools = {tool["name"]: tool for tool in patched["tools"]}
    unresolved = []
    for name in changes["affected"]:
        if patched_tools.get(name) != new_tools.get(name):
            unresolved.append(name)
        for field in ("usage_rules", "routing"):
            actual = patched.get(field, {})
            expected = new_harness.get(field, {})
            if (name in actual) != (name in expected) or actual.get(name) != expected.get(name):
                unresolved.append(f"{field}/{name}")
    return patched, {
        "method": "selective_tool_record_patch",
        "scope": "affected tool records and tool-keyed usage rules and routing",
        "changes": changes,
        "preservation": report,
        "affected_knowledge_matches_target": not unresolved,
        "unresolved_affected_entries": unresolved,
        "global_rules_updated": False,
        "unsupported_global_change": changes["global_rules_changed"],
        "unsupported_top_level_changes": changes["unhandled_top_level_changes"],
        "output_digest": canonical_digest(patched),
        "evidence_type": "STRUCTURAL_AUDIT_NOT_TASK_SCORE",
    }
