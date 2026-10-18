"""Launch the pinned DSH Web UI with suite-local configuration and MCP bridges."""

from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
from .common import ROOT, RUNTIME, CraftError, read_json, write_json
from .toolchains import environment, java_home, node


def install_bundled_skills(dsh_home):
    """Expose the pinned REA instructions without replacing a user's skill."""
    source = ROOT / "node_modules/rea-agents/skills/reverse-engineer-anything"
    target = Path(dsh_home) / "skills/reverse-engineer-anything"
    if target.exists() or target.is_symlink():
        return
    if not (source / "SKILL.md").is_file():
        raise CraftError("Bundled REA skill is missing; run python aero.py setup first.")
    # Copy only the shipped instruction bundle, never another user's skill roots.
    members = [source / "SKILL.md", *sorted((source / "references").rglob("*.md"))]
    if any(p.is_symlink() for p in members):
        raise CraftError("Bundled REA skill must contain regular instruction files.")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError:
        return
    for member in members:
        dest = target / member.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(member, dest)


def prepare(workspace):
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise CraftError("Harness workspace must be an existing directory.")
    entry = ROOT / "node_modules/@deepseek-ai/dsh/lib/bin.js"
    if not entry.is_file():
        raise CraftError("Run python aero.py setup first.")
    env = environment()
    env["DSH_HOME"] = str(RUNTIME / "dsh")
    env["AERO_CRAFT_HOME"] = str(RUNTIME)
    install_bundled_skills(env["DSH_HOME"])
    rea_env = {"PATH": env["PATH"]}
    for key in ("GHIDRA_INSTALL_DIR", "REA_ANALYSIS_PROVIDER", "REA_IDA_MCP_CONFIG", "REA_ADB_PATH"):
        if key in os.environ:
            rea_env[key] = os.environ[key]
    ghidra = RUNTIME / "tools/ghidra"
    if ghidra.exists():
        rea_env.setdefault("GHIDRA_INSTALL_DIR", str(ghidra))
    try:
        home = java_home(21)
        rea_env["JAVA_HOME"] = str(home)
    except CraftError:
        pass
    entries = [
        {
            "id": "aero-craft-policy",
            "name": (ROOT / "plugins/aero-policy.mjs").as_uri(),
            "config": {
                "python": sys.executable,
                "cli": str(ROOT / "aero.py"),
                "workspace": str(workspace),
                "stateDirectory": str(RUNTIME / "dsh/aero-policy"),
                "guide": str(ROOT / "docs/workflows/autonomous-porting.md"),
            },
        },
        {
            "id": "aero-craft-mcp",
            "name": "@deepseek-ai/dsh-mcp-client",
            "config": {
                "serverName": "aerocraft",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(ROOT / "aero.py"), "mcp", "--workspace", str(workspace)],
                "cwd": str(workspace),
                "env": {"AERO_CRAFT_HOME": str(RUNTIME)},
                # Verification may install dependencies and boot BDS twice.
                "toolCallTimeoutMs": 900000,
                "failOnStartupError": True,
            },
        },
        {
            "id": "aero-rea-mcp",
            "name": "@deepseek-ai/dsh-mcp-client",
            "config": {
                "serverName": "rea",
                "transport": "stdio",
                "command": str(node()),
                "args": [str(ROOT / "node_modules/rea-agents/scripts/rea.mjs"), "mcp"],
                "cwd": str(workspace),
                "env": rea_env,
            },
        },
    ]
    # JSON is a YAML subset and safely quotes Windows paths, spaces and Unicode.
    import hashlib

    suffix = hashlib.sha256(str(workspace).encode()).hexdigest()[:12]
    overlay = RUNTIME / "dsh" / ("aero-" + suffix + ".patch.yml")
    write_json(overlay, [{"insert": entries}])
    return entry, overlay, env


def launch(workspace, port=3080, no_open=False, dump=False):
    entry, overlay, env = prepare(workspace)
    args = [node(), entry, "web", "--patch", overlay]
    if dump:
        args += ["--dump-config"]
    else:
        args += ["--host", "127.0.0.1", "--port", str(port)]
        if no_open:
            args += ["--no-open"]
    return subprocess.call(
        [str(x) for x in args], cwd=Path(workspace).resolve(), env=env
    )
