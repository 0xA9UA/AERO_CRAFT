# Autonomous Java to Bedrock porting

The objective is executable, source-grounded gameplay on the requested client.
An archive, a large catalog, a clean import, and a server boot are intermediate
results. Keep required scope visible until it works. These instructions apply
to Bedrock targets; use `guide:workflows/java.md` for Java targets.

## Establish durable state

1. Load the bundled `reverse-engineer-anything` skill when requested. Follow its
   evidence workflow and use REA on the supplied artifact. Use `inspect_artifact`
   and `decompile_artifact` for JVM inventory and reconstructed Java sources.
   Decompilation output must be a new directory. Never pipe a build through
   `head` and mistake that pipeline's exit status for the compiler's result.
   For large archives, keep full inventories in files and inspect focused paths.
   If REA reports a completed operation exceeding its transport budget, retain
   the returned Evidence ID and use `get_evidence_bundle(detail: "summary")`
   followed by `export_evidence_bundle` to a new local path. Read relevant fields
   from that file; do not repeat the same oversized operation or infer failure
   of the analysis itself. This occurs with the supplied TechReborn JAR.
2. Call `start_port(source, path, mod_id)`. The tool creates or adopts a project
   without replacing its files. It writes `aero-port.json` with source identity,
   target pins, client platform and required feature categories. MCP assumes a
   current stable Android target; set a different requested platform explicitly
   in the contract. CLI also supports a deliberately pinned target.
3. Call `resolve_bedrock_target(path)` for a latest-version request. This records
   official stable BDS, Mojang samples and Microsoft API metadata with dates and
   hashes. Hotfix server numbers and content format baselines differ. A profile
   mismatch requires a deliberate API/manifest/dependency upgrade and fresh
   verification. Failed network lookup leaves the latest claim unresolved.
   `cache_docs(id)` fetches catalog references without a DeepSeek search key;
   `read_docs(id)` reads them. Search exact signatures with `search_bedrock_api`.
4. Call `discover_runtimes`. It finds registered servers and known suite-local
   copies. An unavailable `bedrock-server` PATH command is not evidence that BDS
   is absent. If needed, register an extracted official Linux/Windows server
   with `python aero.py runtimes register /path/to/server --version VERSION`.
   Original worlds and runtime directories are not modified by verification.

After compaction or restart, read `aero-port.json`, the relevant source evidence,
and `port_status(path)` before continuing. Do not reconstruct progress from
earlier prose completion claims.

## Prove one chain before generating a catalog

Use `create_industrial_example(path, mod_id)` in a separate new directory for a
small working generator → cable → electric furnace reference. It demonstrates
custom blocks, item/terrain atlases, startup registration, touch-friendly forms,
bounded simulation, persistence, tests and a native scenario. It is an example,
not an implementation of the source mod.

First reconstruct one real source-backed chain: obtain fuel and input, generate
energy, transmit it across a cable, consume it once, produce a recipe result,
and recover the same state after save/reload. Test no-energy behavior, full
outputs, conservation, duplicate inputs, removal, unload and restart. Then
expand machines, fluids, tiers, networks, UI and world generation in tested
increments. Do not generate thousands of identifiers before the first chain
works. Source tags can represent ingredient alternatives; flattening them into
simultaneous ingredients changes recipes. Unsupported source behavior requires
an explicit adaptation, not silent omission.

Bedrock content belongs directly under behavior `blocks/`, `items/`, `recipes/`,
`loot_tables/`, `features/` and `feature_rules/`. Java `data/<namespace>/...`
paths do not load. Resource textures require appropriate atlas entries and real
files. Register custom block components through the startup event's
`blockComponentRegistry.registerCustomComponent`; tick callbacks receive an
event containing `block`, and blocks need the applicable tick component. Follow
the exact installed API and native evidence. Never invent a member or use
`@ts-ignore`, `@ts-nocheck`, or an unchecked cast to hide an unsupported API.

## Evidence and repair loop

Run `build_project(path)` early. It independently checks all pack JavaScript
against the pinned declarations, runs actual Node test files, and validates
content. Replacing npm scripts or reducing `tsconfig.json` coverage cannot skip
those checks. Fix the root cause of failures rather than suppressing them.

Run `verify_project(path)` after each playable increment. It records:

- Static content and reference checks.
- Required API typechecking and actual named unit tests.
- Reproducible packaging, bound to artifact and input hashes.
- Actual BDS registration/placement of declared blocks and construction of
  declared items, two separate boots, and content/runtime error logs.
- Project-specific native assertions from `tests/native-smoke.js` when present.

For native scenarios, export `async function run(ctx)`. The runner copies this
file beside the behavior script entry, so `./machine.js` imports refer to that
script directory. Context provides `world`, `system`, `dimension`, `boot` (1 or
2), `assert(condition, name, details?)`, `waitTicks(count)`, `blockIds`, `itemIds`
and `positions` (a map from block identifier to placed coordinates). Assert real
engine transitions and state surviving boot 2. The scenario runs only in the
staged test copy. Do not put test controls into a release pack.

Every required feature row must retain `required: true` and provide:

- `source_evidence`: real JAR members, optionally followed by `#method`.
- `target_implementation`: existing project files implementing that behavior.
- `tests` and/or `native_assertions`: exact names observed passing in this run.
- `status`: implemented, adapted or verified; adaptations need an explanation.

Keep rows unassessed or incomplete while work remains. The nine broad categories
are a minimum: add individual machine/recipe/feature acceptance cases as needed.
Mapping every row to one trivial test cannot establish parity. The unchanged
starter test and empty test files are insufficient. Test conservation and actual
results, not copies of implementation constants.

After updating the contract or any input, rerun verification. `port_status` is
read-only; it does not run tests. `ready: true` means the recorded release checks
passed for the exact current files. `candidate_ready: true` means technical
checks passed and a build may be offered for testing while remaining scope is
explicit. For that case, `present` descriptions must begin `TEST CANDIDATE:`;
state missing features/client checks clearly. This never permits goal completion.

## Client checks and completion

On the requested client, verify import, activation, visible creative entries,
texture/model rendering, actual interactions and restart persistence. In an
existing world, newly generated ores require new chunks. Ensure both packs are
active and the tested pack version/UUID is the intended one. Collect the client
content log and screenshots where available; do not infer a pass from no report.

Record observed evidence in `.aero/client-evidence.json`:

```json
{
  "artifact_sha256": "the verified mcaddon hash",
  "platform": "android",
  "minecraft_version": "the actually observed client version",
  "observed": true,
  "observer": "person or connected-device test identity",
  "passed_checks": ["import", "activation", "visible_content", "textures", "interaction", "restart"],
  "evidence": [".aero/client/screenshots-or-log.txt"]
}
```

Create this receipt only after observing those checks; never synthesize a pass
or substitute a server log for client evidence. A connected licensed client can
be tested through an available device bridge. For Android, select installed
official Platform Tools with `REA_ADB_PATH=/absolute/path/to/adb` before starting
the harness; REA can inspect the client, list devices and capture supported
observations. ADB installation alone does not mean a device is connected or
Minecraft is available. Without a connected client, request the specific
client test after preparing the verified candidate and leave completion pending.
Do not silently disable client or native acceptance requirements.

Run `port_status` again. Only `ready: true` supports presenting a finished port
or completing its goal. DSH checks this before addon presentation/goal completion,
including resumed sessions. These are workflow checks, not a sandbox or a proof
that arbitrary gameplay is equivalent; evidence quality still matters.
