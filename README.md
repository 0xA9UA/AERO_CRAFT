# AERO_CRAFT

A clone-installable Minecraft development suite built around **DeepSeek Harness 0.2.1-rc.2**, **REA 6.5.0**, managed Java toolchains and practical mod/addon workflows.

Create Java mods and Bedrock addons, inspect and decompile existing mods, plan Minecraft/Java/loader upgrades, and develop ports in either direction. The suite supplies an agent workspace, tools, starters, API references and validation. Cross-engine gameplay still requires implementation and native testing; it is not a universal one-click converter.

## Install and launch

Prerequisites: **Git, Python 3.11.8+ (3.12+ recommended), an internet connection and several GB of free disk space**. Python needs working HTTPS certificates. No system Node, Java, Gradle, administrator account or Python package installation is required.

```sh
git clone https://github.com/0xA9UA/AERO_CRAFT.git
cd AERO_CRAFT
python3 aero.py setup
python3 aero.py doctor
python3 aero.py new projects/my_addon --profile bedrock-stable --id my_addon
python3 aero.py harness --workspace projects/my_addon
```

On Windows use `py -3` in place of `python3`, or run `./install.ps1`. On Linux/macOS `./install.sh` is also available. The optional `./aero` launcher preserves the current working directory.

The harness prints a local authenticated browser URL. Open it, configure your own provider in **Settings → Models**, select the project workspace, and start a session. Model credentials are not bundled. DeepSeek and the other endpoints supported by that release can be configured in its UI. The suite does not need a model key for builds, inspections, decompilation, packaging or tests.

Standard setup installs Node 24.22.0, the pinned harness/REA/npm dependencies, JDKs 21 and 25, CFR and Vineflower. Full setup adds JDKs 8 and 17; Java builds also fetch their missing JDK and Gradle automatically:

```sh
python3 aero.py setup --profile full
python3 aero.py tools install ghidra    # optional native reverse engineering
```

`--profile minimal` installs Node and npm tools only. Downloads are SHA-256 pinned in `catalog/toolchains.lock.json`; npm transitive versions and integrity hashes are in `package-lock.json`. Runtimes, caches, model credentials and sessions live under ignored `.runtime/`. Set `AERO_CRAFT_HOME` to an absolute directory to relocate them. No system Java selection, shell profile or existing DSH configuration is changed. Re-running setup is supported. See [installation details](docs/installation.md).

## What is included

| Area | Tools and workflow |
|---|---|
| Agent harness | Requested DSH release; Web UI; isolated config; AERO_CRAFT and REA MCP bridges |
| Java | Temurin JDK 8/17/21/25, including JVM runtimes and `javac`, `javap`, `jar`, `jcmd`; pinned Gradle |
| Mod loaders | Buildable Fabric, NeoForge and Forge starters; existing-project inspection and upgrade assessment |
| Bedrock | Mandatory API checks, content/reference validation, industrial reference example, unit/native gameplay scenarios and deterministic `.mcaddon` packaging |
| Reverse engineering | REA CLI/MCP, CFR, Vineflower, member hashes, class-version inspection, archive diffs and safe extraction; optional Ghidra |
| Ports | Source inventories, feature/parity ledgers, Java ↔ Bedrock workflows and conservative crafting-recipe conversion |
| Documentation | Searchable primary-source index, offline workflow/API guides, installed declaration search and optional local page cache |
| Validation | Unit tests, actual starter builds, MCP integration checks, server-load and restart test runner, CI for Windows/macOS/Linux |

## Common commands

Create and build a Java mod:

```sh
python3 aero.py new projects/my_mod --profile fabric-1.21.1 --id my_mod
python3 aero.py build projects/my_mod
python3 aero.py gradle projects/my_mod -- runClient
```

Other profiles: `fabric-26.1` (JDK 25), `neoforge-1.21.1` (JDK 21), `forge-1.20.1` (JDK 17), and `bedrock-stable`. These are maintained baselines, not an assertion that each is the newest Minecraft release. Use `profiles` for exact versions. Use a project's existing compatible Gradle wrapper when maintaining an older Forge build.

Inspect, decompile and plan a port or upgrade:

```sh
python3 aero.py inspect /path/to/mod.jar --members --output reports/mod-inventory.json
python3 aero.py decompile /path/to/mod.jar --engine vineflower --output .runtime/mod-source
python3 aero.py port /path/to/mod.jar --to bedrock --output projects/port-assessment
python3 aero.py port /path/to/addon.mcaddon --to neoforge --minecraft 1.21.1 --output projects/java-assessment
python3 aero.py compare /path/to/old.jar /path/to/new.jar
python3 aero.py rea -- --help
```

Build and validate Bedrock:

