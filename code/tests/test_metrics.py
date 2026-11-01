import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from harness_adapt.analysis import local_failure_examples
from harness_adapt.metrics import (EvaluationError, VERSIONS, STRATEGIES, ecs,
    extract_official_scores, import_official_directories, protocol_fingerprint,
    summarize_costs, summarize_experiment)


def experiment():
    manifest = {"protocol": {"model_id": "unit-test-model-not-a-benchmark-result",
        "decoding": {"temperature": 0}, "judge": {"model": "unit-test-judge", "repeats": 5},
        "benchmark_commit": "unit-test-only"}, "task_ids": ["a", "b"], "run_ids": ["r1"],
        "cohort_by_version": {v: {"a": "changed", "b": "retained"} for v in ("Middle", "Late")}}
    pid = protocol_fingerprint(manifest["protocol"])
    records = []
    for strategy in STRATEGIES:
        for version in VERSIONS:
            for task in ("a", "b"):
                tf = 8 if version == "Early" else 4 if task == "a" else 8
                if strategy == "selective_patch" and version != "Early" and task == "a":
                    tf = 7
                if strategy == "full_rewrite" and version != "Early" and task == "b":
                    tf = 6
                records.append({"task_id": task, "strategy": strategy, "version": version,
                    "run_id": "r1", "tf": tf, "pe": 7, "protocol_id": pid,
                    "evidence_kind": "official_mcpevol_judge"})
    return manifest, records


class MetricsTests(unittest.TestCase):
    def test_official_mean_fields(self):
        payload = {"eval_result": {"aggregate": {"task_fulfillment_mean": 7.2,
            "planning_and_efficiency_mean": 8.6, "task_fulfillment": 7,
            "planning_and_efficiency": 9, "successful_runs": 5}}}
        self.assertEqual(extract_official_scores(payload), (7.2, 8.6))

    def test_bad_mean_does_not_fallback(self):
        for invalid in (None, True, float("nan"), 0, 11, "7"):
            with self.subTest(value=invalid), self.assertRaises(EvaluationError):
                extract_official_scores({"eval_result": {"aggregate": {
                    "task_fulfillment_mean": invalid, "task_fulfillment": 7,
                    "planning_and_efficiency_mean": 6}}})

    def test_ecs_not_aggregate_before_variance(self):
        value, rows = ecs({"a": [10, 1, 10], "b": [1, 10, 1]})
        # Per-stage means are all 5.5, but every task is unstable.
        self.assertAlmostEqual(value, 5.5 - (18 ** 0.5))
        self.assertLess(value, 2)
        self.assertEqual(len(rows), 2)

    def test_formula_matches_official_source(self):
        root = Path(__file__).resolve().parents[5]
        path = root / "work/official/MCPEvol-Bench/src/custom/analysis/answer/evolutionary_volatility.py"
        if not path.exists():
            self.skipTest("Official checkout not packaged; direct formula tests remain available")
        spec = importlib.util.spec_from_file_location("official_ecs_test", path)
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        reference = module._compute_row("a", 8, 5, 7)
        value, _ = ecs({"a": [8, 5, 7]})
        self.assertAlmostEqual(value, reference.mean - reference.stdev)

    def test_complete_recovery_retention(self):
        manifest, records = experiment()
        summary = summarize_experiment(records, manifest)
        self.assertEqual(summary["record_count"], 18)
        recovery = next(r for r in summary["recovery_and_retention"] if
            (r["strategy"], r["version"], r["cohort"]) == ("selective_patch", "Late", "changed"))
        self.assertEqual(recovery["tf_delta_vs_no_update"], 3)
        retained = next(r for r in summary["recovery_and_retention"] if
            (r["strategy"], r["version"], r["cohort"]) == ("full_rewrite", "Late", "retained"))
        self.assertEqual(retained["positive_tf_loss_vs_no_update"], 2)
        self.assertIsNone(summary["ecs"][0]["ecs_run_sample_std"])

    def test_reject_missing_duplicate_mismatch_and_local(self):
        manifest, records = experiment()
        for kind in ("missing", "duplicate", "protocol", "local"):
            bad = copy.deepcopy(records)
            if kind == "missing": bad.pop()
            elif kind == "duplicate": bad.append(bad[0])
            elif kind == "protocol": bad[0]["protocol_id"] = "different"
            else: bad[0]["evidence_kind"] = "LOCAL_CONTRACT_TEST"
            with self.subTest(kind=kind), self.assertRaises(EvaluationError):
                summarize_experiment(bad, manifest)

    def test_cohorts_must_cover_exact_tasks(self):
        manifest, records = experiment()
        del manifest["cohort_by_version"]["Late"]["b"]
        with self.assertRaises(EvaluationError): summarize_experiment(records, manifest)

    def test_costs_not_duplicated_per_task(self):
        record = {"strategy": "selective_patch", "version": "Late", "run_id": "r1",
                  "wall_seconds": 0.25}
        summary = summarize_costs([record], run_ids=["r1"])
        self.assertEqual(summary["rows"][0]["mean_wall_seconds"], .25)
        self.assertIsNone(summary["rows"][0]["mean_api_cost_usd"])
        with self.assertRaises(EvaluationError): summarize_costs([record, record], run_ids=["r1"])
        with self.assertRaises(EvaluationError): summarize_costs([record], run_ids=["r1", "r2"])

    def test_official_directory_import_and_missing_file(self):
        manifest, records = experiment()
        pid = protocol_fingerprint(manifest["protocol"])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manifest["eval_directories"] = []
            for strategy in STRATEGIES:
                for version in VERSIONS:
                    folder = base / strategy / version
                    folder.mkdir(parents=True)
                    metadata = dict(protocol_id=pid, strategy=strategy, version=version,
                                    run_id="r1", task_ids=["a", "b"])
                    (folder / "metadata.json").write_text(json.dumps(metadata))
                    manifest["eval_directories"].append(dict(strategy=strategy, version=version,
                        run_id="r1", path=str(folder.relative_to(base)),
                        metadata_path=str((folder / "metadata.json").relative_to(base))))
                    for task in ("a", "b"):
                        payload = {"eval_result": {"aggregate": {
                            "task_fulfillment_mean": 7, "planning_and_efficiency_mean": 8}}}
                        (folder / f"{task}.json").write_text(json.dumps(payload))
            result = import_official_directories(manifest, base_dir=base)
            self.assertEqual(len(result), 18)
            self.assertTrue(all(len(r["source_sha256"]) == 64 for r in result))
            (base / "selective_patch/Late/a.json").unlink()
            with self.assertRaises(FileNotFoundError): import_official_directories(manifest, base_dir=base)

    def test_failure_cases_are_executed_local_only(self):
        cases = local_failure_examples()
        self.assertEqual(set(cases), {"under_update", "over_update"})
        for case in cases.values():
            self.assertEqual(case["evidence_kind"], "LOCAL_CONTRACT_TEST")
            self.assertFalse(case["official_benchmark"])
            self.assertIsNone(case["scores"])
            self.assertTrue(case["trajectory"][-1]["result"]["ok"])
        self.assertEqual(cases["under_update"]["trajectory"][2]["result"]["error"], "MissingRequiredParameter")
        self.assertEqual(cases["over_update"]["trajectory"][2]["result"]["error"], "WrongRoute")


if __name__ == "__main__":
    unittest.main()
