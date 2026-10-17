"""Pinned per-user runtimes; never modifies system Java, shell profiles or PATH."""

from __future__ import annotations
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from .common import (
    ROOT,
    RUNTIME,
    CraftError,
    download,
    extract,
    read_json,
    run,
    sha256,
    write_json,
)


def catalog():
    return read_json(ROOT / "catalog/toolchains.lock.json")["tools"]


def host_key():
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(
        platform.system()
    )
    arch = {"x86_64": "x64", "AMD64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine()
    )
    if not system or not arch:
        raise CraftError(
            f"Unsupported platform: {platform.system()} {platform.machine()}"
        )
    return f"{system}-{arch}"


def spec(name):
    row = catalog().get(name)
    if not row:
        raise CraftError(f"Unknown tool {name}; run tools list.")
    result = row.get("all") or row.get("platforms", {}).get(host_key())
    if not result:
        raise CraftError(
            f"{name} has no pinned build for {host_key()}. Use an explicit external JDK via AERO_JAVA_<major>_HOME or an x64 VM."
        )
    return result


def install(name):
    row = spec(name)
    destination = RUNTIME / "tools" / name
    receipt = destination / "aero-install.json"
    if receipt.is_file() and read_json(receipt).get("sha256") == row["sha256"]:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_suffix(".installing")
    try:
        lock.mkdir()
    except FileExistsError:
        raise CraftError(
            f"Install already in progress: {lock}. If interrupted, remove that empty lock directory and retry."
        ) from None
    try:
        archive = RUNTIME / "downloads" / (row["sha256"] + "." + row["archive"])
        print(f'Installing {name} {row["version"]} for {host_key()}', file=sys.stderr)
        download(row["url"], archive, row["sha256"])
        with tempfile.TemporaryDirectory(
            dir=destination.parent, prefix=".install-"
        ) as tmp:
            stage = Path(tmp) / "payload"
            if row["archive"] == "jar":
                stage.mkdir()
                shutil.copy2(archive, stage / (name + ".jar"))
            else:
                extract(archive, stage)
                children = list(stage.iterdir())
                if len(children) == 1 and children[0].is_dir():
                    stage = children[0]
            write_json(stage / "aero-install.json", row)
            if destination.exists():
                raise CraftError(
                    f"{destination} has a different/incomplete installation. Move it aside before reinstalling."
                )
            shutil.move(str(stage), destination)
        return destination
    finally:
        lock.rmdir()


def java_home(major, ensure=False):
    value = os.environ.get(f"AERO_JAVA_{major}_HOME")
    home = (
        Path(value).expanduser().resolve()
        if value
        else RUNTIME / "tools" / f"jdk{major}"
    )
    if (home / "Contents/Home").is_dir():
        home = home / "Contents/Home"
    executable = home / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not executable.is_file() and ensure and not value:
        install(f"jdk{major}")
        return java_home(major)
    if not executable.is_file():
        raise CraftError(
            f"JDK {major} is missing. Run: python aero.py tools install jdk{major}"
        )
    compiler = home / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    if not compiler.is_file():
        raise CraftError(f"{home} is not a full JDK: javac is missing.")
    release = home / "release"
    if release.is_file():
        match = re.search(
            r'JAVA_VERSION="([^"]+)"', release.read_text(encoding="utf-8")
        )
        if match:
            parts = match.group(1).split(".")
            actual = int(parts[1]) if parts[0] == "1" else int(parts[0])
            if actual != major:
                raise CraftError(
                    f"Expected JDK {major}, but {home} reports Java {actual}."
                )
    return home


def java(major=21, ensure=False):
    return (
        java_home(major, ensure) / "bin" / ("java.exe" if os.name == "nt" else "java")
    )


def node(ensure=False):
    base = RUNTIME / "tools/node"
    binary = base / ("node.exe" if os.name == "nt" else "bin/node")
    if not binary.exists() and ensure:
        install("node")
    if not binary.exists():
        raise CraftError("Node is not installed. Run: python aero.py setup")
    return binary


def environment(jdk=None):
    env = dict(os.environ)
    bins = [str(node().parent), str(ROOT / "node_modules/.bin")]
    if jdk:
        home = java_home(jdk)
        env["JAVA_HOME"] = str(home)
        bins.insert(0, str(home / "bin"))
    env["PATH"] = os.pathsep.join(bins + [env.get("PATH", "")])
    env["GRADLE_USER_HOME"] = str(RUNTIME / "gradle-cache")
    return env


def rea_environment():
    try:
        env = environment(21)
    except CraftError:
        env = environment()
    ghidra = RUNTIME / "tools/ghidra"
    if ghidra.is_dir():
        env.setdefault("GHIDRA_INSTALL_DIR", str(ghidra))
    return env


def npm(args, cwd=ROOT):
    binary = node()
    npm_js = binary.parent / (
        "node_modules/npm/bin/npm-cli.js"
        if os.name == "nt"
        else "../lib/node_modules/npm/bin/npm-cli.js"
    )
    return run([binary, npm_js, *args], cwd=cwd, env=environment())


def setup(profile="standard"):
    node(ensure=True)
    npm(["ci", "--no-audit", "--no-fund"])
    names = [] if profile == "minimal" else ["jdk21", "jdk25", "cfr", "vineflower"]
    if profile == "full":
        names += ["jdk8", "jdk17"]
    installed, unavailable = [], []
    for name in names:
        try:
            spec(name)
        except CraftError as error:
            unavailable.append(str(error))
            continue
        install(name)
        installed.append(name)
    return {
        "installed": installed,
        "unavailable": unavailable,
        "next": "python aero.py harness --workspace <project>",
    }


def doctor():
    rows = []
    for name in catalog():
        try:
            row = spec(name)
            receipt = RUNTIME / "tools" / name / "aero-install.json"
            ok = receipt.is_file() and read_json(receipt).get("sha256") == row["sha256"]
            rows.append(
                {
                    "tool": name,
                    "version": row["version"],
                    "status": "installed" if ok else "available",
                }
            )
        except CraftError as e:
            rows.append({"tool": name, "status": "unsupported", "detail": str(e)})
    npm_modules = {
        name: (
            read_json(ROOT / "node_modules" / name / "package.json").get("version")
            if (ROOT / "node_modules" / name / "package.json").exists()
            else None
        )
        for name in read_json(ROOT / "package.json")["dependencies"]
    }
    return {
        "platform": host_key(),
        "python": platform.python_version(),
        "runtime": str(RUNTIME),
        "tools": rows,
        "npm": npm_modules,
    }


def decompile(source, output, engine="vineflower", jdk=21):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or source.suffix.lower() not in {".jar", ".class"}:
        raise CraftError("Decompile requires a local .jar or .class.")
    if output.exists():
        raise CraftError("Decompilation output must be a new directory.")
    # Inventory validates JAR members before handing a package to an external tool.
    if source.suffix.lower() == ".jar":
        from .inventory import inspect_artifact

        inspect_artifact(source)
    jar = install(engine) / (engine + ".jar")
    executable = java(jdk, ensure=True)
    output.mkdir(parents=True)
    args = [executable, "-Xmx2G", "-jar", jar, source]
    args += ["--outputdir", output, "--silent", "true"] if engine == "cfr" else [output]
    run(args, env=environment(jdk))
    report = {
        "source_sha256": sha256(source),
        "engine": engine,
        "engine_sha256": sha256(jar),
        "jdk": jdk,
        "output": str(output),
        "limitation": "Decompiler output is reconstructed source, not observed runtime behavior.",
    }
    write_json(output / "aero-provenance.json", report)
    return report
