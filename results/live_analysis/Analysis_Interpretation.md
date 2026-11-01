# Independent audit of the completed live pilot

Reviewed 28 October 2026. The analysis is read-only with respect to official tasks, snapshots, model logs, EVAL artifacts and recorded scores. Script: work/analyze_live_results.py. Derived outputs: Group_Project/results/live_analysis.

## Complete grid and provenance

The accepted experiment contains exactly 27 cells: task IDs 133, 144 and 235, three stages, three strategies and one run. All three task objects exactly match the original official task records. The frozen task-content hash is e0a434ee37820fd08ab3aa7095b7006ad8b26218ec8953b2419c48ee8c8443d9.

I independently loaded every expected EVAL file rather than trusting a reported count. Each file's path identity agrees with its normalized record. Its original judge TF and PE agree exactly with the normalized score. All protocol hashes match the frozen manifest, and saved task harness hashes match each case's metadata. The complete EVAL grid and records.json contain the same records, so parallel aggregation and the final resume did not lose or duplicate accepted cells.

The script additionally checks every linked actor and judge CLI call. Request and output-schema hashes match saved inputs. Accepted call status is COMPLETED_WITHOUT_BUILTIN_ACTIONS. Actor allowed_tools exactly match the saved selected harness rendering, and the question matches the fixed task question. Requested model aliases match the frozen configuration. Re-parsing event logs finds no forbidden built-in action item. No CLI call ID is reused across accepted cells.

These checks validate the saved record and protocol consistency. They do not establish a resolved serving-model revision or turn same-model judging into independent human verification.

## Actual cohorts and change coverage

Frozen captured snapshots contain 78, 79 and 81 tools for Early, Middle and Late. Recomputed cohorts exactly match the run manifest:

| Evolved stage | Changed tasks | Retained task |
| --- | --- | --- |
| Middle | 133 and 144 | 235 |
| Late | 133 and 144 | 235 |

Task 133 depends on math-mcp validate_syntax, whose required parameter contract changes. Available candidate tools also include real additions, establishing Tool-level inventory coverage. Task 144 depends on official time-mcp description and parameter-description overlays. Task 235 uses unchanged official chart tool specifications.

Description leaves nested inside inputSchema remain description changes for coverage interpretation. The generic detector labels any inputSchema difference Parameter, but that software path category alone should not be presented as proof of structural parameter mutation. The actual validate_syntax required-field change separately supplies structural Parameter coverage.

## Equal model knowledge

knowledge_equivalence.json checks all 9 task-stage combinations. Full refresh and selective patch have equal rendered model-facing tool schemas, descriptions and order, and equal execution routing for every combination. Raw snapshot hashes can differ because selective patch preserves original record order, while agent_tools sorts by identity before presentation.

For retained task 235, no update also exposes the same rendered tools as both update methods in all stages. Task 235 therefore measures a small unchanged-workflow retention control, not resilience across a large unaffected population.

The equality result is central to causal interpretation. A numerical difference between full refresh and selective patch under this representation could arise from uncontrolled generation, live clock timing or judge variability. It could not by itself establish superior patch semantics. The measured distinction is update scope and serialized payload size.

## Actual independent judge scores

| Strategy | Early TF PE | Middle TF PE | Late TF PE | ECS |
| --- | --- | --- | --- | --- |
| No update | 10.00 10.00 | 10.00 10.00 | 10.00 8.67 | 10.00 |
| Full refresh | 10.00 10.00 | 10.00 10.00 | 10.00 10.00 | 10.00 |
| Selective patch | 10.00 10.00 | 10.00 10.00 | 10.00 10.00 | 10.00 |

These are saved judge scores, not a claim of human-verified perfect completion. All TF and ECS values reach the ceiling on this small convenience subset. There is one run and one same-model judge per cell. Between-run uncertainty is unavailable. The three-task result cannot establish population robustness, superiority or significance.

The raw Late no-update task-133 score is TF 10 and PE 6. The remaining Late no-update tasks have PE 10, yielding the stage average of 8.6666666667. Preserve those scores exactly.

