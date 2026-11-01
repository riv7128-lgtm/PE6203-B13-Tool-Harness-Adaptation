"""Reproduce local adaptation and failure traces without external services.

Run from the code directory: python fixtures/demo_patch.py --output evidence
All outputs are LOCAL_CONTRACT_TEST. They contain no TF, PE, or ECS scores.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness_adapt.changes import detect_changes
from harness_adapt.patch import patch_with_audit
from harness_adapt.validation import preservation_report, validate_tool_call


def make_snapshots() -> tuple[dict, dict, dict]:
    early = {
        "tools": [
            {"name": "weather.forecast", "description": "Return a fixture forecast for a city name.", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}, "server": "weather"},
            {"name": "files.read", "description": "Read a fixture text file using an absolute path.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}, "server": "filesystem"},
            {"name": "reports.save", "description": "Save fixture report text.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "text": {"type": "string"}}, "required": ["path", "text"], "additionalProperties": False}, "server": "reports"},
        ],
        "usage_rules": {"weather.forecast": ["Pass a city name using the city argument."], "files.read": ["Use the path argument and preserve the file contents."], "reports.save": ["Pass the target path and report text."]},
        "routing": {"weather.forecast": "weather", "files.read": "filesystem", "reports.save": "reports"},
        "global_rules": ["Use tool observations as evidence and preserve unrelated tool knowledge."],
    }
    middle = copy.deepcopy(early)
    middle["tools"][0]["inputSchema"] = {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"], "additionalProperties": False}
    middle["tools"][0]["description"] = "Return a fixture forecast. The city argument was replaced by location."
    middle["usage_rules"]["weather.forecast"] = ["Pass the city name using location; city is no longer accepted."]
    middle["tools"][2]["name"] = "reports.write"
    middle["tools"][2]["description"] = "Replacement fixture report writer."
    for field in ("usage_rules", "routing"):
        middle[field]["reports.write"] = middle[field].pop("reports.save")
    late = copy.deepcopy(middle)
    late["tools"][0]["description"] = "Return a fixture forecast for a canonical location identifier such as SG-SIN."
    late["usage_rules"]["weather.forecast"] = ["Resolve city names to canonical identifiers before calling; Singapore maps to SG-SIN in this fixture."]
    late["routing"]["weather.forecast"] = "weather-v3"
    return early, middle, late


def execute_fixture_call(environment: dict, tool_name: str, arguments: dict) -> dict:
    errors = validate_tool_call(environment, tool_name, arguments)
    if errors:
        return {"accepted": False, "errors": errors}
    if tool_name == "weather.forecast":
        return {"accepted": True, "observation": {"fixture_only": True, "location": arguments.get("location", arguments.get("city")), "forecast": "illustrative local value"}}
    if tool_name == "files.read":
        return {"accepted": True, "observation": {"fixture_only": True, "path": arguments["path"], "text": "fixture file contents"}}
    return {"accepted": True, "observation": {"fixture_only": True}}


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evidence/local_patch"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    early, middle, late = make_snapshots()
    for name, snapshot in (("early", early), ("middle", middle), ("late", late)):
        dump(args.output / f"{name}.json", snapshot)
    start = time.perf_counter()
    patched, audit = patch_with_audit(early, middle, {"reports.save": "reports.write"})
    duration = time.perf_counter() - start
    late_patched, late_audit = patch_with_audit(early, late, {"reports.save": "reports.write"})
    dump(args.output / "early_to_middle_changes.json", detect_changes(early, middle, {"reports.save": "reports.write"}))
    dump(args.output / "middle_selective_harness.json", patched)
    dump(args.output / "middle_patch_audit.json", audit)
    dump(args.output / "late_selective_harness.json", late_patched)
    dump(args.output / "late_patch_audit.json", late_audit)
    stale_call = {"tool": "weather.forecast", "arguments": {"city": "Singapore"}}
    repaired_call = {"tool": "weather.forecast", "arguments": {"location": "Singapore"}}
    under_trace = {
        "evidence_type": "LOCAL_CONTRACT_TEST", "is_official_benchmark": False,
        "failure_type": "under_update", "cause": "The old parameter key city remains in the harness after the environment requires location.",
        "environment": "middle", "trajectory": [
            {"step": 1, "harness": "early unchanged", "action": stale_call, "result": execute_fixture_call(middle, stale_call["tool"], stale_call["arguments"])},
            {"step": 2, "harness": "selectively patched", "action": repaired_call, "result": execute_fixture_call(middle, repaired_call["tool"], repaired_call["arguments"])},
        ],
        "interpretation": "The obsolete argument is rejected and the repaired argument is structurally accepted. This is not an LLM task-success measurement.",
    }
    corrupt = copy.deepcopy(patched)
    unrelated = next(tool for tool in corrupt["tools"] if tool["name"] == "files.read")
    unrelated["inputSchema"] = {"type": "object", "properties": {"file": {"type": "string"}}, "required": ["file"], "additionalProperties": False}
    bad_call = {"tool": "files.read", "arguments": {"file": "/fixture/report.txt"}}
    good_call = {"tool": "files.read", "arguments": {"path": "/fixture/report.txt"}}
    over_trace = {
        "evidence_type": "LOCAL_CONTRACT_TEST", "is_official_benchmark": False,
        "failure_type": "over_update", "cause": "Fault injection modifies an unchanged files.read schema from path to file.",
        "environment": "middle", "fault_injected": True,
        "trajectory": [
            {"step": 1, "harness": "fault-injected broad update", "action": bad_call, "result": execute_fixture_call(middle, bad_call["tool"], bad_call["arguments"])},
            {"step": 2, "harness": "selectively patched", "action": good_call, "result": execute_fixture_call(middle, good_call["tool"], good_call["arguments"])},
        ],
        "preservation_check": preservation_report(early, middle, corrupt),
        "interpretation": "This constructed negative control demonstrates the guard, not evidence that a particular full-rewrite implementation naturally fails.",
    }
    dump(args.output / "under_update_trajectory.json", under_trace)
    dump(args.output / "over_update_trajectory.json", over_trace)
    summary = {
        "evidence_type": "LOCAL_CONTRACT_TEST", "is_official_benchmark": False,
        "old_tools": len(early["tools"]), "new_tools": len(middle["tools"]),
        "added": audit["changes"]["added"], "removed": audit["changes"]["removed"],
        "changed": audit["changes"]["changed"], "unchanged": audit["changes"]["unchanged"],
        "preserved_unaffected_knowledge": audit["preservation"]["preserved"],
        "affected_knowledge_matches_target": audit["affected_knowledge_matches_target"],
        "single_observed_adaptation_seconds": duration,
        "adaptation_api_calls": 0,
        "adaptation_api_tokens": 0,
        "task_scores": None,
        "task_score_status": "NOT_RUN_OFFICIAL_AGENT_AND_JUDGE",
    }
    dump(args.output / "local_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
