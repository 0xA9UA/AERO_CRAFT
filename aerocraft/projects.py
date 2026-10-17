"""Versioned Java/Bedrock starters and builds using pinned local toolchains."""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
from .common import ROOT, RUNTIME, CraftError, atomic_write, read_json, run, write_json
from . import toolchains


def profiles():
    return read_json(ROOT / "catalog/profiles.json")


def create(path, profile, mod_id, name=None, package="dev.aerocraft"):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
        raise CraftError("Mod ID must match [a-z][a-z0-9_]{1,63}.")
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", package):
        raise CraftError("Use a lowercase Java package such as dev.example.")
    path = Path(path).resolve()
    if path.exists():
        raise CraftError("New project destination must not exist.")
    if profile not in profiles():
        raise CraftError(f"Unknown profile {profile}. Run profiles.")
    config = {
        **profiles()[profile],
        "schema_version": 1,
        "profile": profile,
        "id": mod_id,
        "name": name or mod_id.replace("_", " ").title(),
        "package": package + "." + mod_id,
        "version": "0.1.0",
    }
    path.mkdir(parents=True)
    write_json(path / "aero-project.json", config)
    atomic_write(
        path / ".gitignore",
        "build/\ndist/\n.gradle/\nnode_modules/\nrun/\nruns/\n.env\n",
    )
    atomic_write(
        path / "AGENTS.md",
        "# Minecraft project\n\nRead aero-project.json for exact engine, loader, API and JDK versions. Keep simulation logic independent from engine adapters. Consult the AERO_CRAFT MCP docs tools and workflow resources. Implement focused regression tests for behavior changes. Preserve world save formats and Bedrock header UUIDs. Track evidence and adaptations in PARITY.md. A compiled package is not proof of in-game parity.\n",
    )
    atomic_write(
        path / "PARITY.md",
        "# Feature and validation ledger\n\nRecord source evidence, implementation, tests, adaptations and unknowns per feature.\n\n| Layer | Status |\n|---|---|\n| Unit | Not run |\n| Build | Not run |\n| Server | Not run |\n| Restart | Not run |\n| Connected client | Not run |\n",
    )
    if config["loader"] == "bedrock":
        _bedrock(path, config)
    else:
        _java(path, config)
    return {"project": str(path), "profile": profile, "config": config}


def _bedrock(path, c):
    bp, rp = path / "packs/behavior", path / "packs/resource"
    bu, ru = str(uuid.uuid4()), str(uuid.uuid4())

    def header(n, u):
        return {
            "name": n,
            "description": "Created with AERO_CRAFT",
            "uuid": u,
            "version": [0, 1, 0],
            "min_engine_version": c["engine_version"],
        }

    write_json(
        bp / "manifest.json",
        {
            "format_version": 2,
            "header": header(c["name"], bu),
            "modules": [
                {"type": "data", "uuid": str(uuid.uuid4()), "version": [0, 1, 0]},
                {
                    "type": "script",
                    "language": "javascript",
                    "entry": "scripts/main.js",
                    "uuid": str(uuid.uuid4()),
                    "version": [0, 1, 0],
                },
            ],
            "dependencies": [
                {"uuid": ru, "version": [0, 1, 0]},
                {"module_name": "@minecraft/server", "version": c["server_api"]},
            ],
        },
    )
    write_json(
        rp / "manifest.json",
        {
            "format_version": 2,
            "header": header(c["name"] + " Resources", ru),
            "modules": [
                {"type": "resources", "uuid": str(uuid.uuid4()), "version": [0, 1, 0]}
            ],
        },
    )
    # JS is both directly runnable in Bedrock and checked against installed .d.ts files.
    atomic_write(
        bp / "scripts/main.js",
        "import { system, world } from '@minecraft/server';\nimport { advance } from './simulation.js';\n\nworld.afterEvents.worldLoad.subscribe(() => {\n  const previous = world.getDynamicProperty('"
        + c["id"]
        + ":boots');\n  const boots = typeof previous === 'number' ? previous + 1 : 1;\n  world.setDynamicProperty('"
        + c["id"]
        + ":boots', boots);\n  console.warn('[AERO_CRAFT_READY] ' + JSON.stringify({ boots }));\n});\n\n// Pure state transitions can be tested independently of the world adapter.\nlet state = { energy: 0 };\nsystem.runInterval(() => { state = advance(state, 1, 100); }, 20);\n",
    )
    atomic_write(
        bp / "scripts/simulation.js",
        '/** @param {{energy:number}} state @param {number} input @param {number} capacity */\nexport function advance(state, input, capacity) {\n  if (!Number.isFinite(input) || input < 0 || !Number.isFinite(capacity) || capacity < 0) throw new RangeError("Invalid energy input");\n  return { ...state, energy: Math.min(capacity, state.energy + input) };\n}\n',
    )
    atomic_write(
        path / "tests/simulation.test.mjs",
        "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { advance } from '../packs/behavior/scripts/simulation.js';\ntest('energy caps without mutating the saved state', () => {\n  const old = {energy: 9};\n  assert.deepEqual(advance(old, 4, 10), {energy: 10});\n  assert.equal(old.energy, 9);\n  assert.throws(() => advance(old, -1, 10), RangeError);\n});\n",
    )
    write_json(
        path / "package.json",
        {
            "name": c["id"],
            "version": c["version"],
            "private": True,
            "type": "module",
            "scripts": {
                "test": "node --test tests/*.test.mjs",
                "typecheck": "tsc --noEmit",
            },
            "devDependencies": {
                "@minecraft/server": c["server_api"],
                "@minecraft/server-ui": c["server_ui_api"],
                "typescript": c["typescript"],
            },
        },
    )
    write_json(
        path / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "strict": True,
                "allowJs": True,
                "checkJs": True,
                "noEmit": True,
                "skipLibCheck": True,
            },
            "include": ["packs/behavior/scripts/**/*.js"],
        },
    )
    # A reproducible project can install the subset from the suite lock, avoiding new resolution.
    lock = read_json(ROOT / "package-lock.json")
    selected = {
        "": {
            "name": c["id"],
            "version": c["version"],
            "devDependencies": read_json(path / "package.json")["devDependencies"],
        }
    }
    for k, v in lock["packages"].items():
        if k.startswith(
            (
                "node_modules/@minecraft/",
                "node_modules/typescript",
                "node_modules/@typescript/",
            )
        ):
            selected[k] = v
    write_json(
        path / "package-lock.json",
        {
            "name": c["id"],
            "version": c["version"],
            "lockfileVersion": 3,
            "requires": True,
            "packages": selected,
        },
    )
    atomic_write(
        path / "README.md",
        "# "
        + c["name"]
        + "\n\nFrom the AERO_CRAFT checkout, run `python aero.py build /absolute/path/to/this/project`. Import the resulting `dist/*.mcaddon` with Minecraft and enable both packs. The starter logs `[AERO_CRAFT_READY]` and counts world boots for restart checks.\n",
    )


