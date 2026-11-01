# Evidence index

| Location | Purpose and interpretation |
|---|---|
| `live_benchmark/` | Original complete 27-condition pilot with trajectories, scores and adaptation outputs |
| `live_model_calls/` | Raw original model requests, responses, events and usage |
| `live_analysis/` | Original TF, PE, ECS, paired cohort analysis and tables |
| `live_deployment/` | Captured deployment and server probes |
| `local_failure_examples/` | Controlled local under-update and over-update examples; distinguish these from natural benchmark failures |
| `supplement_20261029/` | Separate environment, interrupted 20-condition batch, bounded Task 133 follow-up, and earlier local measurements |
| `optimization_20261029/` | Original-versus-optimized output comparisons, test log and 396 timing records |

See `supplement_20261029/Supplementary_Findings_EN.md` and `optimization_20261029/Optimization_Summary_EN.md`. The early environment diagnosis and local-result notes are explicitly historical and do not supersede the later full passing test logs.

Raw JSON, JSONL and logs retain original tool text, task data and machine paths. Some include Chinese source material; these are experimental records, not untranslated report prose. Reader-facing explanatory notes have English filenames and text. Source task labels and historical results were not rewritten to remove source-language characters.

Additional evidence:

- `official_metadata_audit/`: extracted metadata pairs and checks referenced by the report.
- `operational_review_20261101/`: the Task133 model-usage cross-check.
- `submission_checks_20261101/`: the offline software test log.
