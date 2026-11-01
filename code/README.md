# PE6203 Project 4 tool harness adaptation

This implementation delivers the three required strategies: no update, a deterministic complete refresh of normalized tool knowledge, and a selective tool-record patch. The core and tests use Python 3.10 or newer with the standard library. Real MCP execution additionally requires the MCP Python package and independently deployed benchmark servers. The delivered pilot contains 27 scored conditions from official tasks 133, 144 and 235, with one run and one independent judge session across three strategies and three actual server stages. This is a small adapter protocol pilot, not the full benchmark.

## Run the implemented local checks

From this code directory:

```bash
python3 -m unittest discover -s tests -v
python3 -m harness_adapt --help
```

The tests verify actual code behavior. Mock transports and local fixtures are clearly separate from official benchmark evidence and have no TF PE scores.

## Adapt tool knowledge

```bash
python3 fixtures/demo_patch.py --output evidence/local_patch
python3 -m harness_adapt adapt --old evidence/local_patch/early.json --new evidence/local_patch/middle.json --strategy selective_patch --out results/local_middle_selective.json
```

Use the actual fixture filenames in `fixtures/`; the fixture guide identifies their versions. The output includes a separate `.adaptation.json` audit. `serialized_update_bytes` is a byte count, never an estimated token count. The deterministic updates make zero LLM calls and incur zero model-update API charges; inference and judging are separate costs.

## Official source and protocol

Pinned repository: https://github.com/Octobrist/MCPEvol-Bench at commit `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`.

```bash
git clone https://github.com/Octobrist/MCPEvol-Bench.git official
git -C official checkout 888c779a0fe735f612ca62bdd1fdd7c9e6bf8701
python3 -m harness_adapt audit --repo official --out results/repository_audit.json
python3 -m harness_adapt prepare --repo official --out prepared --limit 12
```

The raw task file has 393 tasks. The intersection with the official `chosen_idx.json` has 201 tasks. Preparation copies the chosen task objects without changing questions or reference labels, freezes a deterministic subset before scores exist, and writes content hashes. The live frozen subset in prepared_live/ contains IDs 133, 144 and 235; complete original records are unchanged. Captured tools confirm 133 and 144 as changed and 235 as retained in both evolved stages.

The official checkout does not include live server bundles; follow its README download link to https://huggingface.co/datasets/anonymous2233/evol-servers. The reproduction/README.md documents the exact frozen source and portable setup for the selected servers. Prepare independent Early Middle Late servers using the official original iter3 iter5 releases. Review server dependencies and reset protocols in an isolated benchmark workspace before starting them. This package does not silently install or launch third-party server bundles.

## Capture and run the three conditions

Install the optional `mcp` Python package in a dedicated environment. Start the three prepared endpoints independently, then capture their real tool descriptions:

```bash
python3 -m harness_adapt capture --url http://127.0.0.1:3050/mcp --out snapshots/early.json
python3 -m harness_adapt capture --url http://127.0.0.1:3051/mcp --out snapshots/middle.json
python3 -m harness_adapt capture --url http://127.0.0.1:3052/mcp --out snapshots/late.json
```

Copy `configs/official.example.json` to your own config and fill the model identifiers, API base URLs, isolated workspace, annotation file tree, and a reviewed reset command as an argv list. Store credentials only in the configured environment variables `MODEL_API_KEY` and `JUDGE_API_KEY`; never add keys to a config or repository. The optional API backend uses these credentials. The executed pilot instead uses the codex_cli backend and normal saved ChatGPT login; no API key is required and no authentication file is read or exported by this code.

```bash
python3 -m harness_adapt preflight --config configs/official.json --repo official --snapshots snapshots --out results/preflight.json
python3 -m harness_adapt run-official --config configs/official.json --repo official --prepared prepared --snapshots snapshots --out results/official
```

Preflight returns exit code 2 if prerequisites are missing. Do not interpret preflight, prepared tasks, local fixtures, or successful unit tests as completed benchmark results. Run metadata contains no credential values.

## Fairness and integration details

Every task uses the same candidate server set across stages and strategies. All tools on those servers are included so renamed or newly added alternatives are available to the refreshed strategies. The no-update agent receives only the Early tool knowledge and stale routing; the execution endpoint remains the current stage. No current `list_tools` call or route repair occurs in the inference loop. Stable hashed function aliases disambiguate equal tool names from different servers. Their descriptions preserve the original qualified identity.

