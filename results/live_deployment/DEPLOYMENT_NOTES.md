# Official server release deployment evidence

## Ready deployment

Five servers for the final prespecified task subset 133 144 235 are available in deployments/early.json deployments/middle.json and deployments/late.json. Each deployment contains math-mcp mcp-ai-agent-guidelines time-mcp @umengfe/mcp-server-chart and the unchanged Python time server. The optional_transport_probe_servers section records @guanxiong/mcp-server-time and calculator commands for separate transport probes; it is not automatically started by the primary proxy.

Node uses the bundled executable /Users/huangyu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node. Its args point to the exact extracted package entrypoint and cwd is the corresponding original iter3 or iter5 release root. The Python time command is the frozen work/live_venv/bin/mcp-server-time with --local-timezone=America/New_York. The primary agent froze its distribution at 2026.1.26 across stages because the public original config used unpinned uvx. The optional calculator is similarly frozen at 0.2.1. The Python freeze is a disclosed deployment choice rather than a claimed historical bundle version.

Start the primary agent's inspected proxy with the live Python environment, for example:

```bash
work/live_venv/bin/python outputs/PE6203_Project4/Group_Project/code/scripts/stdio_http_proxy.py --config work/live_servers/deployments/early.json --port 3050
work/live_venv/bin/python outputs/PE6203_Project4/Group_Project/code/scripts/stdio_http_proxy.py --config work/live_servers/deployments/middle.json --port 3051
work/live_venv/bin/python outputs/PE6203_Project4/Group_Project/code/scripts/stdio_http_proxy.py --config work/live_servers/deployments/late.json --port 3052
```

The primary agent may generate its final configs from these records to use its current official overlay adapter. The metadata files contain both ordinary tool description overrides and parameter description JSON pointers. Do not replace only whole tool descriptions while dropping parameter descriptions.

## Fixed dataset provenance

Dataset anonymous2233/evol-servers is pinned at full revision 162e3ffbea1717ac8a20fe9b26465e29117229e4. The precision revision API tree was fetched and compared with the originally captured main tree. Every file path size git blob OID and LFS OID matched. pinned_provenance.json contains this comparison and the cryptographic hashes of all three downloaded ZIP central directories. Future extraction requests in index_remote_zips.py use resolve/fullrevision rather than main.

Archive sizes are original_servers.zip 1218495812 bytes iter3_servers.zip 1088423924 bytes and iter5_servers.zip 1088574402 bytes. The public dataset exposes these three complete archives and no individual server subdirectories. HTTP Range was actually supported and returned matching 206 Content-Range responses. Only ZIP directories and selected package spans were transferred; full archives were not downloaded.

Central directories contain 335955 328463 and 328602 entries respectively and occupy 48361199 46964744 and 46986231 bytes. The expected whole-archive LFS hashes are recorded from Hugging Face metadata; they were not recomputed over full archives because the full archives were not fetched. Every independently extracted file was checked against its ZIP entry CRC and size, and its SHA256 was recorded in a package manifest. Cross-stage reuse occurs only when all relative filenames CRCs sizes and compressed sizes match for the same package path. Reuse is recorded instead of pretending a second network transfer occurred.

The four core Node server dependency closures each contain 242 declared package paths and no unresolved declared dependencies. Chart's closure contains 105 package paths and shares most dependencies with the core closure. Core compressed range transfers were 32271653 bytes for original 6874088 for iter3 and 6878308 for iter5. Chart added 872726 original bytes and reused identical records for the two later releases. Exact file hashes package versions and copied-from paths remain in *_closure_manifest.json and package_records.

Notable frozen dependency versions are @modelcontextprotocol/sdk 1.27.1 root zod 3.25.76 time-mcp's nested zod 4.3.6 commander 14.0.3 decimal.js 10.6.0 and dayjs 1.11.19. They were taken from the official archives, not upgraded by npm install.

## Actual stdio checks

