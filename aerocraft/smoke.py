"""Native, isolated Bedrock pack loading, content checks and restart scenarios."""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid

from .bedrock import validate
from .common import CraftError, read_json, sha256, write_json
from .runtimes import resolve_bedrock

ERROR_PATTERN = re.compile(r"\bERROR\]|\[[^\]\n]*error\]|(?:Syntax|Reference|Type|Range)Error:|unhandled\s+(?:exception|promise|rejection)|watchdog.*(?:hang|terminated)", re.I)
BUILTIN_PACK = re.compile(r"(?:vanilla(?:_[\d.]+|_base)?|chemistry(?:_[\d.]+)?|editor|experimental_[a-z_]+|server(?:_ui|_editor)?_library)\Z")


def _content_logs(stage):
    return {
        p.relative_to(stage).as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(stage.rglob("*"))
        if p.name.lower().startswith("contentlog") and p.is_file()
    }


def _errors(text):
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if ERROR_PATTERN.search(line)))


def _copy_runtime(server, stage):
    excluded = []
    root_excluded = {
        "worlds", "logs", "crashdumps", "debug", "config", "allowlist.json",
        "permissions.json", "server.properties", "packet-statistics.txt",
    }

    def ignore(directory, names):
        directory = Path(directory)
        ignored = []
        for name in names:
            rel = (directory / name).relative_to(server)
            if (len(rel.parts) == 1 and name in root_excluded) or name.lower().startswith("contentlog") or name.endswith(".log"):
                ignored.append(name)
            elif len(rel.parts) == 2 and rel.parts[0] in {"behavior_packs", "resource_packs"} and not BUILTIN_PACK.fullmatch(name):
                ignored.append(name)
            elif (directory / name).is_symlink():
                raise CraftError(f"Native runtime contains a symlink; use a fully extracted runtime: {rel}")
        excluded.extend((directory / name).relative_to(server).as_posix() for name in ignored)
        return ignored

    shutil.copytree(server, stage, ignore=ignore)
    return sorted(excluded)


def _port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _check_assertion(value, expected, block_ids, item_ids, has_scenario):
    if value.get("boots") != expected:
        raise CraftError(f"Expected boot {expected}, observed {value.get('boots')}")
    if value.get("passed") is not True:
        raise CraftError("Native content/scenario assertions failed: " + "; ".join(value.get("errors", [])))
    blocks, items = value.get("blocks", []), value.get("items", [])
    if {b.get("id") for b in blocks} != block_ids or len(blocks) != len(block_ids):
        raise CraftError("Native block assertion inventory differs from the declared project content.")
    if {i.get("id") for i in items} != item_ids or len(items) != len(item_ids):
        raise CraftError("Native item assertion inventory differs from the declared project content.")
    if any(not all(b.get(k) is True for k in ("registered", "resolved", "placed")) for b in blocks):
        raise CraftError("A declared block failed registry, permutation or placement checks.")
    if any(not all(i.get(k) is True for k in ("registered", "constructed")) for i in items):
        raise CraftError("A declared item failed registry or construction checks.")
    assertions = value.get("assertions", [])
    if has_scenario and not assertions:
        raise CraftError("Native scenario did not execute any named assertions.")
    if any(a.get("passed") is not True or not isinstance(a.get("name"), str) or not a["name"].strip() for a in assertions):
        raise CraftError("A native scenario assertion failed.")