def _java(path, c):
    loader = c["loader"]
    jdk = c["jdk"]
    pkg = c["package"]
    mid = c["id"]
    mc = c["minecraft"]
    repos = (
        "pluginManagement { repositories { maven { url = 'https://maven.fabricmc.net/' }; maven { url = 'https://maven.neoforged.net/releases' }; maven { url = 'https://maven.minecraftforge.net/' }; gradlePluginPortal() } }\nrootProject.name = '"
        + mid
        + "'\n"
    )
    atomic_write(path / "settings.gradle", repos)
    common = f"\nversion = '{c['version']}'\ngroup = '{pkg}'\nbase {{ archivesName = '{mid}' }}\njava {{ toolchain.languageVersion = JavaLanguageVersion.of({jdk}); withSourcesJar() }}\ntasks.withType(JavaCompile).configureEach {{ options.encoding = 'UTF-8'; options.release = {jdk} }}\n"
    if loader == "fabric":
        plugin = "net.fabricmc.fabric-loom" if mc.startswith("26.") else "fabric-loom"
        script = (
            f"plugins {{ id '{plugin}' version '{c['loom']}'; id 'maven-publish' }}\n"
            + common
            + f"\ndependencies {{\n  minecraft 'com.mojang:minecraft:{mc}'\n"
            + (
                ""
                if mc.startswith("26.")
                else "  mappings loom.officialMojangMappings()\n"
            )
            + f"  modImplementation 'net.fabricmc:fabric-loader:{c['loader_version']}'\n  modImplementation 'net.fabricmc.fabric-api:fabric-api:{c['fabric_api']}'\n}}\n"
        )
        code = f'package {pkg};\n\nimport net.fabricmc.api.ModInitializer;\n\npublic final class Main implements ModInitializer {{\n  @Override public void onInitialize() {{\n    System.out.println("{mid} initialized");\n  }}\n}}\n'
        write_json(
            path / "src/main/resources/fabric.mod.json",
            {
                "schemaVersion": 1,
                "id": mid,
                "version": c["version"],
                "name": c["name"],
                "environment": "*",
                "entrypoints": {"main": [pkg + ".Main"]},
                "depends": {
                    "fabricloader": ">=" + c["loader_version"],
                    "minecraft": "~" + mc,
                    "java": ">=" + str(jdk),
                    "fabric-api": "*",
                },
            },
        )
    elif loader == "neoforge":
        script = (
            f"plugins {{ id 'java-library'; id 'net.neoforged.moddev' version '{c['moddev']}' }}\n"
            + common
            + f"\nneoForge {{\n  version = '{c['loader_version']}'\n  runs {{ client {{ client() }}; server {{ server(); programArgument '--nogui' }} }}\n  mods {{ {mid} {{ sourceSet(sourceSets.main) }} }}\n}}\n"
        )
        code = f'package {pkg};\n\nimport net.neoforged.fml.common.Mod;\n\n@Mod("{mid}")\npublic final class Main {{\n  public Main() {{ System.out.println("{mid} initialized"); }}\n}}\n'
        _mod_toml(path, c, "neoforge.mods.toml", "neoforge")
    else:
        script = (
            f"plugins {{ id 'java'; id 'net.minecraftforge.gradle' version '{c['forgegradle']}' }}\n"
            + common
            + f"\nminecraft {{\n  mappings channel: 'official', version: '{mc}'\n  runs {{\n    client {{ workingDirectory project.file('run'); mods {{ {mid} {{ source sourceSets.main }} }} }}\n    server {{ workingDirectory project.file('run'); args '--nogui'; mods {{ {mid} {{ source sourceSets.main }} }} }}\n  }}\n}}\ndependencies {{ minecraft 'net.minecraftforge:forge:{mc}-{c['loader_version']}' }}\njar.finalizedBy('reobfJar')\n"
        )
        code = f'package {pkg};\n\nimport net.minecraftforge.fml.common.Mod;\n\n@Mod("{mid}")\npublic final class Main {{\n  public Main() {{ System.out.println("{mid} initialized"); }}\n}}\n'
        _mod_toml(path, c, "mods.toml", "forge")
    if loader == "fabric" and mc.startswith("26."):
        script = script.replace("modImplementation ", "implementation ")
    atomic_write(path / "build.gradle", script)
    atomic_write(
        path / "gradle.properties",
        "org.gradle.jvmargs=-Xmx2G\norg.gradle.daemon=false\n",
    )
    atomic_write(path / ("src/main/java/" + pkg.replace(".", "/") + "/Main.java"), code)
    atomic_write(
        path / "README.md",
        "# "
        + c["name"]
        + f"\n\n{loader} {mc}, JDK {jdk}. Build with `python /path/to/AERO_CRAFT/aero.py build .`. Use `gradle . -- wrapper` to generate a conventional wrapper, or `gradle . -- runClient` to launch the development client. Minecraft assets and libraries are fetched by the loader build plugin on first build.\n",
    )