```sh
python3 aero.py build projects/my_addon
python3 aero.py validate projects/my_addon
python3 aero.py smoke projects/my_addon --server /path/to/official/bedrock-server --output .runtime/native-check
```

The native runner stages a private copy, verifies declared blocks/items in the real engine, runs project-specific assertions, and checks persistence through an actual stop/start. Minecraft/BDS runtimes are not redistributed. A headless pass does not verify Android visuals or touch interaction.

Start a tracked Java-to-Bedrock port and verify it:

```sh
python3 aero.py start-port /path/to/mod.jar --project projects/my_port --id my_port --latest
python3 aero.py resolve-target projects/my_port
python3 aero.py runtimes list
# Register a separately obtained official runtime if discovery found none:
python3 aero.py runtimes register /path/to/bedrock-server --version 1.26.52.3
python3 aero.py verify projects/my_port
python3 aero.py port-status projects/my_port
```

The contract in `aero-port.json` tracks required features and source/test evidence. `verify` reports executed technical checks; `port-status` reports release readiness, including required client evidence. The current stable runtime may differ from the example version above; use `resolve-target`. See [the autonomous port workflow](docs/workflows/autonomous-porting.md) and [the TechReborn first-run review](docs/reviews/techreborn-first-run.md).

For a small original working reference:

```sh
python3 aero.py industrial-example projects/industrial_reference --id industrial_reference
python3 aero.py verify projects/industrial_reference
```

This example supplies a coal generator, cable network, electric furnace, textures, forms, mechanics tests and a native restart scenario. It is not a Tech Reborn port. Restart the harness after updating the suite so new tools, instructions and policy load; existing provider settings and sessions are preserved.

Search APIs and translate supported recipes:

```sh
python3 aero.py docs search "inventory persistence"
python3 aero.py docs api setDynamicProperty
python3 aero.py docs read guide:workflows/porting.md
python3 aero.py recipe examples/java-recipe.json --direction java-to-bedrock --id example:wire --mapping examples/item-map.json --output .runtime/wire.json
```

Recipe conversion supports plain shaped/shapeless crafting, with explicit always-unlocked Bedrock recipe-book metadata. Source advancement/unlock progression needs separate reconstruction. Unsupported tags, metadata, components, custom conditions or recipe types fail with a reason. Read [the porting workflow](docs/workflows/porting.md) before treating converted data as equivalent behavior.

## Use with agents

The harness registers AERO_CRAFT tools plus the pinned REA server and its instruction bundle. Agents can start tracked ports, resolve current stable targets, fetch official documentation without a model-specific search key, inspect/decompile artifacts, create an industrial reference, build, discover BDS and verify gameplay. Durable acceptance state survives compaction. A DSH plugin checks current verification before completing port goals or presenting addons; clearly labelled test candidates remain available for client testing. Existing DSH permission controls remain active. These workflow checks are not a security boundary or a guarantee of full mod equivalence.

Example task:

> Inspect this legacy Java mod, create a Bedrock target, and reconstruct its machines one subsystem at a time. Follow the AERO_CRAFT porting guide. Record source hashes, adaptations and missing behavior; test pure mechanics and native persistence before packaging.

The standalone server works with other MCP clients as well:

```json
{
  "mcpServers": {
    "aerocraft": {
      "command": "/absolute/path/to/python3",
      "args": ["/absolute/path/to/AERO_CRAFT/aero.py", "mcp", "--workspace", "/absolute/path/to/project"]
    }
  }
}
```

AERO_CRAFT MCP paths are confined to that workspace; the CLI accepts explicit paths elsewhere. The complete DSH/REA agent environment is not a security sandbox. DSH is an upstream developer preview; its [release and safety notes](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.2.1-rc.2) apply.

## Verification and maintenance

```sh
python3 -m unittest discover -s tests -v
# After setup, run the SDK integration check with the managed Node:
.runtime/tools/node/bin/node scripts/check_mcp.mjs  # Windows: .runtime/tools/node/node.exe
```

See [validation evidence and limits](docs/validation.md), [architecture](docs/architecture.md), [Java upgrades](docs/workflows/java.md), and [Bedrock workflow](docs/workflows/bedrock.md). Cross-platform CI repeats unit, installation, Bedrock build and MCP checks; a manual workflow performs all Java builds. Run the maintainer-only `scripts/resolve_catalog.py` to deliberately refresh tool URLs/hashes, then review the diff and validate before committing. Installs never silently resolve `latest`.

MIT applies to AERO_CRAFT's own code. Third-party tool licenses remain separate; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No Minecraft game binaries, original mod JARs, copied IC2 assets, decompiled mod sources, private chat contents or API keys are included. This is an unofficial project, not approved by Mojang or Microsoft.
