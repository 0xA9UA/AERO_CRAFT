"""Explicit native runtime registration and bounded, read-only discovery.

Bedrock Dedicated Server is not redistributed. Registrations live in ignored
AERO_CRAFT_HOME. Discovery never walks home or starts an original server.
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import sys

from .common import RUNTIME, CraftError, read_json, sha256, write_json


def _registry():
    return RUNTIME / "runtimes.json"


def _load():
    if not _registry().exists():
        return {"schema_version": 1, "bedrock": {}}
    data = read_json(_registry())
    if data.get("schema_version") != 1 or not isinstance(data.get("bedrock"), dict):
        raise CraftError(f"Invalid native runtime registry: {_registry()}")
    return data


def _directory(path):
    p = Path(path).expanduser().resolve()
    return p.parent if p.name in {"bedrock_server", "bedrock_server.exe"} else p


def _binary(directory):
    preferred = "bedrock_server.exe" if os.name == "nt" else "bedrock_server"
    for name in (preferred, "bedrock_server", "bedrock_server.exe"):
        if (directory / name).is_file():
            return directory / name
    raise CraftError(f"No extracted Bedrock Dedicated Server binary in {directory}")


def _evidence(path):
    directory = _directory(path)
    binary = _binary(directory)
    digest = sha256(binary)
    platform = "windows" if binary.suffix == ".exe" else "linux"
    current = "windows" if os.name == "nt" else sys.platform
    result = {
        "path": str(directory), "binary": str(binary), "sha256": digest,
        "platform": platform, "compatible": platform == current,
        "executable": os.name == "nt" or os.access(binary, os.X_OK),
        "observed_version": None, "version_evidence": None,
    }
    # Old logs are evidence only if the accompanying report binds this binary.
    report_path = directory.parent / "report.json"
    if report_path.is_file():
        try:
            report = read_json(report_path)
            if report.get("server_sha256") == digest:
                version = report.get("server_version")
                if not version:
                    log = directory.parent / "server.log"
                    if log.is_file():
                        match = re.search(r"\bVersion:\s*(\d+(?:\.\d+){2,3})", log.read_text(errors="replace"))
                        version = match.group(1) if match else None
                if version:
                    result.update(observed_version=version, version_evidence=str(report_path))
        except (ValueError, OSError, TypeError):
            pass
    return result


def register_bedrock(path, name="default", expected_version=None):
    """Register an extracted BDS directory (or binary), without altering it."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", name):
        raise CraftError("Runtime name must be 1–64 letters, numbers, dots, underscores or hyphens.")
    if expected_version is not None and not re.fullmatch(r"\d+(?:\.\d+){2,3}", expected_version):
        raise CraftError("Expected BDS version must be numeric, such as 1.26.52.3.")
    record = _evidence(path)
    record.update(name=name, expected_version=expected_version, registered_at=datetime.now(timezone.utc).isoformat())
    data = _load()
    data["bedrock"][name] = record
    write_json(_registry(), data)
    return {**record, "registry": str(_registry())}


def discover_bedrock():
    """List registrations and a shallow set of AERO_CRAFT_HOME locations."""
    candidates = {}
    for name, record in _load()["bedrock"].items():
        path = _directory(record["path"])
        try:
            current = _evidence(path)
            current.update(name=name, origin="registered", expected_version=record.get("expected_version"), registered_sha256=record.get("sha256"), changed=current["sha256"] != record.get("sha256"))
        except (CraftError, OSError) as exc:
            current = {**record, "name": name, "origin": "registered", "available": False, "error": str(exc)}
        candidates["registered:" + name] = current
    known_paths = {r["path"] for r in candidates.values()}
    paths = [RUNTIME / "bedrock", RUNTIME / "bedrock-server", RUNTIME / "bds", RUNTIME / "tools/bedrock-server"]
    # Previous suite smoke runs are useful installations; avoid broad scanning.
    if RUNTIME.is_dir():
        paths.extend(p / "server" for p in sorted(RUNTIME.glob("smoke-*")) if p.is_dir())
    for path in paths:
        path = path.resolve()
        if str(path) in known_paths or not path.is_dir():
            continue
        try:
            candidates[str(path)] = {**_evidence(path), "origin": "suite-local", "changed": False}
        except (CraftError, OSError):
            continue
    rows = list(candidates.values())
    for row in rows:
        row.setdefault("available", True)
        row["usable"] = bool(row["available"] and row.get("compatible") and row.get("executable") and not row.get("changed"))
    return {
        "runtimes": rows, "registry": str(_registry()),
        "scope": "Explicit registrations and known shallow AERO_CRAFT_HOME locations only; no global filesystem scan.",
        "installation": "Extract an official Bedrock Dedicated Server for Linux or Windows, then register its directory. macOS requires a Linux/Windows runtime host.",
    }


def resolve_bedrock(server=None):
    """Resolve a path/name, default registration, or unique suite-local build."""
    if server is not None and _directory(server).is_dir():
        result = _evidence(server)
        if not result["compatible"] or not result["executable"]:
            raise CraftError("The selected Bedrock runtime is not executable or incompatible with this OS. Native BDS supports Linux and Windows.")
        return result
    records = discover_bedrock()["runtimes"]
    if server is not None:
        matches = [r for r in records if r.get("name") == str(server)]
        result = matches[0] if matches else {**_evidence(server), "changed": False}
    else:
        defaults = [r for r in records if r.get("name") == "default"]
        if defaults:
            result = defaults[0]
        else:
            choices = {}
            for row in records:
                if row["usable"]:
                    choices.setdefault(row["sha256"], row)
            if len(choices) != 1:
                raise CraftError("No unique usable Bedrock runtime. List/register a default runtime, or supply --server PATH.")
            result = next(iter(choices.values()))
    if result.get("changed"):
        raise CraftError("Registered BDS binary has changed. Inspect it and register the intended version again.")
    if not result.get("available", True) or not result.get("compatible") or not result.get("executable"):
        raise CraftError("The selected Bedrock runtime is missing, not executable, or incompatible with this OS. Native BDS supports Linux and Windows.")
    return result
