"""CLI for reproducible adaptation and optional official benchmark execution."""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

from .baselines import no_update, full_rewrite
from .official import (
    VERSIONS, STRATEGIES, audit_repository, capture_snapshot, check_config,
    fingerprint, prepare_subset, read_json, write_json, task_harness,
    run_agent, judge_trajectory, canonical_bytes, canonical_server,
)


def adapt(old, new, strategy):
    if strategy == "no_update":
        return no_update(old, new)
    if strategy == "full_rewrite":
        return full_rewrite(old, new)
    if strategy == "selective_patch":
        from .patch import selective_patch
        return selective_patch(old, new)
    raise ValueError(f"Unknown strategy {strategy}")


def adaptation_record(old, new, strategy):
    from .changes import detect_changes
    started = time.perf_counter()
    result = adapt(old, new, strategy)
    elapsed = time.perf_counter() - started
    delta = detect_changes(old, result)
    changed = set(delta["added"]) | set(delta["removed"]) | set(delta["changed"])
    if strategy == "no_update":
        regenerated = []
    elif strategy == "full_rewrite":
        regenerated = [t["name"] for t in new["tools"]]
    else:
        regenerated = sorted(changed)
    # Serialized payload size is an implementation diagnostic, never tokens or
    # API dollars. Report it under its own name.
    payload = {"tools": [t for t in result["tools"] if t["name"] in regenerated],
               "routing": {k: v for k, v in result.get("routing", {}).items() if k in regenerated},
               "usage_rules": {k: v for k, v in result.get("usage_rules", {}).items() if k in regenerated},
               "deleted": delta["removed"]}
    return result, {
        "strategy": strategy, "old_sha256": fingerprint(old), "new_sha256": fingerprint(new),
        "result_sha256": fingerprint(result), "actual_changed_tools": sorted(changed),
        "regenerated_tool_count": len(regenerated), "serialized_update_bytes": 0 if strategy == "no_update" else len(canonical_bytes(payload)),
        "elapsed_seconds": elapsed, "llm_update_calls": 0,
        "update_prompt_tokens": 0, "update_completion_tokens": 0, "update_api_cost_usd": 0.0,
        "cost_scope": "Deterministic in-memory adaptation only; endpoint discovery and inference/judging costs are recorded separately.",
    }


def task_cohort(task, old_harness, new_harness):
    old = {t["name"]: t for t in old_harness["tools"]}
    new = {t["name"]: t for t in new_harness["tools"]}
    required = {(canonical_server(s), n) for s, names in task["servers"].items() for n in names}
    affected = []
    for name, record in old.items():
        server, short = name.rsplit("_1mcp_", 1) if "_1mcp_" in name else (record.get("server", ""), name)
        if (server, short) in required and (name not in new or record != new[name]):
            affected.append(name)
    return ("changed" if affected else "retained"), affected


def build_protocol(config, manifest, snapshots_data):
    cli = config.get("backend") == "codex_cli"
    if cli:
        decoding = {
            "backend": "codex_cli", "max_rounds": config["max_rounds"],
            "fixed_time": config["fixed_time"],
            "cli_version": config["codex_cli_expected_version"],
            "reasoning_effort": config.get("codex_cli_reasoning_effort", "low"),
            "unsupported_parameters": ["temperature", "seed", "max_tokens"],
            "sampling_parameters_controlled": False,
            "action_protocol": "Stateless strict JSON proposals converted by external executor",
        }
        judge = {
            "backend": "codex_cli", "model": config["judge_model"],
            "runs": config["judge_runs"],
            "reasoning_effort": config.get("codex_cli_reasoning_effort", "low"),
            "sampling_parameters_controlled": False,
            "independent_ephemeral_session": True,
            "rubric": "pinned official build_mcp_bench_judge_prompt",
            "dimension_order": [0, 1, 2],
        }
    else:
        decoding = {k: config[k] for k in ("temperature", "max_tokens", "max_rounds", "seed", "fixed_time")}
        judge = {"model": config["judge_model"], "temperature": config.get("judge_temperature", 0.0), "runs": config["judge_runs"], "rubric": "pinned official build_mcp_bench_judge_prompt", "dimension_order": [0, 1, 2]}
    return {
        "model_id": config["model"], "decoding": decoding, "judge": judge,
        "benchmark_commit": config["benchmark_commit"], "config": config,
        "task_sha256": manifest["tasks_sha256"],
        "snapshots": {v: fingerprint(x) for v, x in snapshots_data.items()},
        "protocol_extension": "Canonical tool-knowledge intervention; all candidate-server tools; hashed aliases; fixed time and max rounds; complete assistant evidence for judge. CLI is a custom JSON action backend with unexposed sampling parameters, not native API tool calling.",
    }


