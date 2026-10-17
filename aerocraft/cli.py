"""A single portable entry point for the Minecraft development suite."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
from . import (
    __version__,
    bedrock,
    docs,
    harness,
    inventory,
    porting,
    projects,
    toolchains,
)
from .common import ROOT, CraftError, extract, read_json, run, write_json


def parser():
    p = argparse.ArgumentParser(
        prog="aero", description="AERO_CRAFT — Minecraft development and porting suite"
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser(
        "setup", help="Install pinned Node, harness, REA, APIs and optional JVM tools"
    )
    q.add_argument(
        "--profile", choices=["minimal", "standard", "full"], default="standard"
    )
    sub.add_parser("doctor", help="Report installed and available tools")
    sub.add_parser("profiles", help="List pinned project profiles")
    q = sub.add_parser("tools")
    s = q.add_subparsers(dest="action", required=True)
    s.add_parser("list")
    s.add_parser("install").add_argument("names", nargs="+")
    q = sub.add_parser("new", help="Create a starter project")
    q.add_argument("path")
    q.add_argument("--profile", required=True, choices=list(projects.profiles()))
    q.add_argument("--id", required=True)
    q.add_argument("--name")
    q.add_argument("--package", default="dev.aerocraft")
    q = sub.add_parser(
        "build", help="Build a project; Bedrock also typechecks, tests and packages"
    )
    q.add_argument("path")
    q = sub.add_parser(
        "gradle", help="Run a task with the project-pinned Gradle and JDK"
    )
    q.add_argument("path")
    q.add_argument("args", nargs=argparse.REMAINDER)
    q = sub.add_parser("inspect", help="Inventory an archive or source project")
    q.add_argument("path")
    q.add_argument("--members", action="store_true")
    q.add_argument("--output")
    q = sub.add_parser("compare")
    q.add_argument("old")
    q.add_argument("new")
    q.add_argument("--output")
    q = sub.add_parser("extract")
    q.add_argument("path")
    q.add_argument("output")
    q = sub.add_parser("decompile")
    q.add_argument("path")
    q.add_argument("--output", required=True)
    q.add_argument("--engine", choices=["cfr", "vineflower"], default="vineflower")
    q.add_argument("--jdk", type=int, default=21)
    q = sub.add_parser(
        "port", help="Create a source-grounded port / upgrade assessment"
    )
    q.add_argument("source")
    q.add_argument(
        "--to", choices=["bedrock", "fabric", "neoforge", "forge"], required=True
    )
    q.add_argument("--minecraft")
    q.add_argument("--output", required=True)
    q = sub.add_parser("recipe", help="Convert supported plain crafting recipes")
    q.add_argument("path")
    q.add_argument(
        "--direction", choices=["java-to-bedrock", "bedrock-to-java"], required=True
    )
    q.add_argument("--id", required=True)
    q.add_argument("--mapping")
    q.add_argument("--output", required=True)
    q = sub.add_parser("validate")
    q.add_argument("path")
    q = sub.add_parser("package")
    q.add_argument("path")
    q = sub.add_parser(
        "smoke", help="Stage a supplied BDS runtime and test script persistence"
    )
    q.add_argument("path")
    q.add_argument("--server", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--timeout", type=int, default=120)
    q = sub.add_parser("docs")
    s = q.add_subparsers(dest="action", required=True)
    for n, k in [
        ("search", "query"),
        ("read", "id"),
        ("cache", "id"),
        ("api", "query"),
    ]:
        s.add_parser(n).add_argument(k)
    q = sub.add_parser("harness", help="Start the pinned DeepSeek Web UI and MCP tools")
    q.add_argument("--workspace", default=".")
    q.add_argument("--port", type=int, default=3080)
    q.add_argument("--no-open", action="store_true")
    q.add_argument("--dump-config", action="store_true")
    q = sub.add_parser("rea", help="Run the pinned REA CLI")
    q.add_argument("args", nargs=argparse.REMAINDER)
    q = sub.add_parser("mcp", help="Serve workspace-scoped MCP over stdio")
    q.add_argument("--workspace", required=True)
    return p


def main(argv=None):
    # MCP and JSON output are UTF-8 even when Windows pipes default to a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    a = parser().parse_args(argv)
    try:
        c = a.command
        result = None
        if c == "setup":
            result = toolchains.setup(a.profile)
        elif c == "doctor":
            result = toolchains.doctor()
        elif c == "profiles":
            result = projects.profiles()
        elif c == "tools":
            result = (
                toolchains.catalog()
                if a.action == "list"
                else {"installed": {n: str(toolchains.install(n)) for n in a.names}}
            )
        elif c == "new":
            result = projects.create(a.path, a.profile, a.id, a.name, a.package)
        elif c == "build":
            result = projects.build(a.path)
        elif c == "gradle":
            return projects.gradle(
                a.path, a.args[1:] if a.args[:1] == ["--"] else a.args
            )
        elif c == "inspect":
            result = (
                inventory.inspect_project(a.path)
                if Path(a.path).is_dir()
                else inventory.inspect_artifact(a.path, a.members)
            )
        elif c == "compare":
            result = inventory.compare(a.old, a.new)
        elif c == "extract":
            result = {"output": str(extract(a.path, a.output))}
        elif c == "decompile":
            result = toolchains.decompile(a.path, a.output, a.engine, a.jdk)
        elif c == "port":
            result = porting.plan(a.source, a.to, a.output, a.minecraft)
        elif c == "recipe":
            if Path(a.output).exists():
                raise CraftError("Recipe output already exists.")
            result = porting.convert_recipe(
                read_json(a.path),
                a.direction,
                a.id,
                read_json(a.mapping) if a.mapping else None,
            )
            write_json(a.output, result)
        elif c == "validate":
            result = bedrock.validate(a.path)
        elif c == "package":
            result = bedrock.package(a.path)
        elif c == "smoke":
            from .smoke import bedrock_smoke

            result = bedrock_smoke(a.path, a.server, a.output, a.timeout)
        elif c == "docs":
            result = {
                "search": lambda: docs.search(a.query),
                "read": lambda: docs.read(a.id),
                "cache": lambda: docs.cache(a.id),
                "api": lambda: docs.api_search(a.query),
            }[a.action]()
        elif c == "harness":
            return harness.launch(a.workspace, a.port, a.no_open, a.dump_config)
        elif c == "rea":
            return run(
                [
                    toolchains.node(),
                    ROOT / "node_modules/rea-agents/scripts/rea.mjs",
                    *(a.args[1:] if a.args[:1] == ["--"] else a.args),
                ],
                env=toolchains.rea_environment(),
            )
        elif c == "mcp":
            from .mcp import serve

            serve(a.workspace)
            return 0
        if result is not None:
            if c in {"inspect", "compare"} and a.output:
                write_json(a.output, result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if isinstance(result, dict) and result.get("passed") is False else 0
    except (CraftError, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print(f"AERO_CRAFT: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
