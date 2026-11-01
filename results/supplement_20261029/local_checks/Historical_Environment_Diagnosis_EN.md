# Historical environment diagnosis and proposed experiments

This is an earlier diagnostic note, not the final experiment plan or final test status. The final follow-up and optimization records report 79 passing checks with no skips. The proposed 162-condition expansion below was not completed.

At this diagnostic stage, 79 tests were discovered: 76 passed and three were skipped because the pinned official source was not supplied. There were no failures or errors in that diagnostic run; see `test_diagnostic.log`.

Two earlier model-backend test errors occurred while creating a default temporary subdirectory (`WinError 5`), before any model request. Redirecting temporary paths into the workspace resolved them. An infrastructure test also stalled while creating a Windows asyncio event loop (`socket._fallback_socketpair` followed by `accept`), before tool execution. The same script completed outside the restricted environment, indicating a local execution restriction rather than an observed adaptation-algorithm failure. Normal localhost loopback access is required.

Python 3.12.14 was available in the bundled runtime; a global reinstall was unnecessary. At this stage, a dedicated environment, locked MCP/httpx/anyio dependencies, pinned official source, and original/iter3/iter5 server runtime files still needed preparation. The local CLI was 0.165.0-alpha.1.2 rather than 0.164.0-alpha.11.1, and Node was 24.22.1 rather than 24.19.0. These differences require a separate experimental batch. Model connectivity had not yet been verified.

The historical proposal was to prepare dependencies and official source, rerun skipped checks, verify server reset behavior, run one end-to-end task, and then consider six tasks across three stages, three strategies and three runs (162 conditions). That expansion was interrupted after 20 accepted conditions. It was replaced with the bounded two-condition follow-up, not resumed as a mandatory plan.

The proposal also called for fixed task selection and judge evidence, explicit budgets, separate infrastructure failures, and separate reporting of local timings. It did not require a favorable outcome. Implementation changes constitute a separate version, and controlled failures must not be represented as natural benchmark failures.