def _probe_source(token, key, block_ids, item_ids, scenario_name=None):
    source = r'''
import {world, system, BlockTypes, BlockPermutation, ItemTypes, ItemStack} from '@minecraft/server';
__SCENARIO_IMPORT__
const token = __TOKEN__, key = __KEY__, blockIds = __BLOCKS__, itemIds = __ITEMS__;
const waitTicks = ticks => new Promise(resolve => system.runTimeout(resolve, ticks));
world.afterEvents.worldLoad.subscribe(() => {
  system.run(() => run().catch(error => console.warn('[AERO_CRAFT_SMOKE] ' + JSON.stringify({token, passed:false, errors:[String(error)]}))));
});
async function run() {
  const old = world.getDynamicProperty(key), boot = typeof old === 'number' ? old + 1 : 1;
  world.setDynamicProperty(key, boot);
  const dimension = world.getDimension('overworld');
  const report = {token, boots:boot, passed:false, blocks:[], items:[], assertions:[], errors:[]};
  const positions = {};
  const assert = (condition, name, details = null) => {
    if (typeof condition !== 'boolean' || typeof name !== 'string' || !name.trim())
      throw new TypeError('Use assert(booleanCondition, nonemptyName, details)');
    report.assertions.push({name:String(name), passed:!!condition, details});
    if (!condition) throw new Error('Scenario assertion failed: ' + name);
  };
  try {
    if (boot === 1) dimension.runCommand('tickingarea add 0 0 0 47 255 15 aero_smoke true');
    let ready = false;
    for (let attempt = 0; attempt < 200; attempt++) {
      try { if (dimension.getBlock({x:0,y:80,z:0})) { ready = true; break; } } catch (_) {}
      await waitTicks(1);
    }
    if (!ready) throw new Error('Smoke ticking area did not load without a client');
    for (let i=0; i<blockIds.length; i++) {
      const id=blockIds[i], position={x:i%16, y:80+Math.floor(i/256)*2, z:Math.floor(i/16)%16};
      positions[id]=position;
      const record={id, registered:false, resolved:false, placed:false};
      try {
        record.registered=!!BlockTypes.get(id);
        if (!record.registered) throw new Error('not registered');
        const permutation=BlockPermutation.resolve(id); record.resolved=!!permutation;
        const original=dimension.getBlock(position);
        if (!original) throw new Error('test position unavailable');
        if (boot > 1) record.after_restart=original.typeId;
        // Preserve first-boot blocks and their states for the restart scenario.
        const block=boot > 1 ? dimension.getBlock({...position,x:position.x+32}) : original;
        if (!block) throw new Error('second-boot placement area unavailable');
        block.setPermutation(permutation);
        record.placed=block.typeId===id;
        if (!record.placed) throw new Error('placement readback differs: '+block.typeId);
      } catch (error) { record.error=String(error); report.errors.push('Block '+id+': '+error); }
      report.blocks.push(record);
      if (i%32===31) await waitTicks(1);
    }
    for (const id of itemIds) {
      const record={id, registered:false, constructed:false};
      try {
        record.registered=!!ItemTypes.get(id);
        if (!record.registered) throw new Error('not registered');
        record.constructed=new ItemStack(id,1).typeId===id;
        if (!record.constructed) throw new Error('ItemStack construction failed');
      } catch (error) { record.error=String(error); report.errors.push('Item '+id+': '+error); }
      report.items.push(record);
    }
    if (!report.errors.length) {
      __SCENARIO_RUN__
    }
    await waitTicks(20);
  } catch (error) { report.errors.push(String(error)); }
  report.passed=!report.errors.length;
  console.warn('[AERO_CRAFT_SMOKE] '+JSON.stringify(report));
}
'''
    return (source.replace("__SCENARIO_IMPORT__", f"import {{run as scenario}} from './{scenario_name}';" if scenario_name else "")
        .replace("__SCENARIO_RUN__", "await scenario({world,system,dimension,boot,assert,waitTicks,blockIds,itemIds,positions});\n      if (!report.assertions.length) throw new Error('Native scenario must execute at least one assertion per boot');" if scenario_name else "")
        .replace("__TOKEN__", json.dumps(token)).replace("__KEY__", json.dumps(key))
        .replace("__BLOCKS__", json.dumps(block_ids)).replace("__ITEMS__", json.dumps(item_ids)))


