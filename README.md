# Tool Harness Adaptation under Environment Change

PE6203 Group Project 4. This repository contains the adaptation code, reproducibility materials, experimental evidence, formal group report and English presentation.

## Deliverables

| Assignment requirement | Files |
|---|---|
| Adaptation pipeline | `code/harness_adapt/runner.py`, `official.py` and `code/reproduction/` |
| Developed selective adaptation method | `code/harness_adapt/changes.py`, `patch.py` and `validation.py` |
| No-update and full-rewrite baselines | `code/harness_adapt/baselines.py` |
| Configurations, commands and raw logs | `code/configs/`, `code/reproduction/`, `code/prepared_live/`, `results/` |
| Main results, recovery/retention, update costs, failures and discussion | [Formal group report](reports/Group_Technical_Report_EN.docx) |
| Method, integration, comparisons, failures and conclusions | [English presentation](presentation/Presentation_EN.pptx) |

## Run and inspect

- [Code and commands](code/README.md)
- [Pinned live experiment reproduction](code/reproduction/README.md)
- [Experimental evidence index](results/README.md)
- [Sources and requirements](docs/Sources_and_Requirements.json)
- [AI assistance](docs/AI_Assistance.md)
- [Third-party source notice](code/THIRD_PARTY_NOTICES.txt)

Offline demonstration from the repository root:

```bash
cd code
python fixtures/demo_patch.py --output ../results/local_demo_rerun
```

Full offline checks, using an existing official checkout at the recorded commit:

```bash
python scripts/run_offline_checks.py --repo /path/to/MCPEvol-Bench --log ../results/offline_rerun.log
```

These commands do not call a model. Live model trials require the dependencies, server setup and model access documented in `code/reproduction/README.md`. Use separate output paths rather than overwrite archived evidence.

## Evidence and interpretation

The original pilot contains 27 scored conditions across three tasks, three stages and three strategies. Supplementary trials and local timings are reported separately. Selective patching reduces serialized update bytes by 91.71% in Middle and 86.60% in Late. The optimized selective implementation reduces median local update time by 43.4%–65.9% relative to its original version, while full rewrite remains faster. Historical TF/PE/ECS scores are not relabelled as optimized-agent trials.

The original implementation in `code/reference_harness/` is required by the optimization reproduction script. The formal three-task subset is under `code/prepared_live/`; source task objects and labels are unchanged. Raw task and log records retain source-language text and historical environment paths.

There is one formal group report and one English presentation. Historical paths `Group_Project/code` and `Group_Project/results` correspond to `code/` and `results/` here. Personal reports are submitted separately by email and are not included in the repository.