## Real under-update trajectory and attribution limit

Source: results/live_benchmark/run_0/late/no_update/EVAL/133.json. The saved observation shows math-mcp_1mcp_validate_syntax called without the newly required allow_variables argument. The actual evolved server rejects it. Later in the same task trajectory, the actor supplies the flag and the same tool succeeds. failure_candidates.json links the raw file hash, observation index, old and current required sets, actual arguments and later success.

The judge received current tool schemas, while the no-update actor received Early schemas. Its PE rationale incorrectly assumes the actor had the new required flag in its supplied schema. Therefore the PE 6 score and observed retry are real data, but the rationale does not show that the actor ignored a rule it already knew. Do not edit the frozen score or silently rescore it. Disclose this information-asymmetry limitation alongside the efficiency observation.

No natural over-update failure is established. Full refresh does not intentionally corrupt unrelated routes, and its model knowledge matches selective patching. A retention score difference alone would not establish over-update. Keep the separate controlled route-corruption example labelled LOCAL_CONTRACT_TEST, with null benchmark scores. If presenting an actual MCP bad-route replay, label it a deliberate replay intervention and preserve its corrective control separately from the 27 formal cells.

## Invalid attempt and accepted retry

attempt_audit.json records one INVALID_INFRASTRUCTURE_NOT_SCORED artifact: Middle full_rewrite task 144, actor phase, TimeoutExpired at the configured 300-second limit. Its scores are null. The matching frozen condition later completed after resume, while already completed cells remained cached.

The model-log directory contains 93 completed model calls and one failed call. Two completed actor calls are unlinked to the final accepted grid because they preceded the timeout in an abandoned attempt. These are retained evidence and must not be counted as additional formal task samples. The failed call has unknown usage, not fabricated zero tokens. The script lists these unlinked calls explicitly rather than assuming every model log belongs to an accepted cell.

Accepted CLI calls are logged separately in accepted_model_calls.json. Account usage is measured tokens, not a known API bill. Dollars remain null. Deterministic adaptation has its own zero-LLM-call cost records and measured serialized byte counts.

## Parallel execution review

Each stage has one worker and its own endpoint and process set. Strategies and tasks remain serial inside a stage. The stage reset command affects only that stage's services. A records lock protects append and writes, and final joining precedes sorting and final records persistence. The final complete-grid audit found no lost cells or duplicates.

The runner persists snapshot harness and adaptation-cost artifacts and reuses them on resume. Cached EVAL files are accepted only under the same protocol hash. The one timeout is kept as an invalid attempt rather than converted to a low task score. No additional parallel test was added after the final verification count of 79, as requested by the primary agent.

## Derived files and rebuilding

- summary.json: strict paired metrics from summarize_experiment, with the same original TF PE ECS values.
- knowledge_equivalence.json: actual-snapshot cohorts and model-facing equality for all task-stage combinations.
- attempt_audit.json: invalid attempts, model status counts and calls not linked to accepted cells.
- failure_candidates.json: one observed stale-required-parameter candidate, human-review status and judge caveat.
- accepted_model_calls.json: accepted call IDs, provenance hashes, roles and measured token usage.
- analysis_status.json: complete validated 27-cell grid and matching records.json.
- stage_metrics.csv, ecs.csv, recovery_and_retention.csv: exported derived tables.

Run from the task workspace:

    python3 work/analyze_live_results.py

The standard code/scripts/analyze_results.py official command can also recompute the core summary directly from the same normalized records and manifest. The independent audit files remain relevant even if the primary agent rewrites summary.json through that standard command. They do not modify formal outcomes or task selection.

## Report and slide consistency review

The current live report builder correctly separates the real stale-call failure from the controlled over-update example and records the judge information asymmetry. The live deck uses actual metric rows from summary.json, reports byte reductions as serialized representation costs, and states that full refresh and selective patch expose equal knowledge. Builders use the final 79-test software count. The 17-pair 85-check static audit remains separate from the 27 measured task conditions.
