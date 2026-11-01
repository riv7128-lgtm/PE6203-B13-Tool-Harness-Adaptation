#!/usr/bin/env python3
"""Import official judge artifacts, or generate labelled mechanical examples."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_adapt.analysis import write_failure_examples, failure_annotation_template
from harness_adapt.metrics import (EvaluationError, import_official_directories,
                                    summarize_experiment)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("official", help="Read complete official judge outputs")
    analyze.add_argument("--manifest", required=True, type=Path)
    analyze.add_argument("--records", type=Path, help="Optional already normalized official record list")
    analyze.add_argument("--output", required=True, type=Path)
    examples = sub.add_parser("local-failures", help="Execute two LOCAL_CONTRACT_TEST examples")
    examples.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "local-failures":
        paths = write_failure_examples(args.output)
        template_path = args.output / "official_failure_annotation_template.json"
        template_path.write_text(json.dumps(failure_annotation_template(), indent=2) + "\n")
        print(json.dumps({"evidence_kind": "LOCAL_CONTRACT_TEST", "official_benchmark_scores": None,
                          "paths": paths, "template": str(template_path)}, indent=2))
        return 0
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        records = (json.loads(args.records.read_text(encoding="utf-8")) if args.records else
                   import_official_directories(manifest, base_dir=args.manifest.parent))
        summary = summarize_experiment(records, manifest)
    except (EvaluationError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"Official analysis not generated: {error}", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "normalized_records.json").write_text(json.dumps(records, indent=2) + "\n")
    for key in ("stage_metrics", "ecs", "recovery_and_retention"):
        rows = summary[key]
        path = args.output / f"{key}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"status": "complete", "record_count": summary["record_count"],
                      "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
