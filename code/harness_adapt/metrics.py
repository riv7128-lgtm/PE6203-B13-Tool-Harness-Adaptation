"""Strict paired analysis of official MCPEvol judge results.

Numerical summaries are never produced from mechanical demonstration logs.
ECS follows the official implementation: mean over tasks of (mean TF across
three stages minus population standard deviation across those stages).
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

VERSIONS = ("Early", "Middle", "Late")
STRATEGIES = ("no_update", "full_rewrite", "selective_patch")
REQUIRED_PROTOCOL_FIELDS = ("model_id", "decoding", "judge", "benchmark_commit")


class EvaluationError(ValueError):
    """The experiment cannot be summarized as a complete fair comparison."""


def protocol_fingerprint(protocol: dict[str, Any]) -> str:
    """Hash the locked protocol; do not include credentials in the protocol."""
    if not isinstance(protocol, dict):
        raise EvaluationError("protocol must be an object")
    for field in REQUIRED_PROTOCOL_FIELDS:
        if field not in protocol or protocol[field] in (None, "", {}):
            raise EvaluationError(f"Missing locked protocol field: {field}")
    forbidden = {"api_key", "password", "token", "secret", "authorization"}
    def reject_secret_keys(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if str(key).lower() in forbidden:
                    raise EvaluationError("Credentials must not enter experiment metadata")
                reject_secret_keys(value)
        elif isinstance(obj, list):
            for item in obj:
                reject_secret_keys(item)
    reject_secret_keys(protocol)
    return hashlib.sha256(json.dumps(protocol, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _number(value: Any, label: str, *, score: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise EvaluationError(f"{label} must be finite")
    if score and not 1.0 <= value <= 10.0:
        raise EvaluationError(f"{label} must be in the official 1 to 10 range")
    if not score and value < 0:
        raise EvaluationError(f"{label} must be nonnegative")
    return value


def extract_official_scores(payload: dict[str, Any]) -> tuple[float, float]:
    """Read the official mean fields, falling back to its integer fields.

    A present malformed mean is an error, not a reason to silently use an
    integer value. Files with failed or missing scores cannot be averaged away.
    """
    result = payload.get("eval_result")
    if not isinstance(result, dict):
        raise EvaluationError("Missing eval_result object")
    aggregate = result.get("aggregate", {})
    if not isinstance(aggregate, dict):
        raise EvaluationError("Malformed eval_result.aggregate")
    def first_score(mean_name: str, int_name: str) -> float:
        for source, key in ((aggregate, mean_name), (result, mean_name),
                            (aggregate, int_name), (result, int_name)):
            if key in source:
                return _number(source[key], key, score=True)
        raise EvaluationError(f"Missing official judge metric {mean_name}")
    if "successful_runs" in aggregate:
        count = aggregate["successful_runs"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise EvaluationError("No successful judge evaluations")
    return (first_score("task_fulfillment_mean", "task_fulfillment"),
            first_score("planning_and_efficiency_mean", "planning_and_efficiency"))


def _unique_strings(values: Any, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise EvaluationError(f"{label} must be a nonempty list")
    if any(not isinstance(v, str) or not v for v in values):
        raise EvaluationError(f"{label} must contain nonempty strings")
    if len(values) != len(set(values)):
        raise EvaluationError(f"Duplicate {label}")
    return list(values)


def validate_paired_records(records: list[dict[str, Any]], *, task_ids: list[str],
                            run_ids: list[str], protocol_id: str,
                            strategies: tuple[str, ...] = STRATEGIES) -> dict:
    """Require the entire strategy x stage x run x task Cartesian product."""
    tasks = _unique_strings(task_ids, "task_ids")
    runs = _unique_strings(run_ids, "run_ids")
    strategy_list = _unique_strings(list(strategies), "strategies")
    if set(strategy_list) != set(STRATEGIES):
        raise EvaluationError("The comparison must include exactly the three required strategies")
    if not isinstance(protocol_id, str) or not protocol_id:
        raise EvaluationError("protocol_id is required")
    if not isinstance(records, list) or not records:
        raise EvaluationError("No official judge records available; benchmark results remain pending")
    expected = {(s, v, r, t) for s in strategies for v in VERSIONS
                for r in runs for t in tasks}
    actual = {}
    for record in records:
        if not isinstance(record, dict):
            raise EvaluationError("Each result must be an object")
        if record.get("evidence_kind") != "official_mcpevol_judge":
            raise EvaluationError("Only official_mcpevol_judge records can enter TF PE ECS summaries")
        key = tuple(record.get(f) for f in ("strategy", "version", "run_id", "task_id"))
        if key not in expected:
            raise EvaluationError(f"Unexpected experiment record {key}")
        if key in actual:
            raise EvaluationError(f"Duplicate experiment record {key}")
        if record.get("protocol_id") != protocol_id:
            raise EvaluationError(f"Protocol mismatch for {key}")
        row = deepcopy(record)
        row["tf"] = _number(row.get("tf"), "tf", score=True)
        row["pe"] = _number(row.get("pe"), "pe", score=True)
        actual[key] = row
    missing = expected - actual.keys()
    if missing:
        examples = sorted(missing)[:8]
        raise EvaluationError(f"Incomplete paired experiment: {len(missing)} missing records; examples={examples}")
    return actual


def ecs(scores_by_task: dict[str, list[float]]) -> tuple[float, list[dict]]:
    """The official per-task ECS formula using population standard deviation."""
    if not scores_by_task:
        raise EvaluationError("ECS requires at least one task")
    rows = []
    for task_id, scores in sorted(scores_by_task.items()):
        if len(scores) != 3:
            raise EvaluationError(f"ECS requires exactly three stage scores for task {task_id}")
        values = [_number(v, "TF", score=True) for v in scores]
        mean = statistics.mean(values)
        sd = statistics.pstdev(values)
        rows.append({"task_id": task_id, "tf_by_stage": dict(zip(VERSIONS, values)),
                     "mean": mean, "population_std": sd, "ecs": mean - sd})
    return statistics.mean(row["ecs"] for row in rows), rows


def summarize_costs(costs: list[dict[str, Any]], *, run_ids: list[str]) -> dict:
    """Aggregate adaptation costs once per snapshot and run, never per task.

    Missing measurements remain null. A run with zero measured adaptation
    cost must explicitly record zeros. Partial run coverage is rejected.
    """
    if not costs:
        return {"status": "not_measured", "rows": []}
    fields = ("input_tokens", "output_tokens", "wall_seconds", "api_cost_usd")
    seen, grouped = set(), defaultdict(list)
    for record in costs:
        key = tuple(record.get(f) for f in ("strategy", "version", "run_id"))
        if (key[0] not in STRATEGIES or key[1] not in VERSIONS or key[2] not in run_ids):
            raise EvaluationError(f"Unexpected adaptation-cost record {key}")
        if key in seen:
            raise EvaluationError(f"Duplicate snapshot cost record {key}; do not repeat costs for each task")
        seen.add(key)
        parsed = {"run_id": key[2]}
        for field in fields:
            value = record.get(field)
            parsed[field] = None if value is None else _number(value, field)
        if all(parsed[f] is None for f in fields):
            raise EvaluationError(f"Cost record has no measured dimension: {key}")
        grouped[key[:2]].append(parsed)
    rows = []
    for (strategy, version), values in sorted(grouped.items()):
        if {r["run_id"] for r in values} != set(run_ids):
            raise EvaluationError(f"Incomplete cost runs for {strategy} {version}")
        row = {"strategy": strategy, "version": version, "run_count": len(values)}
        for field in fields:
            present = [r[field] for r in values]
            row[f"mean_{field}"] = (statistics.mean(present)
                                        if all(v is not None for v in present) else None)
        rows.append(row)
    return {"status": "measured_dimensions_only", "accounting_unit": "one adaptation per strategy stage run",
            "rows": rows}


def summarize_experiment(records: list[dict], manifest: dict) -> dict:
    """Produce stage metrics, per-run ECS, paired recovery and retention."""
    protocol = manifest.get("protocol", {})
    protocol_id = protocol_fingerprint(protocol)
    tasks = _unique_strings(manifest.get("task_ids"), "task_ids")
    runs = _unique_strings(manifest.get("run_ids"), "run_ids")
    indexed = validate_paired_records(records, task_ids=tasks, run_ids=runs,
                                      protocol_id=protocol_id)
    cohorts = manifest.get("cohort_by_version")
    if not isinstance(cohorts, dict):
        raise EvaluationError("cohort_by_version is required for recovery and retention analysis")
    for version in ("Middle", "Late"):
        mapping = cohorts.get(version)
        if not isinstance(mapping, dict) or set(mapping) != set(tasks):
            raise EvaluationError(f"Exact task cohort mapping required for {version}")
        if any(v not in ("changed", "retained") for v in mapping.values()):
            raise EvaluationError("Cohorts must be changed or retained")
    stage_rows, ecs_rows, paired_rows = [], [], []
    per_task_ecs = []
    for strategy in STRATEGIES:
        for version in VERSIONS:
            run_means = []
            for run in runs:
                run_means.append({"tf": statistics.mean(indexed[strategy, version, run, t]["tf"] for t in tasks),
                                  "pe": statistics.mean(indexed[strategy, version, run, t]["pe"] for t in tasks)})
            stage_rows.append({"strategy": strategy, "version": version,
                               "task_count": len(tasks), "run_count": len(runs),
                               "tf_mean": statistics.mean(r["tf"] for r in run_means),
                               "pe_mean": statistics.mean(r["pe"] for r in run_means),
                               "tf_run_sample_std": statistics.stdev(r["tf"] for r in run_means) if len(runs) > 1 else None,
                               "pe_run_sample_std": statistics.stdev(r["pe"] for r in run_means) if len(runs) > 1 else None})
        run_ecs = []
        for run in runs:
            value, details = ecs({t: [indexed[strategy, v, run, t]["tf"] for v in VERSIONS] for t in tasks})
            run_ecs.append(value)
            per_task_ecs.extend(dict(row, strategy=strategy, run_id=run) for row in details)
        ecs_rows.append({"strategy": strategy, "ecs_mean": statistics.mean(run_ecs),
                         "ecs_run_sample_std": statistics.stdev(run_ecs) if len(runs) > 1 else None,
                         "run_count": len(runs)})
        for version in ("Middle", "Late"):
            for cohort in ("changed", "retained"):
                selected = [t for t in tasks if cohorts[version][t] == cohort]
                deltas, losses, early_deltas = [], [], []
                improved = regressed = equal = 0
                for run in runs:
                    for task in selected:
                        old = indexed["no_update", version, run, task]["tf"]
                        now = indexed[strategy, version, run, task]["tf"]
                        early = indexed["no_update", "Early", run, task]["tf"]
                        delta = now - old
                        deltas.append(delta)
                        losses.append(max(0.0, -delta))
                        early_deltas.append(now - early)
                        improved += delta > 0
                        regressed += delta < 0
                        equal += delta == 0
                paired_rows.append({"strategy": strategy, "version": version, "cohort": cohort,
                                    "task_count": len(selected), "paired_observations": len(deltas),
                                    "tf_delta_vs_no_update": statistics.mean(deltas) if deltas else None,
                                    "positive_tf_loss_vs_no_update": statistics.mean(losses) if losses else None,
                                    "tf_delta_vs_early_no_update": statistics.mean(early_deltas) if early_deltas else None,
                                    "improved_count": improved, "regressed_count": regressed,
                                    "equal_count": equal, "status": "available" if deltas else "cohort_empty"})
    return {"evidence_kind": "IMPORTED_OFFICIAL_JUDGE_RESULTS", "protocol_id": protocol_id,
            "protocol": deepcopy(protocol), "task_ids": tasks, "run_ids": runs,
            "record_count": len(indexed), "stage_metrics": stage_rows, "ecs": ecs_rows,
            "ecs_per_task_per_run": per_task_ecs, "recovery_and_retention": paired_rows,
            "adaptation_costs": summarize_costs(manifest.get("adaptation_costs", []), run_ids=runs),
            "caveats": ["Protocol metadata are supplied declarations; review against actual run manifests.",
                        "Changed and retained cohorts must be fixed before viewing scores.",
                        "A single run has no estimable between-run standard deviation.",
                        "Cohort deltas are additional analysis, not official benchmark metric definitions."]}


def import_official_directories(manifest: dict, *, base_dir: str | Path = ".") -> list[dict]:
    """Import explicit official EVAL directories with immutable run metadata.

    Each entry requires strategy, version, run_id, path, metadata_path.
    Metadata must contain matching protocol_id, strategy, version, run_id and
    exact task_ids. Task files are <task_id>.json. No silent intersection.
    """
    protocol_id = protocol_fingerprint(manifest.get("protocol", {}))
    tasks = _unique_strings(manifest.get("task_ids"), "task_ids")
    if any(Path(t).name != t or t in (".", "..") for t in tasks):
        raise EvaluationError("Task IDs cannot contain filesystem path components")
    base_dir = Path(base_dir)
    entries = manifest.get("eval_directories")
    if not isinstance(entries, list) or not entries:
        raise EvaluationError("No official eval_directories configured")
    records, seen = [], set()
    for entry in entries:
        key = tuple(entry.get(f) for f in ("strategy", "version", "run_id"))
        if key in seen:
            raise EvaluationError(f"Duplicate eval directory for {key}")
        seen.add(key)
        if "metadata_path" not in entry:
            raise EvaluationError(f"Missing run metadata path for {key}")
        metadata_path = base_dir / entry["metadata_path"]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("protocol_id") != protocol_id:
            raise EvaluationError(f"Run metadata protocol mismatch in {metadata_path}")
        if any(metadata.get(field) != value for field, value in zip(("strategy", "version", "run_id"), key)):
            raise EvaluationError(f"Run metadata identity mismatch in {metadata_path}")
        if set(_unique_strings(metadata.get("task_ids"), "metadata task_ids")) != set(tasks):
            raise EvaluationError(f"Run metadata task subset mismatch in {metadata_path}")
        directory = base_dir / entry["path"]
        for task in tasks:
            path = directory / f"{task}.json"
            raw = path.read_bytes()
            payload = json.loads(raw)
            tf, pe = extract_official_scores(payload)
            records.append({"strategy": key[0], "version": key[1], "run_id": key[2],
                            "task_id": task, "tf": tf, "pe": pe,
                            "evidence_kind": "official_mcpevol_judge", "protocol_id": protocol_id,
                            "source_path": str(path), "source_sha256": hashlib.sha256(raw).hexdigest(),
                            "metadata_path": str(metadata_path)})
    # Validation catches missing strategy/stage/run entries and extra identities.
    validate_paired_records(records, task_ids=tasks, run_ids=manifest.get("run_ids"), protocol_id=protocol_id)
    return records
