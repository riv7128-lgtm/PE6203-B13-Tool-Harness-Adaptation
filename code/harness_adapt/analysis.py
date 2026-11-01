"""Failure-analysis utilities and reproducible mechanical illustrations.

These examples invoke an in-process contract-checking tool emulator. They are
not MCPEvol tasks, LLM trajectories, or evidence for TF/PE/ECS performance.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


def _invoke(environment: dict, tool: str, arguments: dict, route: str) -> dict:
    spec = environment.get(tool)
    if spec is None:
        return {"ok": False, "error": "UnknownTool", "tool": tool}
    if route != spec["route"]:
        return {"ok": False, "error": "WrongRoute", "expected_route": spec["route"], "actual_route": route}
    missing = [key for key in spec["required"] if key not in arguments]
    if missing:
        return {"ok": False, "error": "MissingRequiredParameter", "missing": missing}
    extra = sorted(set(arguments) - set(spec["required"]))
    if extra:
        return {"ok": False, "error": "UnexpectedParameter", "extra": extra}
    if tool == "files.read":
        return {"ok": True, "content": "local fixture file content", "path": arguments["file_path"]}
    if tool == "math.add":
        return {"ok": True, "result": arguments["a"] + arguments["b"]}
    return {"ok": False, "error": "UnsupportedFixture"}


def local_failure_examples() -> dict[str, dict]:
    """Execute two faulty updates and two corrected controls."""
    environment = {
        "files.read": {"required": ["file_path"], "route": "files-v2"},
        "math.add": {"required": ["a", "b"], "route": "math-v1"},
    }
    old_knowledge = {"files.read": {"parameter": "path", "route": "files-v2"},
                     "math.add": {"parameters": ["a", "b"], "route": "math-v1"}}
    under = deepcopy(old_knowledge)
    under["files.read"]["description"] = "Read a file using the new environment"
    bad_args = {under["files.read"]["parameter"]: "fixture.txt"}
    under_result = _invoke(environment, "files.read", bad_args, under["files.read"]["route"])
    fixed_args = {"file_path": "fixture.txt"}
    fixed_under = _invoke(environment, "files.read", fixed_args, "files-v2")
    over = deepcopy(old_knowledge)
    over["files.read"]["parameter"] = "file_path"
    over["math.add"]["route"] = "math-v2"
    math_args = {"a": 2, "b": 3}
    before_over = _invoke(environment, "math.add", math_args, old_knowledge["math.add"]["route"])
    over_result = _invoke(environment, "math.add", math_args, over["math.add"]["route"])
    fixed_over = _invoke(environment, "math.add", math_args, "math-v1")
    assert not under_result["ok"] and fixed_under["ok"]
    assert before_over["ok"] and not over_result["ok"] and fixed_over["ok"]
    common = {"evidence_kind": "LOCAL_CONTRACT_TEST", "official_benchmark": False,
              "agent_type": "deterministic in-process tool emulator",
              "scores": None, "benchmark_task_id": None}
    under_case = dict(common, failure_type="under_update", title="Parameter rename missed by patch",
        environment_change={"tool": "files.read", "old_parameter": "path", "new_parameter": "file_path"},
        attempted_update={"description": "changed", "parameter_knowledge": "left stale"},
        trajectory=[
            {"step": 1, "action": "load_harness", "knowledge": under["files.read"]},
            {"step": 2, "action": "call_tool", "tool": "files.read", "arguments": bad_args, "route": "files-v2"},
            {"step": 3, "action": "observe", "result": under_result},
            {"step": 4, "action": "apply_corrective_patch", "new_parameter": "file_path"},
            {"step": 5, "action": "call_tool", "arguments": fixed_args, "result": fixed_under}],
        conclusion="Updating the description alone leaves the required argument name stale.")
    over_case = dict(common, failure_type="over_update", title="Unrelated route changed by patch",
        environment_change={"changed_tool": "files.read", "unchanged_tool": "math.add"},
        attempted_update={"files.read.parameter": "file_path", "math.add.route": "math-v2"},
        trajectory=[
            {"step": 1, "action": "control_before_patch", "tool": "math.add", "arguments": math_args,
             "route": "math-v1", "result": before_over},
            {"step": 2, "action": "apply_faulty_patch", "unrelated_route_after": "math-v2"},
            {"step": 3, "action": "call_tool", "tool": "math.add", "arguments": math_args,
             "route": "math-v2", "result": over_result},
            {"step": 4, "action": "restore_unchanged_route", "route": "math-v1"},
            {"step": 5, "action": "call_tool", "tool": "math.add", "arguments": math_args,
             "route": "math-v1", "result": fixed_over}],
        conclusion="Changing an unaffected tool route damages a previously working call.")
    return {"under_update": under_case, "over_update": over_case}


def write_failure_examples(output_dir: str | Path) -> list[str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, payload in local_failure_examples().items():
        path = directory / f"{name}_LOCAL_CONTRACT_TEST.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def failure_annotation_template() -> dict[str, Any]:
    """Fields for manually reviewed official failure trajectories."""
    return {"evidence_kind": "OFFICIAL_TRAJECTORY_REVIEW_PENDING", "task_id": None,
            "strategy": None, "version": None, "run_id": None,
            "trajectory_path": None, "trajectory_sha256": None,
            "changed_tools": [], "failure_type": None,
            "required_categories": ["under_update", "over_update"],
            "failed_call_step": None, "before_knowledge": None, "after_knowledge": None,
            "observed_error": None, "causal_evidence": None,
            "counterfactual_control": None, "reviewer": None,
            "review_status": "pending actual benchmark execution"}