def bedrock_smoke(project, server, output, timeout=120, scenario=None):
    """Test copied packs on BDS; a pass is not a client/gameplay parity claim.

    Optional tests/native-smoke.js exports async run(ctx). It is copied beside the
    first behavior entry, so relative imports resolve there. ctx.assert records
    named assertions and throws on failure; ctx.boot distinguishes the restart.
    """
    project, output = Path(project).resolve(), Path(output).resolve()
    runtime = resolve_bedrock(server)
    server = Path(runtime["path"])
    binary_name = Path(runtime["binary"]).name
    if output.exists() or output.is_relative_to(server) or output.is_relative_to(project):
        raise CraftError("Smoke output must be a new directory outside the project and server.")
    if timeout < 5:
        raise CraftError("Native smoke timeout must be at least five seconds per boot.")
    validation = validate(project)
    if not validation["passed"]:
        raise CraftError("Fix pack validation before running the server: " + "; ".join(validation["errors"]))
    scenario_path = Path(scenario) if scenario else project / "tests/native-smoke.js"
    if not scenario_path.is_absolute():
        scenario_path = project / scenario_path
    if scenario and not scenario_path.is_file():
        raise CraftError("The requested native scenario does not exist.")
    if scenario_path.exists() and (not scenario_path.resolve().is_relative_to(project) or scenario_path.is_symlink() or scenario_path.suffix != ".js"):
        raise CraftError("Native scenario must be a project-owned .js file.")
    scenario_path = scenario_path.resolve() if scenario_path.is_file() else None
    source_packs = {p.relative_to(project).as_posix(): sha256(p) for p in sorted((project / "packs").rglob("*")) if p.is_file()}
    if not source_packs:
        raise CraftError("Native smoke expects a project with a packs directory.")
    digest = hashlib.sha256(json.dumps(source_packs, sort_keys=True).encode()).hexdigest()
    result = {
        "schema_version": 2, "passed": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "project": str(project), "server_sha256": runtime["sha256"], "server_version": None,
        "runtime": runtime, "observed_boots": [], "phases": [], "errors": [],
        "client_rendering_observed": False, "player_interaction_observed": False,
        "multiplayer_observed": False,
        "scope": "Native pack/script loading, declared block registry and default placement, item construction, restart dynamic-property persistence, and explicit scenario assertions. Client visuals, player interactions, recipe execution and gameplay parity are unverified unless separately observed.",
        "source_packs": source_packs, "source_tree_sha256": digest,
        "scenario": {"path": scenario_path.relative_to(project).as_posix(), "sha256": sha256(scenario_path), "passed": False, "assertions": []} if scenario_path else None,
        "mechanics_assertions_observed": False, "validation": validation,
    }
    output.mkdir(parents=True)
    stage = output / "server"
    transcript = []
    token = uuid.uuid4().hex
    expected_scripts = []
    minimum_versions = []
    block_ids, item_ids = set(), set()
    try:
        result["excluded_runtime_content"] = _copy_runtime(server, stage)
        world = stage / "worlds/AERO-validation"
        world.mkdir(parents=True)
        bp_ids, rp_ids, script_entries = [], [], []
        for manifest in sorted((project / "packs").rglob("manifest.json")):
            data = read_json(manifest)
            minimum_versions.append(data["header"]["min_engine_version"])
            types = {m["type"] for m in data["modules"]}
            kind = "resource" if types == {"resources"} else "behavior"
            dest = stage / (kind + "_packs") / ("aero-" + data["header"]["uuid"])
            shutil.copytree(manifest.parent, dest)
            record = {"pack_id": data["header"]["uuid"], "version": data["header"]["version"]}
            (rp_ids if kind == "resource" else bp_ids).append(record)
            if kind == "behavior":
                for folder, key, ids in (("blocks", "minecraft:block", block_ids), ("items", "minecraft:item", item_ids)):
                    for content in (manifest.parent / folder).rglob("*.json"):
                        identifier = read_json(content).get(key, {}).get("description", {}).get("identifier")
                        if identifier:
                            ids.add(identifier)
            for module in data["modules"]:
                if module["type"] == "script":
                    entry = dest / module["entry"]
                    label = (manifest.parent / module["entry"]).relative_to(project).as_posix()
                    expected_scripts.append(label)
                    script_entries.append(entry)
                    with entry.open("a", encoding="utf-8") as handle:
                        handle.write("\nconsole.warn('[AERO_CRAFT_SCRIPT] ' + " + json.dumps(json.dumps({"token": token, "module": label})) + ");\n")
        if not script_entries:
            config = read_json(project / "aero-project.json")
            api = config.get("server_api")
            if not api:
                raise CraftError("A script-free project must pin server_api in aero-project.json for the native probe.")
            dest = stage / "behavior_packs/aero-native-probe"
            pack_uuid = str(uuid.uuid4())
            write_json(dest / "manifest.json", {
                "format_version": 2,
                "header": {"name": "AERO native probe", "uuid": pack_uuid, "version": [1, 0, 0], "min_engine_version": max(minimum_versions)},
                "modules": [{"type": "script", "language": "javascript", "entry": "scripts/main.js", "uuid": str(uuid.uuid4()), "version": [1, 0, 0]}],
                "dependencies": [{"module_name": "@minecraft/server", "version": api}],
            })
            bp_ids.append({"pack_id": pack_uuid, "version": [1, 0, 0]})
            entry = dest / "scripts/main.js"
            entry.parent.mkdir(parents=True)
            entry.write_text("", encoding="utf-8")
            script_entries.append(entry)
        if len(block_ids) > 16384:
            raise CraftError("Native default placement probe supports at most 16,384 declared blocks.")
        helper_name = f"__aero_smoke_{token}.js"
        scenario_name = f"__aero_scenario_{token}.js" if scenario_path else None
        entry = script_entries[0]
        if scenario_path:
            shutil.copy2(scenario_path, entry.parent / scenario_name)
        (entry.parent / helper_name).write_text(_probe_source(token, "aerocraft:test_" + token, sorted(block_ids), sorted(item_ids), scenario_name), encoding="utf-8")
        with entry.open("a", encoding="utf-8") as handle:
            handle.write(f"\nimport './{helper_name}';\n")
        result["declared_content"] = {"blocks": sorted(block_ids), "items": sorted(item_ids), "script_modules": expected_scripts}
        write_json(world / "world_behavior_packs.json", bp_ids)
        write_json(world / "world_resource_packs.json", rp_ids)
        write_json(stage / "allowlist.json", [])
        write_json(stage / "permissions.json", [])
        write_json(stage / "config/default/permissions.json", {"allowed_modules": ["@minecraft/server", "@minecraft/server-ui"]})
        (stage / "server.properties").write_text(
            "server-name=AERO validation\ntransport=nethernet\nserver-ip=127.0.0.1\nlevel-name=AERO-validation\nlevel-type=FLAT\ngamemode=creative\ndifficulty=peaceful\nallow-cheats=true\nonline-mode=true\nallow-list=true\nenable-lan-visibility=false\n"
            f"server-port={_port()}\nserver-portv6={_port()}\n"
            "max-players=1\nview-distance=4\ntick-distance=4\ncontent-log-file-enabled=true\ncontent-log-console-output-enabled=true\nemit-server-telemetry=false\n", encoding="utf-8")

        def phase(expected):
            env = dict(os.environ)
            env["LD_LIBRARY_PATH"] = str(stage) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            # A prior boot's markers must never satisfy this boot's requirements.
            previous_logs = _content_logs(stage)
            proc = subprocess.Popen([str(stage / binary_name)], cwd=stage, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            events = queue.Queue()
            observed_modules = set()
            assertion = None
            entry = {"boot": expected, "script_modules": [], "clean_shutdown": False}
            result["phases"].append(entry)

            def reader():
                for line in proc.stdout:
                    transcript.append(line)
                    events.put(line)

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()

            def observe(line):
                nonlocal assertion
                errors = _errors(line)
                if errors:
                    raise CraftError("Bedrock reported an error: " + errors[0])
                version = re.search(r"\bVersion:\s*(\d+(?:\.\d+){2,3})", line)
                if version:
                    actual = version.group(1)
                    result["server_version"] = actual
                    if runtime.get("expected_version") and runtime["expected_version"] != actual:
                        raise CraftError(f"Expected BDS {runtime['expected_version']}, observed {actual}")
                    if any(tuple(map(int, actual.split(".")[:3])) < tuple(v) for v in minimum_versions):
                        raise CraftError("The native runtime is older than a pack's min_engine_version.")
                for marker in ("[AERO_CRAFT_SCRIPT]", "[AERO_CRAFT_SMOKE]"):
                    if marker not in line:
                        continue
                    value = json.JSONDecoder().raw_decode(line.split(marker, 1)[1].lstrip())[0]
                    if value.get("token") != token:
                        continue
                    if marker == "[AERO_CRAFT_SCRIPT]":
                        observed_modules.add(value["module"])
                    elif value.get("boots") == expected or value.get("boots") is None:
                        assertion = value
                        entry["assertion"] = value
                        _check_assertion(value, expected, block_ids, item_ids, bool(scenario_path))

            try:
                deadline = time.monotonic() + timeout
                log_poll = 0
                while time.monotonic() < deadline:
                    try:
                        observe(events.get(timeout=0.2))
                    except queue.Empty:
                        if proc.poll() is not None:
                            raise CraftError("Bedrock server exited before the smoke assertions.")
                    if time.monotonic() >= log_poll:
                        for name, content in _content_logs(stage).items():
                            previous = previous_logs.get(name, "")
                            start = len(previous) if content.startswith(previous) else 0
                            # A writer can be between writes; defer incomplete lines.
                            end = content.rfind("\n") + 1
                            for line in content[start:end].splitlines():
                                observe(line)
                            previous_logs[name] = content[:end]
                        log_poll = time.monotonic() + 1
                    if assertion is not None and set(expected_scripts) <= observed_modules:
                        if assertion.get("boots") != expected:
                            raise CraftError(f"Expected boot {expected}, observed {assertion.get('boots')}")
                        entry["assertion"] = assertion
                        result["observed_boots"].append(expected)
                        return
                missing = sorted(set(expected_scripts) - observed_modules)
                raise CraftError(f"Timed out waiting for native assertions; missing script markers: {missing}")
            finally:
                entry["script_modules"] = sorted(observed_modules)
                if proc.poll() is None:
                    try:
                        proc.stdin.write("stop\n")
                        proc.stdin.flush()
                        proc.wait(timeout=20)
                        entry["clean_shutdown"] = proc.returncode == 0
                    except (subprocess.TimeoutExpired, BrokenPipeError, OSError):
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                thread.join(timeout=2)
                entry["exit_code"] = proc.returncode
                proc.stdin.close()
                proc.stdout.close()

        phase(1)
        if not result["phases"][-1]["clean_shutdown"]:
            raise CraftError("BDS did not stop cleanly; persistence cannot be verified.")
        phase(2)
        if not result["phases"][-1]["clean_shutdown"]:
            raise CraftError("BDS did not stop cleanly after the second boot.")
        if not result["server_version"]:
            raise CraftError("Native startup did not report its server version.")
        result["passed"] = True
        result["mechanics_assertions_observed"] = bool(scenario_path and all(p.get("assertion", {}).get("assertions") for p in result["phases"]))
    except (CraftError, OSError, ValueError, KeyError) as exc:
        result["failure"] = str(exc)
    finally:
        if result["scenario"] is not None:
            result["scenario"]["assertions"] = [
                {**assertion, "boot": phase["boot"]}
                for phase in result["phases"]
                for assertion in phase.get("assertion", {}).get("assertions", [])
            ]
            result["scenario"]["passed"] = bool(
                result["mechanics_assertions_observed"]
                and all(a.get("passed") is True for a in result["scenario"]["assertions"])
            )
        logs = _content_logs(stage) if stage.exists() else {}
        result["content_logs"] = list(logs)
        combined = "".join(transcript) + "\n" + "\n".join(logs.values())
        result["errors"] = _errors(combined)
        result["warnings"] = list(dict.fromkeys(line.strip() for line in combined.splitlines() if "[warning]" in line.lower()))
        if result["errors"]:
            result["passed"] = False
            result.setdefault("failure", "Native content/runtime errors were reported; inspect server.log and content-logs.json.")
        after = {p.relative_to(project).as_posix(): sha256(p) for p in sorted((project / "packs").rglob("*")) if p.is_file()}
        if after != source_packs or (scenario_path and (not scenario_path.is_file() or sha256(scenario_path) != result["scenario"]["sha256"])):
            result["passed"] = False
            result["failure"] = "Project sources changed during native verification; rerun against the final sources."
        (output / "server.log").write_text("".join(transcript), encoding="utf-8")
        write_json(output / "content-logs.json", logs)
        write_json(output / "report.json", result)
    return result