The fixed system prompt is read as a literal from the pinned upstream source, with a fixed experimental date rather than wall-clock drift. The executed CLI pilot fixes the model alias, CLI version, low reasoning effort, six action rounds, 12000 character tool observation limit, task subset, judge repetitions and rubric order. Temperature seed and token caps are not exposed by this backend and are explicitly null, so sampling is not claimed as controlled. Exact serving revision is unavailable. The context date is fixed, while the actual server clock used by time queries is not mocked. Environment state is reset before every strategy task stage run condition. Capture setup overhead is shared and excluded from adaptation-only costs.

The adapter reuses the official task objects and `build_mcp_bench_judge_prompt` rubric, but is an explicitly documented protocol extension rather than the published leaderboard implementation. Differences include all candidate-server tools instead of gold-tool filtering, globally unique aliases, strict round cap, fixed date, complete saved assistant evidence, and fixed rubric order. The upstream evaluator imports a missing `custom.analysis.mutation.utils` and references missing `real.json`; this adapter bypasses those broken imports without changing labels or scores.

No update and selective patch start from the same Early snapshot for both later stages. The experiment therefore measures independent persistent shifts from Early to Middle and Early to Late, not accumulated online learning. Output JSON records the exact agent-visible and execution snapshot hashes.

## Results and accounting

Each official condition saves `ANSWER`, `EVAL`, `HARNESS`, and `ADAPTATION` evidence. All three strategies must have the identical task stage run Cartesian product. The normalized records and `run_manifest.json` feed the strict metrics analyzer. Actual completed evidence is in ../results/live_benchmark and its validated summary in ../results/live_analysis. Raw CLI requests responses events usage and stderr are in ../results/live_model_calls. Infrastructure or transport errors are unscored invalid attempts, not low task scores. Stage workers use separate endpoints; conditions within one stage run serially. ECS is calculated per task as the mean of three TF scores minus their population standard deviation, then averaged over tasks. Missing or incomparable results cause a failure rather than silent task dropping.

Recovery and retention cohorts are identified from changes to the task's annotated required tool records. This is a structural exposure criterion, not an oracle that proves semantic solvability; manually inspect cohorts and replacement behavior before drawing retention claims. A subset with no retained tasks cannot establish retained-task performance.

This method copies authoritative changed records exactly. Complete refresh and selective patch can therefore produce equivalent effective schemas and equal task performance. The implementation does not promise a TF gain. Its measurable differences are update scope, unchanged knowledge preservation and processing cost. Unsupported global-rule changes are explicitly surfaced by the patch audit.

Individual contribution statements should reflect the work performed and subsequent revisions.

## Recompute the delivered results

```bash
python3 scripts/analyze_results.py official --manifest ../results/live_benchmark/run_manifest.json --records ../results/live_benchmark/records.json --output evidence/recomputed_live_analysis
```

The CLI backend is a stateless structured JSON proposal interface, not native API tool calling. Every action and judge is a fresh process with built in action tools disabled. Raw observations are retained separately from the bounded agent messages. The pinned official judge rubric is reused with a documented trajectory serialization extension. Agent and judge use the same model alias in separate sessions; shared model bias and a single run limit conclusions.

The current method exposes equivalent sorted model facing knowledge for full refresh and selective patch. Their structural benefit is the amount of tool knowledge rewritten, not a guaranteed behavioral difference. Actual late no update task 133 shows a stale required parameter rejection followed by recovery. The separate over update example is an explicit local fault injection and is not represented as a natural full refresh failure.

## Budgeted follow-up dated 29 October 2026

See ../results/supplement_20261029 and the package update note. The 162-cell plan stopped at 20 accepted cells and was abandoned. Only two missing Late/133 conditions were added; one existing no-update case was reused. These do not replace or pool with the old 27-cell pilot.

Run offline analysis only:

```bash
python supplement_20261029/summarize_supplement.py
```

This command does not start servers or call models. Historical experiment scripts require rebased paths and a new explicit budget; do not run the full-pilot launcher as a routine check.

Original recorded source is preserved separately in ../code_original_20261028.zip. Current code adds Windows environment handling, repetition support and actor-aware judge evidence. Use the archived source for historical protocol inspection; do not pool results across these changes.

## Output-equivalent implementation optimization

Active harness_adapt now uses indexed tool lookup, a per-operation reused diff, and one copy of unchanged records. The public independent preservation audit still recomputes changes. reference_harness preserves the previous implementation for comparison.

Offline reproduction, no model calls:

```bash
python scripts/benchmark_optimization.py --output ../results/optimization_rerun
python scripts/run_offline_checks.py --repo /path/to/pinned/MCPEvol-Bench --log ../results/offline_rerun.log
```

Without --repo, official-source comparison tests may skip. Timing results are hardware-dependent. Do not reuse the historical TF/PE/ECS as newly measured optimized-agent scores.
