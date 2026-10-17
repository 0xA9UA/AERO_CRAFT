# Validation record

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
