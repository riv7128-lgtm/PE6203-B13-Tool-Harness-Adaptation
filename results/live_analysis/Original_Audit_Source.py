#!/usr/bin/env python3
"""Read-only audit and paired analysis of the frozen live experiment.

The script never changes a task, EVAL file, model log or formal score. It writes
derived summaries only after the entire declared grid passes validation.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "outputs/PE6203_Project4/Group_Project/code"
sys.path.insert(0, str(CODE))
from harness_adapt.metrics import (EvaluationError, STRATEGIES, VERSIONS,
    extract_official_scores, protocol_fingerprint, summarize_experiment)
from harness_adapt.official import (agent_tools, fingerprint, parse_cli_events,
                                   task_harness, _redact_observation)
from harness_adapt.runner import adapt, task_cohort
from harness_adapt.changes import detect_changes


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def actual_levels(changes):
    """Separate schema-description edits from structural parameter mutations."""
    result = set()
    if changes["added"] or changes["removed"]:
        result.add("Tool")
    for detail in changes["details"].values():
        for edit in detail.get("changes", []):
            p = edit["path"]
            if p.startswith("/tool/inputSchema") or p.startswith("/tool/outputSchema"):
                result.add("Description" if p.endswith("/description") else "Parameter")
            elif p.startswith("/tool/description") or p.startswith("/usage_rules"):
                result.add("Description")
            elif p == "/":
                result.add("Tool")
            else:
                result.add("Other metadata")
    return sorted(result)


def knowledge_audit(tasks, snapshots, manifest):
    rows, cohorts = [], {v: {} for v in ("Middle", "Late")}
    for task in tasks:
        old = task_harness(snapshots["early"], task)
        for version in VERSIONS:
            current = task_harness(snapshots[version.lower()], task)
            changes = detect_changes(old, current)
            cohort, required = task_cohort(task, old, current)
            rendered, routes = {}, {}
            for strategy in STRATEGIES:
                selected = task_harness(adapt(snapshots["early"], snapshots[version.lower()], strategy), task)
                rendered[strategy] = agent_tools(selected)[0]
                routes[strategy] = selected["routing"]
            rows.append({"task_id": str(task["idx"]), "version": version, "cohort": cohort,
                "affected_required_tools": required, "added_tools": changes["added"],
                "removed_tools": changes["removed"], "changed_tools": changes["changed"],
                "actual_change_levels": actual_levels(changes),
                "full_selective_equal_model_tools": rendered["full_rewrite"] == rendered["selective_patch"],
                "full_selective_equal_routes": routes["full_rewrite"] == routes["selective_patch"],
                "no_update_equal_full_model_tools": rendered["no_update"] == rendered["full_rewrite"],
                "model_tools_sha256": {k: fingerprint(v) for k, v in rendered.items()}})
            if version != "Early":
                cohorts[version][str(task["idx"])] = cohort
    if cohorts != manifest["cohort_by_version"]:
        raise EvaluationError("Recomputed actual-snapshot cohorts differ from the frozen run manifest")
    return {"evidence_kind": "MODEL_KNOWLEDGE_EQUIVALENCE_AND_COHORT_AUDIT", "rows": rows,
        "cohort_by_version": cohorts,
        "full_selective_equal_for_every_task_stage": all(r["full_selective_equal_model_tools"] and r["full_selective_equal_routes"] for r in rows),
        "interpretation": "When full refresh and selective patch expose equal model tools and routes, score differences cannot establish a semantic update advantage. Uncontrolled sampling, live clock timing and judge variability remain possible causes.",
        "schema_description_note": "Descriptions nested inside inputSchema count as Description coverage here, not structural Parameter changes."}


def invalid_attempt_audit(results, accepted_calls, config):
    rows = []
    for path in sorted(results.glob("run_*/*/*/INVALID_ATTEMPTS/*.json")):
        item = read(path)
        if item.get("scores") is not None:
            raise EvaluationError("Invalid attempt contains purported scores: " + str(path))
        rows.append({"path": str(path), "sha256": digest(path), "status": item.get("status"),
                     "phase": item.get("phase"), "task_id": item.get("task_id"),
                     "strategy": item.get("metadata", {}).get("strategy"),
                     "version": item.get("metadata", {}).get("version"),
                     "error_type": item.get("error_type"), "scores": None})
    model_statuses, unaccepted = {}, []
    log_root = Path(config.get("codex_cli_log_dir", "__not_configured__"))
    for path in sorted(log_root.glob("*/metadata.json")):
        item = read(path); status = item.get("status", "unknown")
        model_statuses[status] = model_statuses.get(status, 0) + 1
        if item.get("call_id") not in accepted_calls:
            unaccepted.append({"call_id": item.get("call_id"), "status": status,
                               "request_type": item.get("request_type"), "path": str(path),
                               "elapsed_seconds": item.get("elapsed_seconds"), "usage": item.get("usage")})
    return {"invalid_attempt_count": len(rows), "invalid_attempts": rows,
            "model_log_status_counts": model_statuses, "calls_not_linked_to_accepted_cells": unaccepted,
            "interpretation": "Invalid attempts and unsuccessful model calls remain saved and unscored. Successful retries fill the same frozen grid cell. Completed but unlinked calls may be abandoned attempts and are not assumed to be formal results."}


def accepted_call_audit(case, harness, config, seen):
    out = []
    expected_tools = agent_tools(harness)[0]
    roles = [("agent", call) for call in case.get("backend_calls", [])]
    roles += [("judge", call) for call in case.get("eval_result", {}).get("backend_calls", [])]
    if config.get("backend") == "codex_cli" and not roles:
        raise EvaluationError("Accepted CLI case has no backend call provenance")
    for role, call in roles:
        path = Path(call["path"]); meta = read(path); call_id = meta["call_id"]
        if call_id in seen:
            raise EvaluationError("A CLI call is reused across accepted cells: " + call_id)
        seen.add(call_id)
        if meta.get("status") != "COMPLETED_WITHOUT_BUILTIN_ACTIONS" or meta.get("built_in_actions_allowed") is not False:
            raise EvaluationError("Accepted cell links a failed or contaminated CLI call")
        request_path, schema_path = path.parent / "request.json", path.parent / "schema.json"
        request, schema = read(request_path), read(schema_path)
        if fingerprint(request) != meta["request_sha256"] or fingerprint(schema) != meta["schema_sha256"]:
            raise EvaluationError("CLI request or schema hash does not match its provenance")
        if role == "agent":
            if request.get("allowed_tools") != expected_tools:
                raise EvaluationError("Actual actor request tool knowledge differs from saved selected harness")
            messages = request.get("messages", [])
            if len(messages) < 2 or messages[1].get("content") != case["question"]:
                raise EvaluationError("Actual actor request question differs from the fixed task")
        expected_model = config["model" if role == "agent" else "judge_model"]
        if meta.get("requested_model") != expected_model:
            raise EvaluationError("Actual CLI model alias differs from frozen protocol")
        _, usage = parse_cli_events((path.parent / "events.jsonl").read_text())
        out.append({"call_id": call_id, "role": role, "metadata_path": str(path),
                    "metadata_sha256": digest(path), "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"], "elapsed_seconds": meta.get("elapsed_seconds")})
    return out


def failure_candidates(case, path, old, current):
    old_tools = {t["name"]: t for t in old["tools"]}
    current_tools = {t["name"]: t for t in current["tools"]}
    candidates = []
    observations = case.get("raw_tool_observations", [])
    for index, obs in enumerate(observations):
        if obs.get("status") == "INFRASTRUCTURE_ERROR" or obs.get("error_details", {}).get("classification") == "infrastructure_error":
            raise EvaluationError("Accepted scored case contains an infrastructure failure: " + str(path))
        if obs.get("status") != "VALID_TASK_FAILURE":
            continue
        name = obs.get("tool_identity")
        before, after = old_tools.get(name), current_tools.get(name)
        args = obs.get("arguments") or {}
        old_required = set((before or {}).get("inputSchema", {}).get("required", []))
        new_required = set((after or {}).get("inputSchema", {}).get("required", []))
        missing = new_required - set(args)
        stale_required = sorted(missing - old_required)
        future_success = any(o.get("tool_identity") == name and o.get("status") == "OBSERVED_TOOL_RESULT" for o in observations[index + 1:])
        candidates.append({"review_status": "CANDIDATE_REQUIRES_HUMAN_CAUSAL_REVIEW",
            "category": "under_update_stale_required_parameter" if stale_required else "other_valid_task_failure",
            "task_id": str(case["idx"]), "strategy": case["metadata"]["strategy"],
            "version": case["metadata"]["version"], "run_id": case["metadata"]["run_id"],
            "source_path": str(path), "source_sha256": digest(path), "observation_index": index,
            "tool_identity": name, "observation": obs, "old_required": sorted(old_required),
            "current_required": sorted(new_required), "newly_required_but_missing": stale_required,
            "same_tool_later_successful": future_success,
            "raw_tf": case["normalized_record"]["tf"], "raw_pe": case["normalized_record"]["pe"],
            "judge_caveat": "The judge sees current schemas while a no-update actor sees Early knowledge. A real stale call and retry do not establish that the actor ignored a requirement it had received. Preserve the original score and disclose this attribution asymmetry."})
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    base = ROOT / "outputs/PE6203_Project4/Group_Project/results"
    parser.add_argument("--results", type=Path, default=base / "live_benchmark")
    parser.add_argument("--output", type=Path, default=base / "live_analysis")
    parser.add_argument("--prepared", type=Path, default=CODE / "prepared_live")
    parser.add_argument("--snapshots", type=Path, default=ROOT / "work/live_runtime/snapshots")
    args = parser.parse_args()
    manifest = read(args.results / "run_manifest.json")
    config = manifest["protocol"]["config"]
    protocol_id = protocol_fingerprint(manifest["protocol"])
    if manifest["protocol_id"] != protocol_id:
        raise EvaluationError("Frozen manifest protocol fingerprint mismatch")
    tasks = read(args.prepared / "tasks.json")
    if fingerprint(tasks) != manifest["protocol"]["task_sha256"]:
        raise EvaluationError("Prepared official task content differs from frozen protocol")
    snapshots = {v.lower(): read(args.snapshots / (v.lower() + ".json")) for v in VERSIONS}
    if {v: fingerprint(s) for v, s in snapshots.items()} != manifest["protocol"]["snapshots"]:
        raise EvaluationError("Snapshot hashes differ from frozen protocol")
    knowledge = knowledge_audit(tasks, snapshots, manifest)
    write(args.output / "knowledge_equivalence.json", knowledge)
    task_index = {str(t["idx"]): t for t in tasks}
    records, sources, calls, failures, missing, seen_calls = [], [], [], [], [], set()
    for run in manifest["run_ids"]:
        for version in VERSIONS:
            for strategy in STRATEGIES:
                folder = args.results / ("run_" + run) / version.lower() / strategy
                for task_id in manifest["task_ids"]:
                    path = folder / "EVAL" / (task_id + ".json")
                    if not path.exists():
                        missing.append(str(path)); continue
                    case = read(path); record = case["normalized_record"]
                    if tuple(record[k] for k in ("run_id", "version", "strategy", "task_id")) != (run, version, strategy, task_id):
                        raise EvaluationError("Result identity differs from its grid path")
                    if case["metadata"]["protocol_id"] != protocol_id:
                        raise EvaluationError("Accepted EVAL metadata protocol mismatch")
                    tf, pe = extract_official_scores(case)
                    if (record["tf"], record["pe"]) != (tf, pe):
                        raise EvaluationError("Normalized score differs from original judge output")
                    harness_path = folder / "HARNESS" / (task_id + ".json")
                    harness = read(harness_path)
                    if fingerprint(harness) != case["metadata"]["agent_visible_harness_sha256"]:
                        raise EvaluationError("Saved actor harness differs from its captured provenance")
                    calls.extend(accepted_call_audit(case, harness, config, seen_calls))
                    task = task_index[task_id]
                    old, current = task_harness(snapshots["early"], task), task_harness(snapshots[version.lower()], task)
                    failures.extend(failure_candidates(case, path, old, current))
                    records.append(record)
                    sources.append({"path": str(path), "sha256": digest(path), "identity": [run, version, strategy, task_id]})
    attempts = invalid_attempt_audit(args.results, seen_calls, config)
    write(args.output / "attempt_audit.json", attempts)
    write(args.output / "failure_candidates.json", {"candidates": failures,
        "natural_over_update": "No structural over-update is established by these candidate records. Retention score variation under identical knowledge cannot establish that mechanism.",
        "controlled_over_update": "See separately labelled LOCAL_CONTRACT_TEST route-corruption example; it has no benchmark score."})
    if missing:
        write(args.output / "analysis_status.json", {"status": "INCOMPLETE_NOT_SUMMARIZED", "accepted_cells": len(records), "missing_cells": missing})
        print(json.dumps({"status": "INCOMPLETE_NOT_SUMMARIZED", "accepted_cells": len(records), "missing_cells": len(missing)}))
        return 2
    # Validate the live records.json rather than silently replacing a lost file.
    saved_records = read(args.results / "records.json")
    key = lambda r: (r["run_id"], r["version"], r["strategy"], r["task_id"])
    if sorted(saved_records, key=key) != sorted(records, key=key):
        raise EvaluationError("records.json and the complete EVAL grid disagree")
    summary = summarize_experiment(records, manifest)
    summary["caveats"].extend([
        "Custom Codex CLI JSON action protocol uses an explicit model alias and unexposed sampling controls.",
        "One agent run and one same-model independent judge session per cell cannot establish uncertainty or population robustness.",
        "Full refresh and selective patch expose equal model-facing tools and routes for every selected task-stage; score differences cannot establish a semantic patch advantage.",
        "The judge sees current tool schemas even when no-update actors receive Early knowledge. Some PE rationales may incorrectly attribute stale-call errors to ignoring supplied rules.",
        "Task 235 measures official vis-chart specifications, not rendered PNG artifact production.",
        "Invalid attempts remain retained and unscored; accepted retry results occupy the same frozen grid cell.",
    ])
    summary["source_eval_files"] = sources
    summary["attempt_audit_file"] = "attempt_audit.json"
    summary["knowledge_equivalence_file"] = "knowledge_equivalence.json"
    summary["accepted_model_usage"] = {role: {"calls": sum(c["role"] == role for c in calls),
        "input_tokens": sum(c["input_tokens"] for c in calls if c["role"] == role),
        "output_tokens": sum(c["output_tokens"] for c in calls if c["role"] == role),
        "api_cost_usd": None} for role in ("agent", "judge")}
    write(args.output / "accepted_model_calls.json", calls)
    write(args.output / "summary.json", summary)
    write(args.output / "analysis_status.json", {"status": "COMPLETE_VALIDATED", "accepted_cells": len(records),
        "expected_cells": len(manifest["task_ids"]) * len(manifest["run_ids"]) * 9,
        "invalid_attempt_count": attempts["invalid_attempt_count"], "records_json_matches_eval_grid": True})
    for field in ("stage_metrics", "ecs", "recovery_and_retention"):
        rows = summary[field]
        with (args.output / (field + ".csv")).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"status": "COMPLETE_VALIDATED", "records": len(records), "output": str(args.output),
                      "invalid_attempts": attempts["invalid_attempt_count"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvaluationError, FileNotFoundError, json.JSONDecodeError) as error:
        print("Live analysis not generated: " + str(error), file=sys.stderr)
        raise SystemExit(2)
