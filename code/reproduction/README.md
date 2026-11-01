# Reproduce the frozen live pilot

The live subset is **133, 144, 235**, frozen before benchmark scores: three strategies × three stages × one run = **27 conditions**. `../prepared_live/` contains the unchanged official task objects and hashes.

The runtime and model are real. The Node tool bodies come from the published original/iter3/iter5 archives. Official description metadata is applied at proxy discovery before each strategy receives its stored harness. The Python time server is explicitly frozen across stages. Chart tools return the official `vis-chart` JSON specifications; this deployment does not claim to render PNGs.

## Inputs and prerequisites

- Python **3.12.14**, Node **24.19.0** (the observed delivery runtime), Git, and network access for public downloads/model calls. See `environment_versions.json`; the scripts accept explicit executable paths. Other interpreter/runtime versions are not verified by this delivery.
- Install the exact Python dependency snapshot in `requirements-live.lock.txt` into a dedicated virtual environment. This is a `pip freeze` version lock, not a wheel/hash lock; platform-specific wheel availability is not guaranteed.
- Codex CLI **`codex-cli 0.164.0-alpha.11.1`**, already normally logged in, with access to **`gpt-6.1-sol`**. No API key is required for this backend. Do not copy or export login files. The exact archived CLI release/model alias may not remain available later.
- Optional separate **`MCPEvol_Selected_Node_Runtime.tar.gz`** distributed beside the main project archive. It contains `extracted/original`, `extracted/iter3`, `extracted/iter5`; it is intentionally not duplicated into all six member packages.

All examples are run from this package's `code/` directory. Replace `/path/to/pilot` with a new writable location. The scripts derive code paths from their own location and generate runtime paths under the chosen root; there is no dependency on the author's `/Users/...` paths.

```bash
python3 -m venv /path/to/pilot/work/live_venv
/path/to/pilot/work/live_venv/bin/python -m pip install -r reproduction/requirements-live.lock.txt
/path/to/pilot/work/live_venv/bin/python reproduction/prepare_runtime.py --root /path/to/pilot --python /path/to/pilot/work/live_venv/bin/python --node /path/to/node --clone-official --runtime-archive /path/to/MCPEvol_Selected_Node_Runtime.tar.gz --no-launch
```

If the optional archive is unavailable, replace `--runtime-archive ...` with `--download`. This fetches public ZIP byte ranges and resolves each selected package's bundled dependency closure; it does not run npm install or substitute newer npm dependencies. The central directory hashes, extracted CRC/size checks, and complete runtime tree fingerprints must match before configs are emitted. The pinned archive LFS hashes are recorded as upstream expected identities; complete multi-GB archive bodies were not downloaded and those full-archive hashes were not independently recomputed.

Pinned sources:

- Benchmark `https://github.com/Octobrist/MCPEvol-Bench.git`, commit `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`.
- Dataset `anonymous2233/evol-servers`, revision `162e3ffbea1717ac8a20fe9b26465e29117229e4`.
- Node dependencies are the bundled versions; see `pinned_provenance.json` and complete tree fingerprints. The download fallback includes the original transport-probe package `@guanxiong/mcp-server-time`, but the formal five-server proxy does not start it.
- Python dependencies are the exact saved live environment, including `mcp==1.25.0` and `mcp-server-time==2026.1.26`. The original official uvx command was unpinned; this explicit freeze is a disclosed deployment choice.

`--repo /path/to/existing/MCPEvol-Bench` can reuse a clean checkout at the pinned commit instead of `--clone-official`. `--no-launch` documents the default preparation-only behavior: preparation never starts downloaded server programs or model calls.

## Execute a new pilot

Review the generated `work/live_runtime/{early,middle,late}_proxy.json` and `experiment_config.json`, then run:

```bash
/path/to/pilot/work/live_venv/bin/python reproduction/run_experiment.py --root /path/to/pilot
```

This starts the inspected five-server proxies on localhost ports 3050–3052, waits for readiness, captures actual metadata, runs preflight, executes all conditions, and analyzes only a complete result grid. Every condition resets the corresponding subprocess environment. The launcher shuts down its own proxies when it finishes. Existing occupied ports are rejected instead of silently reusing another experiment.

New evidence is written to `/path/to/pilot/results/live_reproduction/` and `live_reproduction_model_calls/`, not into the archived delivery evidence. Rebased absolute config paths change the protocol fingerprint, which is correct for a new run. Do not combine records from two fingerprints or overwrite archived scores with rerun scores.

To validate only the local implementation, no external calls are needed:

```bash
python3 -m unittest discover -s tests -v
```

## What is and is not controlled

The model/judge alias, CLI release, low reasoning effort, strict JSON action protocol, maximum six rounds, 12,000-character tool-result limit, fixed prompt date, task objects, source snapshots and official rubric are fixed. Agent and judge use separate fresh ephemeral CLI sessions. CLI built-in tools are disabled; only externally executed proposals from the supplied allowed-tool schema are accepted.

The installed CLI does **not** expose temperature, seed, or output-token cap for this protocol. Their config values are null; `run_seeds: [0]` is an ignored compatibility placeholder. Do not describe this as fixed sampling, independent repeated trials, or bitwise deterministic reproduction. The serving model revision and dollar cost are unavailable, even though requested model, real token usage and elapsed time are logged. The same model alias judges the agent, so self-judge bias remains despite separate sessions.

This is a three-task convenience pilot with one run per condition. There are no run-level confidence intervals or significance claims. Clock tools remain time dependent: a fixed prompt date does not freeze real clock outputs. Middle uses the root official DESC layer; Late uses all four layers root-to-deep. This disclosed mapping and the proxy's server-qualified descriptions are an adapter protocol, not a claim of exact published leaderboard replication.

Transport probes, synthetic schema probes, unit tests and static metadata audits are separate evidence and must not be converted into TF/PE/ECS. Formal metrics require the saved real agent trajectories and official judge outputs.

## Supplementary Windows environment

The fresh download passed per-file archive SHA checks, but Early has 11386 files versus the old runtime tree 11390; the four-file difference is unresolved. Middle/Late tree fingerprints match. Use the explicit source-validation helper only for a separately labelled new environment; do not edit the old expected fingerprints to claim exact replication. Windows ordering uses case-sensitive path-component sorting. Normal Windows system/profile variables must be retained by the CLI adapter. New model runs require a separately approved budget.

The active code includes a local performance optimization. Historical model scores remain historical. For zero-model offline reproduction use scripts/benchmark_optimization.py; the old implementation is in reference_harness. No new agent experiment is needed to reproduce the reported local timing comparison.