def run_official(config, repo, prepared, snapshots, output):
    from .metrics import protocol_fingerprint
    repo, prepared, snapshots, output = map(Path, (repo, prepared, snapshots, output))
    preflight = check_config(config, repo, snapshots)
    if preflight["errors"]:
        write_json(output / "preflight.json", preflight)
        raise RuntimeError("Official run blocked: " + "; ".join(preflight["errors"]))
    manifest = read_json(prepared / "subset_manifest.json")
    tasks = read_json(prepared / "tasks.json")
    if fingerprint(tasks) != manifest["tasks_sha256"]:
        raise ValueError("Prepared task content changed after subset freeze")
    snapshots_data = {v: read_json(snapshots / f"{v}.json") for v in VERSIONS}
    for version in VERSIONS:
        live_snapshot = asyncio.run(capture_snapshot(config["endpoints"][version]))
        if fingerprint(live_snapshot) != fingerprint(snapshots_data[version]):
            raise ValueError(f"Live {version} endpoint schema does not match the frozen capture")
    protocol = build_protocol(config, manifest, snapshots_data)
    protocol_hash = protocol_fingerprint(protocol)
    cohorts = {v.title(): {str(t["idx"]): task_cohort(t, task_harness(snapshots_data["early"], t), task_harness(snapshots_data[v], t))[0] for t in tasks} for v in ("middle", "late")}
    run_manifest = {"benchmark": "MCPEvol-Bench", "result_type": "OFFICIAL_TASKS_ADAPTER_PROTOCOL", "task_ids": [str(x) for x in manifest["task_ids"]], "run_ids": [str(x) for x in range(config["runs"])], "protocol_id": protocol_hash, "protocol_fingerprint": protocol_hash, "protocol": protocol, "cohort_by_version": cohorts, "adaptation_costs": [], "status": "RUNNING"}
    previous = output / "run_manifest.json"
    if previous.exists() and read_json(previous).get("protocol_fingerprint") != protocol_hash:
        raise ValueError("Output belongs to a different frozen protocol")
    write_json(previous, run_manifest)
    records = []
    records_lock = threading.Lock()
    def run_version(run_id, version):
        run_config = dict(config, seed=config.get("run_seeds", [config["seed"]])[run_id])
        for strategy in STRATEGIES:
            condition = output / f"run_{run_id}" / version / strategy
            cost_path, harness_path = condition / "snapshot_adaptation.json", condition / "snapshot_harness.json"
            if cost_path.exists() and harness_path.exists():
                full_harness, cost = read_json(harness_path), read_json(cost_path)
                if fingerprint(full_harness) != cost["result_sha256"]:
                    raise ValueError("Saved adaptation harness and cost audit disagree")
            else:
                full_harness, cost = adaptation_record(snapshots_data["early"], snapshots_data[version], strategy)
                if version == "early":
                    cost.update({"elapsed_seconds": 0.0, "serialized_update_bytes": 0, "regenerated_tool_count": 0, "cost_scope": "Shared initial knowledge construction is excluded; no evolution update at Early."})
                write_json(harness_path, full_harness)
                write_json(cost_path, cost)
            run_manifest["adaptation_costs"].append({"strategy": strategy, "version": version.title(), "run_id": str(run_id), "input_tokens": cost["update_prompt_tokens"], "output_tokens": cost["update_completion_tokens"], "wall_seconds": cost["elapsed_seconds"], "api_cost_usd": cost["update_api_cost_usd"]})
            for task in tasks:
                base = output / f"run_{run_id}" / version / strategy
                eval_path = base / "EVAL" / f"{task['idx']}.json"
                if eval_path.exists():
                    saved = read_json(eval_path)
                    if saved["metadata"]["protocol_fingerprint"] != protocol_hash:
                        raise ValueError("Existing evaluation protocol mismatch")
                    with records_lock:
                        records.append(saved["normalized_record"])
                    continue
                reset_command = [str(arg).replace('{endpoint}', config['endpoints'][version]).replace('{version}', version).replace('{task_id}', str(task['idx'])) for arg in config["reset_command"]]
                subprocess.run(reset_command, cwd=config["workspace"], check=True, shell=False)
                old_h = task_harness(snapshots_data["early"], task)
                new_h = task_harness(snapshots_data[version], task)
                harness = task_harness(full_harness, task)
                cohort, affected = task_cohort(task, old_h, new_h)
                metadata = {"strategy": strategy, "version": version.title(), "run_id": str(run_id), "run_seed": None if config.get("backend") == "codex_cli" else run_config["seed"], "seed_controlled": config.get("backend") != "codex_cli", "protocol_id": protocol_hash, "protocol_fingerprint": protocol_hash, "task_ids": [str(x) for x in manifest["task_ids"]], "cohort": cohort, "affected_required_tools": affected, "agent_visible_harness_sha256": fingerprint(harness), "execution_snapshot_sha256": fingerprint(new_h), "execution_endpoint": config["endpoints"][version]}
                write_json(base / "metadata.json", metadata)
                write_json(base / "HARNESS" / f"{task['idx']}.json", harness)
                write_json(base / "ADAPTATION" / f"{task['idx']}.json", cost)
                # The execution endpoint is current; model schema and routing
                # are entirely determined by the selected harness strategy.
                try:
                    case = run_agent(task, harness, config["endpoints"][version], run_config, repo)
                except Exception as exc:
                    write_json(base / "INVALID_ATTEMPTS" / f"{task['idx']}_{uuid.uuid4().hex}.json", {
                        "status": "INVALID_INFRASTRUCTURE_NOT_SCORED", "phase": "agent_execution",
                        "task_id": str(task['idx']), "metadata": metadata,
                        "error_type": type(exc).__name__, "error": str(exc)[:1000],
                        "error_details": getattr(exc, "error_details", None),
                        "raw_tool_observations": getattr(exc, "raw_tool_observations", None),
                        "trajectory_messages": getattr(exc, "trajectory_messages", None),
                        "created_unix": time.time(), "scores": None,
                    })
                    raise
                case["metadata"] = metadata
                write_json(base / "ANSWER" / f"{task['idx']}.json", case)
                try:
                    case["eval_result"] = judge_trajectory(case, new_h, run_config, repo)
                except Exception as exc:
                    write_json(base / "INVALID_ATTEMPTS" / f"{task['idx']}_{uuid.uuid4().hex}.json", {
                        "status": "INVALID_JUDGE_ATTEMPT_NOT_SCORED", "phase": "judge_execution",
                        "task_id": str(task['idx']), "metadata": metadata,
                        "error_type": type(exc).__name__, "error": str(exc)[:1000],
                        "created_unix": time.time(), "scores": None,
                    })
                    raise
                agg = case["eval_result"]["aggregate"]
                record = {"task_id": str(task["idx"]), "strategy": strategy, "version": version.title(), "run_id": str(run_id), "tf": agg["task_fulfillment_mean"], "pe": agg["planning_and_efficiency_mean"], "cohort": cohort, "evidence_kind": "official_mcpevol_judge", "protocol_id": protocol_hash}
                case["normalized_record"] = record
                write_json(eval_path, case)
                with records_lock:
                    records.append(record)
                    write_json(output / "records.json", records)
                print(json.dumps({"status": "CELL_COMPLETED", **record}), flush=True)
    for run_id in range(config["runs"]):
        workers = int(config.get("stage_workers", 1))
        if workers not in (1, 2, 3):
            raise ValueError("stage_workers must be 1, 2 or 3")
        if workers == 1:
            for version in VERSIONS:
                run_version(run_id, version)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(run_version, run_id, version) for version in VERSIONS]
                for future in futures:
                    future.result()
    records.sort(key=lambda r: (r["run_id"], r["version"], r["strategy"], r["task_id"]))
    run_manifest["adaptation_costs"].sort(key=lambda r: (r["run_id"], r["version"], r["strategy"]))
    write_json(output / "records.json", records)
    run_manifest["status"] = "COMPLETED"
    write_json(previous, run_manifest)
    return run_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tool-harness adaptation and official benchmark adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("adapt")
    a.add_argument("--old", required=True); a.add_argument("--new", required=True)
    a.add_argument("--strategy", choices=STRATEGIES, required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("audit"); a.add_argument("--repo", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("prepare"); a.add_argument("--repo", required=True); a.add_argument("--out", required=True); a.add_argument("--limit", type=int, default=12)
    a = sub.add_parser("capture"); a.add_argument("--url", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("preflight"); a.add_argument("--config", required=True); a.add_argument("--repo", required=True); a.add_argument("--snapshots", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("run-official"); a.add_argument("--config", required=True); a.add_argument("--repo", required=True); a.add_argument("--prepared", required=True); a.add_argument("--snapshots", required=True); a.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "adapt":
            result, record = adaptation_record(read_json(args.old), read_json(args.new), args.strategy)
            write_json(args.out, result); write_json(str(args.out) + ".adaptation.json", record)
            print(json.dumps({"status": "ADAPTED", "record": record}, ensure_ascii=False))
        elif args.command == "audit":
            result = audit_repository(args.repo); write_json(args.out, result); print(json.dumps(result, ensure_ascii=False))
        elif args.command == "prepare":
            result = prepare_subset(args.repo, args.out, args.limit); print(json.dumps(result, ensure_ascii=False))
        elif args.command == "capture":
            result = asyncio.run(capture_snapshot(args.url)); write_json(args.out, result)
            write_json(str(args.out) + ".provenance.json", {"endpoint": args.url, "snapshot_sha256": fingerprint(result), "captured_unix": time.time(), "tool_count": len(result["tools"])})
            print(json.dumps({"status": "CAPTURED", "tool_count": len(result["tools"])}))
        elif args.command == "preflight":
            result = check_config(read_json(args.config), args.repo, args.snapshots); write_json(args.out, result); print(json.dumps(result, ensure_ascii=False))
            return 0 if not result["errors"] else 2
        elif args.command == "run-official":
            print(json.dumps(run_official(read_json(args.config), args.repo, args.prepared, args.snapshots, args.out), ensure_ascii=False))
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(json.dumps({"status": "FAILED_NOT_SCORED", "error": str(exc)}, ensure_ascii=False))
        return 2
    return 0
