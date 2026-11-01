# Historical local update measurements

These offline experiments use synthetic tool information. They are not official task trials and produce no TF, PE, or ECS scores. Original benchmark scores remain unchanged. These measurements predate implementation optimization.

Each method is warmed up once and measured seven times per scenario, rotating method order. Timing includes in-memory updating and internal checks. Independent output verification, file I/O, discovery, model inference and judging are excluded.

| Tools | Changes | Method | Median ms | Minimum to maximum ms | Update bytes |
|---:|---:|---|---:|---:|---:|
|100|1|no_update|0.697|0.686—0.737|0|
|100|1|full_rewrite|0.733|0.686—1.349|21275|
|100|1|selective_patch|8.882|8.613—9.297|296|
|100|10|no_update|0.715|0.682—0.993|0|
|100|10|full_rewrite|0.708|0.702—0.762|21572|
|100|10|selective_patch|9.731|9.690—10.110|2492|
|100|50|no_update|0.717|0.696—1.343|0|
|100|50|full_rewrite|0.724|0.696—0.759|22892|
|100|50|selective_patch|14.399|13.999—20.072|12292|
|300|3|no_update|2.373|2.259—2.492|0|
|300|3|full_rewrite|2.321|2.146—2.355|63941|
|300|3|selective_patch|30.633|29.748—33.021|784|
|300|30|no_update|2.450|2.356—2.546|0|
|300|30|full_rewrite|2.533|2.292—2.607|64832|
|300|30|selective_patch|33.968|33.351—35.025|7392|
|300|150|no_update|2.404|2.242—4.638|0|
|300|150|full_rewrite|2.336|2.219—2.357|68792|
|300|150|selective_patch|46.740|46.485—48.768|36842|
|1000|10|no_update|8.232|7.891—12.786|0|
|1000|10|full_rewrite|8.103|7.472—8.991|213272|
|1000|10|selective_patch|155.327|151.809—158.776|2492|
|1000|100|no_update|8.647|8.363—9.073|0|
|1000|100|full_rewrite|8.974|8.171—9.231|216242|
|1000|100|selective_patch|171.054|170.716—174.920|24542|
|1000|500|no_update|8.310|8.213—9.355|0|
|1000|500|full_rewrite|8.744|8.542—13.376|229442|
|1000|500|selective_patch|219.809|216.381—224.839|122942|

Measured outputs passed strategy consistency, unrelated-knowledge preservation and input-immutability checks. Correct no-update behavior means retaining old information, not adapting successfully.

Smaller update volume does not imply less computation. The original selective implementation performed repeated comparisons and checks and used linear name searches. These results do not characterize every selective algorithm. Seven timing repetitions are not seven independent model trials.

In the boundary control, a global-policy change was flagged as unsupported and the old policy was retained. Tool-level success does not mean all target knowledge was synchronized. No agent was run in that control, so no real task failure is claimed.

At this early stage, all 20 patch checks passed, but a full-suite attempt encountered two backend errors and an infrastructure stall and was stopped without a complete result. These issues were later diagnosed, and the final follow-up and optimization verification passed all 79 checks. See the separate final records. This early measurement did not modify the algorithm or run model tasks; later work is documented separately.