probe_stdio_servers.py was executed with work/live_venv/bin/python. All twelve Node server and stage combinations initialized and listed tools successfully. Math exposes 6 6 7 tools across original iter3 iter5. Guidelines exposes 36 37 38. Time-mcp exposes 6 6 6. Chart exposes 28 28 28. Full raw schemas call results and stderr logs are saved in stdio_probes with evidence_kind OFFICIAL_SERVER_TRANSPORT_PROBE_NOT_BENCHMARK.

Math validate_syntax with expression 2+2 is accepted in original and iter3. The same old arguments produce isError true in iter5. Supplying the new required allow_variables false restores successful execution. This is a direct native-server contract observation and is not an LLM performance measurement.

The original to iter3 guidelines tools add constitution-validator, and iter3 to iter5 adds prompt-version-manager. The late math server adds batch_evaluate. Actual server bodies and schemas reflect these changes; no mutation was invented locally.

Time-mcp prints Starting Time MCP server on stdout before JSON-RPC. The MCP SDK reports this line as a parse diagnostic but initialization and real current_time calls succeed in all three releases. The downloaded source has not been edited to suppress the diagnostic.

## Retained chart server

The actual registered chart CallTool handler in build/server.js invokes build/utils/callTool.js. That function validates the supplied arguments and returns a vis-chart fenced JSON specification and meta.spec. It does not render a PNG or invoke the remote HTTP generator on this execution path. Although build/utils/generate.js contains remote API helpers, their presence alone does not imply the registered tool calls use them.

All three releases were actually called through stdio using generate_column_chart on two transport-only fixture values. All returned isError false and a real vis-chart specification. HTTP_PROXY HTTPS_PROXY and ALL_PROXY were pointed at an unreachable local endpoint for the chart subprocess, so the declared remote axios helper would not have been available if used. This is additional evidence alongside the inspected call path, not a general operating-system network isolation claim.

All three complete chart list_tools schemas have the same SHA256 c0e3cc263b132716a4811f8c697270c6a26a8c5bef775a017406d2fd01c1c5ab under the saved schema serialization. No mutation metadata targets @umengfe/mcp-server-chart. It is therefore a suitable retained context for task 235. A report must describe generated specifications accurately and must not claim rendered image output unless separately produced.

## Official description overlays

The public tool_level_test.py helper get_all_evolution_status begins at the supplied mutation_path and walks upward while HYBRID remains in the path. It collects deepest metadata first. return_involved_mutated_tool_status then iterates that collection in reverse order so earlier descriptions are applied first and later descriptions overwrite them. It starts from tools obtained from the actual execution endpoint. Parameter and Tool mutations are implemented in those native server releases; the helper's metadata overlay applies only DESC records.

For a DESC record the helper picks the first key other than mutation_type and task_idx as the tool name. It updates record.tool.modified_description when that nested tool field exists and the description of every listed parameter. Three explicit nested-schema exceptions handle PDF sources Salesforce objects and knowledge-graph relations; the exporter preserves their JSON pointer paths. Flat original_description and modified_description records do not match the helper's supported fields and are therefore ignored by the strict exporter. Fourteen such records occur in the full chain and remain documented as ignored rather than silently reinterpreted.

The exported Early overlay is empty. Middle uses the root HYBRID/evolution.json. Late uses all four available files from root to the three nested HYBRID children. These choices match the relevant executable anchors: iter3 @guanxiong get_time_info adds locale includeTimestamp hour12 and iter3 math adds detailed allow_variables; iter5 adds the later tool and parameter changes. The dataset's middle and late labels are retained as provided; a claim that every server underwent exactly three or five successful mutation operations would exceed the available evidence.

overlays/Middle.json contains 41 affected tool descriptors and overlays/Late.json contains 85 descriptors across 56 servers. Only descriptors for actually deployed servers are applied. Every overlay has ordered source file paths and SHA256 values, and all strings come directly from pinned official metadata. No alternative task labels or model outcomes are used.

## Scope boundary

These checks establish deployability and real tool contract behavior. They do not establish TF PE ECS recovery retention or model-level superiority. The formal frozen task experiment is the separate run managed by the primary agent. No downloaded financial order server arbitrary command server or personal-file server was started for this subset.
