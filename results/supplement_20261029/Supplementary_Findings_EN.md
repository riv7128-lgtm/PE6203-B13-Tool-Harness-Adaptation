# Supplementary findings

## Focused follow-up

Only the two missing update strategies for Late Task 133 were newly scored. A matching no-update record from the interrupted batch is reused. This gives one observation per strategy, not three repetitions and not a completed 162-condition experiment.

| Strategy | TF | PE | Tool calls | Failed calls |
|---|---:|---:|---:|---:|
| No update | 10 | 10 | 3 | 1 |
| Full rewrite | 10 | 10 | 1 | 0 |
| Selective patch | 10 | 10 | 2 | 0 |

The no-update trajectory contains rejection of a call missing `allow_variables`, followed by correction. Neither update trajectory contains that error. Equal scores do not imply identical trajectories. PE follows the benchmark redundancy rubric, rather than counting all tool errors. Different action choices and one observation prevent a stable efficiency ranking. Full refresh used only the security-guidance tool, without an explicit math-validation call; the high TF score should be interpreted with this limitation.

The earlier 189 local timings show a smaller update payload but slower computation for the original selective implementation. With 1,000 tools and 10 changes, full refresh takes a median 8.103 ms and selective patching 155.327 ms; payloads are 213,272 and 2,492 bytes respectively. This does not prove lower total time or monetary cost.

The 20 accepted interrupted-batch records do not form a complete strategy comparison. Tasks 249, 291, and 448 lack some numerical inputs. Their observed TF of 1 is an input-completeness diagnostic, not evidence of evolution-induced failure.

The bounded follow-up used seven model calls including connectivity, 259,569 input tokens and 2,548 output tokens, without automatic retry. Historical batch usage is separate. A budget reservation check temporarily stopped execution; only the final judge call was subsequently completed after calibration using measured usage under the same protocol.

## Evidence boundaries

The original 27-condition pilot retains its scores and ECS. The incomplete batch is not pooled across strategies. The single-stage follow-up has no ECS or significance claim. The controlled over-update example remains labelled `LOCAL_CONTRACT_TEST`. Later implementation optimization is reported separately in `../optimization_20261029/`.
