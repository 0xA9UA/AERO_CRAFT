"""Stage a supplied Bedrock server and prove a script can persist data across restart."""

from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from .bedrock import validate
from .common import CraftError, read_json, sha256, write_json


def bedrock_smoke(project, server, output, timeout=120):
    project, server, output = map(
        lambda x: Path(x).resolve(), (project, server, output)
    )
    binary_name = "bedrock_server.exe" if os.name == "nt" else "bedrock_server"
    if not (server / binary_name).is_file():
        raise CraftError(
            "Supply an extracted official Bedrock Dedicated Server for this OS."
        )
    if (
        output.exists()
        or output.is_relative_to(server)
        or output.is_relative_to(project)
    ):
        raise CraftError(
            "Smoke output must be a new directory outside the project and server."
        )
    report = validate(project)
    if not report["passed"]:
        raise CraftError("Fix pack validation before running the server.")
    # Source content is copied; server binaries, worlds and configuration are never edited in place.
    output.mkdir(parents=True)
    stage = output / "server"
    ignored = {
        "worlds",
        "logs",
        "crashdumps",
        "debug",
        "allowlist.json",
        "permissions.json",
        "server.properties",
    }
    shutil.copytree(
        server,
        stage,
        ignore=lambda directory, names: [
            n for n in names if n in ignored or n.startswith("ContentLog")
        ],
    )
    world = stage / "worlds/AERO-validation"
    world.mkdir(parents=True)
    bp_ids = []
    rp_ids = []
    script_entry = None
    for manifest in sorted((project / "packs").rglob("manifest.json")):
        data = read_json(manifest)
        types = {m["type"] for m in data["modules"]}
        kind = "resource" if types == {"resources"} else "behavior"
        dest = stage / (kind + "_packs") / ("aero-" + data["header"]["uuid"])
        shutil.copytree(manifest.parent, dest)
        record = {
            "pack_id": data["header"]["uuid"],
            "version": data["header"]["version"],
        }
        (rp_ids if kind == "resource" else bp_ids).append(record)
        for m in data["modules"]:
            if m["type"] == "script":
                script_entry = dest / m["entry"]
    if script_entry is None:
        raise CraftError("Native persistence smoke requires a script module.")
    key = "aerocraft:test_" + uuid.uuid4().hex
    with script_entry.open("a", encoding="utf-8") as f:
        f.write(
            "\nimport { world as aeroSmokeWorld } from '@minecraft/server';\naeroSmokeWorld.afterEvents.worldLoad.subscribe(() => {\n const previous = aeroSmokeWorld.getDynamicProperty("
            + json.dumps(key)
            + ");\n const boots = typeof previous === 'number' ? previous + 1 : 1;\n aeroSmokeWorld.setDynamicProperty("
            + json.dumps(key)
            + ", boots);\n console.warn('[AERO_CRAFT_SMOKE] ' + JSON.stringify({boots}));\n});\n"
        )
    write_json(world / "world_behavior_packs.json", bp_ids)
    write_json(world / "world_resource_packs.json", rp_ids)
    write_json(stage / "allowlist.json", [])
    write_json(stage / "permissions.json", [])
    write_json(
        stage / "config/default/permissions.json",
        {"allowed_modules": ["@minecraft/server", "@minecraft/server-ui"]},
    )
    (stage / "server.properties").write_text(
        "server-name=AERO validation\ntransport=nethernet\nserver-ip=127.0.0.1\nlevel-name=AERO-validation\nlevel-type=FLAT\ngamemode=creative\ndifficulty=peaceful\nallow-cheats=true\nonline-mode=true\nallow-list=true\nenable-lan-visibility=false\nserver-port=29981\nserver-portv6=29982\nmax-players=1\nview-distance=4\ntick-distance=4\ncontent-log-file-enabled=true\ncontent-log-console-output-enabled=true\n",
        encoding="utf-8",
    )
    transcript = []
    result = {
        "passed": False,
        "server_sha256": sha256(server / binary_name),
        "observed_boots": [],
        "client_rendering_observed": False,
        "scope": "Script loading and world dynamic-property persistence across a real server restart. No gameplay equivalence claim.",
        "source_packs": {
            str(p.relative_to(project)): sha256(p)
            for p in (project / "packs").rglob("*")
            if p.is_file()
        },
    }

    def phase(expected):
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = (
            str(stage) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        )
        proc = subprocess.Popen(
            [str(stage / binary_name)],
            cwd=stage,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        events = queue.Queue()

        def reader():
            for line in proc.stdout:
                transcript.append(line)
                events.put(line)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    line = events.get(timeout=0.5)
                except queue.Empty:
                    if proc.poll() is not None:
                        raise CraftError(
                            "Bedrock server exited before the smoke assertion."
                        )
                    continue
                if re.search(r"\bERROR\]|\[error\]", line, re.I):
                    raise CraftError("Bedrock reported an error: " + line.strip())
                if "[AERO_CRAFT_SMOKE]" in line:
                    value = json.loads(line.split("[AERO_CRAFT_SMOKE]", 1)[1].strip())
                    if value.get("boots") != expected:
                        raise CraftError(f"Expected boot {expected}, observed {value}")
                    result["observed_boots"].append(expected)
                    return
            raise CraftError("Timed out waiting for the native smoke assertion.")
        finally:
            if proc.poll() is None:
                try:
                    proc.stdin.write("stop\n")
                    proc.stdin.flush()
                    proc.wait(timeout=20)
                except (subprocess.TimeoutExpired, BrokenPipeError):
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            thread.join(timeout=2)
            proc.stdin.close()
            proc.stdout.close()

    try:
        phase(1)
        phase(2)
        content = "".join(transcript)
        for log in stage.glob("ContentLog*.txt"):
            content += "\n" + log.read_text(errors="replace")
        errors = [
            x
            for x in content.splitlines()
            if re.search(r"\bERROR\]|\[.*?error\]|unhandled|watchdog.*hang", x, re.I)
        ]
        result["errors"] = errors
        if errors:
            raise CraftError(
                "Native content/runtime errors were reported; inspect the smoke log."
            )
        result["passed"] = True
    except (CraftError, OSError, ValueError) as e:
        result["failure"] = str(e)
    finally:
        (output / "server.log").write_text("".join(transcript), encoding="utf-8")
        write_json(output / "report.json", result)
    return result
