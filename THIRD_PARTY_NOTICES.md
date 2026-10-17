# Third-party software and source references

AERO_CRAFT's own code is MIT licensed. Third-party software is downloaded at install/build time and retains its own licenses and notices. This repository's license does not relicense downloaded dependencies or imply permission to redistribute someone else's mod/assets.

| Component | Upstream | License / notice |
|---|---|---|
| DeepSeek Harness 0.2.1-rc.2 | https://github.com/deepseek-ai/deepseek-harness | MIT; upstream THIRD_PARTY_NOTICES also applies |
| REA 6.5.0 | https://github.com/morluto/rea | MIT and dependencies' notices |
| Node.js 24.22.0 | https://nodejs.org/ | MIT and bundled third-party licenses |
| Eclipse Temurin JDKs | https://adoptium.net/ | GPL v2 with Classpath Exception and included notices |
| Gradle | https://gradle.org/ | Apache 2.0 and distribution notices |
| CFR 0.152 | https://www.benf.org/other/cfr/ | MIT |
| Vineflower 1.12.0 | https://github.com/Vineflower/vineflower | Apache 2.0 |
| Ghidra (optional) | https://github.com/NationalSecurityAgency/ghidra | Apache 2.0 and bundled notices |
| Fabric Loader/API/Loom | https://github.com/FabricMC | Component-specific upstream licenses, commonly Apache 2.0 |
| NeoForge/ModDevGradle | https://github.com/neoforged | Component-specific upstream licenses |
| Forge/ForgeGradle | https://github.com/MinecraftForge | Component-specific upstream licenses |
| Minecraft Script API declarations | https://www.npmjs.com/package/@minecraft/server | MIT in the installed declaration packages; game/API service terms remain separate |
| TypeScript | https://github.com/microsoft/TypeScript | Apache 2.0 and package notices |
| Minecraft game/server/mappings | https://www.minecraft.net/ | Minecraft EULA and mapping terms; not included in this repository |

The npm lock records the exact dependency graph and integrity hashes. Installed packages carry their license files. Managed tool archives preserve upstream license files through extraction. CFR/Vineflower JARs retain packaged notices. No IC2 binary, texture, sound or decompiled source is redistributed. Offline workflow documents and API navigation summaries are original suite documentation; cached upstream pages remain local and are excluded from Git.
