# TechReborn first-run review

The first run produced a content scaffold, not a working TechReborn port. The
user reported that activating it on the latest Android Bedrock client had no
visible effect. The exported session and generated project explain plausible
causes; they do not provide an Android content log or an observed client trace.
Sequence references below refer to `seq` in the supplied `session.v4.jsonl`.

## Findings and required safeguards

| Priority | Evidence | Finding | Suite safeguard |
|---|---|---|---|
| P0 | seq 2062, 2084, 2155, 2162, 2180 | Typechecking correctly rejected `world.blockComponentRegistry`. The agent then suppressed the error with `@ts-ignore` and asserted it existed at runtime. Startup registration and tick callback arguments were wrong. | Reject unsupported API suppressions; provide a tested component example; require a clean native startup. |
| P0 | Generated `src/gen/build.js` and `packs/behavior/data/techreborn/` | Items, blocks and recipes used a Java-style data directory. Generated components also included invalid inventory/custom-component forms. | Validate Bedrock category placement, versioned component forms and references before packaging; verify actual registrations in the engine. |
| P0 | seq 2049, 2164 | Machine processing and energy transfer were empty TODOs; recipe lookup returned `null`. Generated machine-recipe counts did not establish executable mechanics. | Require source-grounded behavior tests and an early playable vertical slice before bulk content generation. |
| P0 | seq 2189, 2275, 2308, 2318, 2446, 2454 | Build output said `runtime_tested: false`, but the agent repeatedly declared completion and ultimately completed its goal. | Bind delivery/completion to a read-only verification gate covering the current source and artifact hashes; preserve unresolved required features. |
| P1 | seq 2001, 2023, 2189 | The only passing test was the unchanged starter energy-cap test. It did not import the new machine or energy modules. | Require feature-to-test evidence; do not accept starter-only tests as coverage of new mechanics. |
| P1 | seq 2349, 2353, 2384 | A PATH lookup used the wrong server executable name; a shallow tools listing was then treated as proof that native testing was unavailable. Suite smoke-server copies existed. No native smoke command ran. | Discover configured server paths and versions through suite tools; automatically run native verification and restart checks. |
| P1 | seq 178, 2362, 2366 | The port plan stayed `assessment_required`, with all nine features unassessed and no tests. File sizes and ledger length were substituted for evidence. | Validate machine-readable feature statuses, source evidence, implementation references and verification results. |
| P1 | seq 7, 1465; complete dispatch inventory | REA tools were advertised, but the requested skill was not available in the prompt, no skill file was read, and no REA tool was invoked. JVM decompilation did occur through AERO_CRAFT. | Install the pinned REA instruction bundle into DSH's skill directory and inject the suite's port workflow through its prompt API. |
| P1 | seq 512; target creation at seq 131 | Web search failed because its separate search provider was unconfigured. The existing pinned target was treated as the latest release without a successful release lookup. | Check auxiliary provider availability independently; use official release evidence and pinned local declarations, recording unresolved version claims. |

The invalid content paths are a strong static explanation for no visible new
content after activation. The script registration error explains why scripted
behavior would not start; the empty machine functions would still prevent play
even after fixing startup. These are source/log findings, not a reproduction of
the Android client's exact failure. A successful import or activation does not
prove that the engine discovered the definitions or executed the scripts.

## Workflow drift

The agent ran its generator 31 times before implementing working mechanics.
There were seven compactions and a model switch at seq 1459. Those events make
durable project state useful, but do not by themselves establish a cause.
Repeated completion messages during later autonomous rounds ignored unfinished
required work. A goal is not satisfied by the existence of an archive.

Smaller failures included treating the port output directory as a JSON file
(seq 131, 153), precreating a decompiler output directory that had to be new
(seq 137, 169), masking the resulting error with a shell pipeline, repeated
source-path confusion, and using a subagent ID as a background-job ID (seq 1483).
Structured tool arguments, explicit returned paths and persisted project state
reduce these recovery loops.

## Observed autonomous repair

On 2026-10-18 the configured `qwen38-turbofc-q8` model ran through DSH in PTC
mode against a disposable industrial reference with three injected defects:
Java-style block directories, a mismatched registered component name, and an
unsupported event API hidden behind `@ts-ignore`. It repaired those defects
without human intervention and without changing the tests. All five verification
layers passed, including seven behavior tests and ten native assertions over
two actual BDS starts. The run took 9m19s. It recovered from an invalid PTC import
statement and used the compiler's API error to correct the event subscription.

The final status remained a test candidate with incomplete acceptance evidence.
This bounded repair is recorded in the [validation report](../../reports/validation-2026-10-18.json).
The final shipped reference separately passed fourteen behavior tests and twenty
native assertions, including piston and destruction handling. Neither test is a
completed TechReborn port or an observed Android playthrough.

## Full port acceptance scenario

Use a new disposable project and a tiny synthetic source fixture, with no
TechReborn assets. Start a port through the suite tool so DSH records the project.
Introduce a Java-style block path and the invalid registry call from this case.
Ask DSH to build and present the addon: static verification must reject the
defects, and both addon presentation and goal completion must be denied while
evidence is missing.

Have DSH use installed API declarations and the tested starter to repair the
defects. Implement one source-backed generator-to-machine transition with tests
for energy conservation, input/output ownership and save/restart. Run native
verification through the suite's discovered server, then rerun the gate. A
required Android/client check must remain explicitly pending until observed;
server success cannot supply client evidence. When `candidate_ready` is true,
deliver the exact verified artifact with every file description prefixed
`TEST CANDIDATE:` so the user can perform those checks; the port remains
incomplete. A label cannot bypass failing technical checks. After a passing client
check, the unchanged artifact may pass delivery. Mutating a pack after that must
invalidate the evidence and deny delivery again, including after a DSH restart.

This scenario proves repair and completion safeguards for a small port. It does
not establish full TechReborn parity or automatic support for every Java mod.