def _mod_toml(path, c, filename, loader):
    mid = c["id"]
    loadermajor = "[1,)" if loader == "neoforge" else "[47,)"
    txt = (
        f'modLoader="javafml"\nloaderVersion="{loadermajor}"\nlicense="All Rights Reserved"\n\n[[mods]]\nmodId="{mid}"\nversion="{c["version"]}"\ndisplayName={json.dumps(c["name"])}\ndescription="Created with AERO_CRAFT"\n\n[[dependencies.{mid}]]\nmodId="{loader}"\n'
        + ('type="required"\n' if loader == "neoforge" else "mandatory=true\n")
        + f'versionRange="[{c["loader_version"]},)"\nordering="NONE"\nside="BOTH"\n\n[[dependencies.{mid}]]\nmodId="minecraft"\n'
        + ('type="required"\n' if loader == "neoforge" else "mandatory=true\n")
        + f'versionRange="[{c["minecraft"]}]"\nordering="NONE"\nside="BOTH"\n'
    )
    atomic_write(path / "src/main/resources/META-INF" / filename, txt)


def gradle(path, args):
    path = Path(path).resolve()
    config = read_json(path / "aero-project.json")
    if config["loader"] == "bedrock":
        raise CraftError("Bedrock projects use build or npm, not Gradle.")
    toolchains.java(config["jdk"], ensure=True)
    base = toolchains.install("gradle" + config["gradle"])
    # Invoke Gradle's Java entry directly; no cmd.exe quoting ambiguity on Windows.
    jars = list((base / "lib").glob("gradle-gradle-cli-main-*.jar")) or list(
        (base / "lib").glob("gradle-launcher-*.jar")
    )
    if len(jars) != 1:
        raise CraftError("Cannot identify the Gradle launcher JAR.")
    cls = "org.gradle.launcher.GradleMain"
    return run(
        [
            toolchains.java(config["jdk"]),
            "-classpath",
            jars[0],
            cls,
            "--no-daemon",
            *args,
        ],
        cwd=path,
        env=toolchains.environment(config["jdk"]),
    )


def build(path):
    path = Path(path).resolve()
    c = read_json(path / "aero-project.json")
    if c["loader"] == "bedrock":
        toolchains.npm(["ci", "--no-audit", "--no-fund"], path)
        toolchains.npm(["run", "typecheck"], path)
        toolchains.npm(["test"], path)
        from .bedrock import package

        return package(path)
    gradle(path, ["build"])
    artifacts = sorted(str(p) for p in (path / "build/libs").glob("*.jar"))
    if not artifacts:
        raise CraftError("Gradle finished without producing a JAR.")
    return {"artifacts": artifacts, "runtime_tested": False}
