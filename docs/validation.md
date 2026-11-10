# Validation record

## 2026-11-10 — REA 6.8.0 upgrade

Validated from a clean Linux x64 installation with Node 24.22.1, REA 6.8.0 and
DeepSeek Harness 0.2.1-rc.2. The [recorded results](../reports/validation-2026-11-10.json)
include artifact hashes and the verification scope.

| Check | Result | Boundary |
|---|---|---|
| Python regression suite | 115 passed, zero skipped | Includes runtime upgrades, old and edited skill copies, rollback, concurrent refresh rejection and existing port checks |
| Existing installation migration | Real Node 24.22.0 upgraded to 24.22.1; real REA 6.5.0 instructions refreshed to the eight files shipped by 6.8.0 | Previous runtime and instructions retained; repeated refresh is idempotent |
| AERO_CRAFT / REA MCP | 19 / 229 tools; versions and tool calls passed | Installed DSH SDK negotiation; both servers inspected the generated Fabric JAR |
| DeepSeek Harness | Configuration composition and authenticated HTTP 200 passed | Local startup and session cookie; zero model calls |
| Java profiles | Fabric 1.21.1, Fabric 26.1, NeoForge 1.21.1 and Forge 1.20.1 built | Fresh compiled JARs; Java game startup remains unverified |
| Bedrock builds | Starter and industrial reference passed API, unit and packaging checks | Industrial reference executed 14 behavior tests |
| Native Bedrock | Official BDS 1.26.63.1 passed all five verification layers, 20 native assertions and two boots | Original industrial example; client visuals and touch interaction remain unverified |
| Port workflow | Both assessment directions, recipe conversion, CFR and Vineflower passed | Adding a contract invalidated prior verification; successful re-verification allowed a test candidate while required feature and client evidence kept release readiness false |

This run covers Linux x64. The five Node download pins match the publisher's
checksum manifest. Windows, macOS, ARM execution and connected Minecraft clients
require their own validation runs. Full native logs and generated projects are
retained locally under ignored `reports/local/rea-6.8.0`, `.runtime` and `projects`.

## 2026-10-18: autonomous Bedrock port safeguards

Validated on Linux x64 after reviewing the first TechReborn run. The sanitized
[machine-readable report](../reports/validation-2026-10-18.json) records the checks
and their limits; the [session review](reviews/techreborn-first-run.md) connects
the failures to the safeguards.

| Check | Result | Boundary |
|---|---|---|
| Python regression suite | 105 passed | Content validation, current-input receipts, completion policy, runtime discovery, recipe conversion and reference behavior |
| AERO_CRAFT / REA MCP | 19 / 207 tools; integration passed | Actual installed SDK and configured bridges |
| Official target resolution | BDS 1.26.52.3; samples 1.26.50.4; API 2.10.0 / UI 2.2.0 | Retrieved official release metadata; pinned profile matched on this date |
| Original TechReborn output | Rejected by content validation | Ignored Java-style directories, invalid API/components, missing texture references and invalid recipes; original files preserved |
| Industrial reference | API checks, 14 behavior tests, deterministic packaging and 20 native assertions passed | Generator → cable → furnace, persistence, piston immovability and destruction inventory ownership; original example, not a TechReborn port |
| Native content inventory | 151 blocks and 151 items checked across two boots | Registration, block placement and item construction; client appearance unobserved |
| Autonomous repair | Configured `qwen38-turbofc-q8`, PTC, 9m19s; all five verification layers passed | Model repaired three injected defects without human repairs or changing tests; 7 unit tests and 10 native assertions passed in that earlier reference fixture |
| Completion gate | Candidate allowed; finished-port status remained false | Required feature and client evidence could not be replaced by successful packaging or server tests |

The autonomous benchmark recovered from ignored content directories, a mismatched
component registration, an invalid event API hidden by a typecheck suppression,
and a PTC import error. It proves repair of a bounded working example. It does
not establish complete TechReborn parity or that an arbitrary full port will
finish without intervention. No Android device was connected, so rendering and
touch interactions remain unobserved. The workflow deliberately preserves that
missing acceptance evidence.

Run `python aero.py industrial-example projects/reference`, then
`python aero.py verify projects/reference` with a registered official Bedrock
server to repeat the reference checks. For a new port, follow the
[autonomous workflow](workflows/autonomous-porting.md), which records source
evidence and acceptance requirements before implementation.

## 2026-10-17: original suite

Local validation on **2026-10-17**, Debian 13 Linux x64, Python 3.13.5. Machine-readable details and generated artifact hashes: [reports/validation-2026-10-17.json](../reports/validation-2026-10-17.json).

| Check | Result | Boundary |
|---|---|---|
| Python unit/contract suite | 37 passed | Archive traversal/links/collisions, checksums, output preservation, inventories, manifests, recipes, plans, workspace confinement and protocol errors |
| Fresh clone from GitHub | Install and Bedrock build passed | Independent checkout with fresh managed Node and npm packages |
| JDK 8 | Installed, compiled class and JAR inspection passed | Legacy runtime toolchain smoke |
| Standard installation | Passed | Managed Node 24.22.0, JDK 21/25, pinned npm graph, CFR/Vineflower; JDK 17 installed during Forge build |
| Fabric 1.21.1 | Gradle build passed | Compiled and remapped JAR; game startup not tested |
| Fabric 26.1 | Gradle build passed on JDK 25 | Compiled Java 25 JAR; game startup not tested |
| NeoForge 1.21.1 | Gradle build passed | Sources prepared and JAR built; game startup not tested |
| Forge 1.20.1 | Gradle build passed on JDK 17 | Reobfuscated JAR built; game startup not tested |
| Bedrock starter | Typecheck, simulation test, validation, package passed | Stable API 2.10.0; repeated packaging produces the same SHA-256 for the same project |
| Official BDS 1.26.52.3 | Native smoke and actual restart passed | Script boot counts 1 → 2, no content/runtime errors; generic persistence fixture only |
| CFR 0.152 / Vineflower 1.12.0 | Decompiled generated Fabric JAR | Output inspected; not a claim that all obfuscated or malformed mods decompile |
| AERO_CRAFT MCP | Negotiated and discovered 10 tools; calls/resources passed | Actual installed DSH SDK, including legacy fallback |
| REA MCP 6.5.0 | Negotiated, discovered 207 tools, session call passed | Provider/host availability still governs individual tools |
| Ghidra 12.1.4 | Pinned installation and scoped REA provider readiness passed | Native target analysis not exercised |
| DeepSeek Harness | Config composition and authenticated HTTP 200 passed | Web UI startup; no live model call or API spending |
| Port assessments | Java → Bedrock and Bedrock → NeoForge passed | Source identities/feature ledgers; no automatic behavioral reconstruction claim |

The first generic Bedrock test exposed omitted module permissions and a transport default. The runner now explicitly configures allowed script modules, NetherNet transport and loopback binding in its staged server. The corrected two-process test passed; it does not modify the original server or distributable pack.

[GitHub Actions](https://github.com/0xA9UA/AERO_CRAFT/actions) is the source of truth for the current commit's Windows/macOS/Linux jobs. The suite does not infer another OS was tested from a Linux pass. ARM distribution entries are pinned but local ARM execution was not performed. Optional native providers and Minecraft clients have their own platform requirements.

To repeat: run the tests, create fresh projects from the five profiles, run `build` for each, run `scripts/check_mcp.mjs` with the managed Node, and supply an official BDS runtime to `smoke`. Keep a new output directory for each native test. Model configuration is only needed when asking the harness to perform an agent task.
