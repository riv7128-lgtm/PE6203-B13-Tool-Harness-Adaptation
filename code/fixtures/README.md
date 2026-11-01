# Local contract fixtures

These fixtures validate metadata detection, patch scope, and illustrative failure
mechanisms. They are not a replacement for MCPEvol-Bench, an LLM agent, or its
judge. They contain no TF, PE, or ECS task scores.

Run from the code directory:

```bash
python fixtures/demo_patch.py --output evidence/local_patch
python -m unittest discover -s tests -p test_patch.py -v
```

The script writes three tool-knowledge snapshots, detected changes, the updated
harness and its structural audit, and two executable local call trajectories.
The under-update trajectory uses a stale parameter. The over-update trajectory
is an explicitly fault-injected negative control on an unrelated tool. The
local dispatcher returns illustrative values only and does not contact weather
or filesystem services.

The selective method updates complete records for affected tools, along with
their keyed usage rules and routes. It preserves unrelated tools, global rules,
and other top-level metadata. It reports global-policy changes as unsupported.
The example uses an explicit reports.save to reports.write rename map for audit
provenance. Without that map the same change is represented as deletion plus
addition; the algorithm does not infer functional equivalence.
