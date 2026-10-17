"""Pack validation and deterministic distributable generation."""

from __future__ import annotations
import io
import json
import os
import tempfile
from pathlib import Path
import re
import uuid
import zipfile
from .common import CraftError, files, read_json, sha256, write_json


def validate(path):
    path = Path(path).resolve()
    packroot = path / "packs" if (path / "packs").is_dir() else path
    manifests = sorted(packroot.rglob("manifest.json"))
    errors = []
    warnings = []
    headers = {}
    uuids = set()
    packs = []
    if not manifests:
        errors.append("No manifest.json files found.")

    def version(v):
        return (
            isinstance(v, list)
            and len(v) == 3
            and all(type(x) is int and x >= 0 for x in v)
        )

    def identifier(v, where):
        try:
            uuid.UUID(v)
        except (ValueError, TypeError, AttributeError):
            errors.append(f"{where}: invalid UUID")
            return
        if v.lower() in uuids:
            errors.append(f"{where}: duplicate UUID {v}")
        uuids.add(v.lower())

    for manifest in manifests:
        label = manifest.relative_to(path).as_posix()
        if manifest.is_symlink():
            errors.append(f"{label}: symlink manifest")
            continue
        try:
            data = read_json(manifest)
            if not isinstance(data, dict):
                raise ValueError("manifest must be an object")
            if data.get("format_version") != 2:
                errors.append(f"{label}: expected stable manifest format 2")
            h = data.get("header", {})
            if not isinstance(h, dict):
                raise ValueError("header must be an object")
            deps = data.get("dependencies", [])
            if not isinstance(deps, list) or any(not isinstance(d, dict) for d in deps):
                raise ValueError("dependencies must be an array of objects")
            identifier(h.get("uuid"), label)
            if not version(h.get("version")):
                errors.append(f"{label}: invalid header version")
            if not version(h.get("min_engine_version")):
                errors.append(f"{label}: min_engine_version is required")
            if not h.get("name"):
                errors.append(f"{label}: name is required")
            if isinstance(h.get("uuid"), str):
                headers[h["uuid"].lower()] = h.get("version")
            modules = data.get("modules", [])
            if not isinstance(modules, list) or any(
                not isinstance(m, dict) for m in modules
            ):
                raise ValueError("modules must be an array of objects")
            if not modules:
                errors.append(f"{label}: modules are required")
            for m in modules:
                identifier(m.get("uuid"), label)
                if not version(m.get("version")):
                    errors.append(f"{label}: invalid module version")
                if m.get("type") not in {"data", "resources", "script"}:
                    errors.append(f"{label}: unsupported module type")
                if m.get("type") == "script":
                    entry = m.get("entry", "")
                    target = (manifest.parent / entry).resolve()
                    if (
                        not entry
                        or not target.is_relative_to(manifest.parent.resolve())
                        or not target.is_file()
                    ):
                        errors.append(
                            f"{label}: missing or escaping script entry {entry}"
                        )
                    if m.get("language") != "javascript":
                        errors.append(f"{label}: script language must be javascript")
                    deps = {d.get("module_name") for d in data.get("dependencies", [])}
                    if "@minecraft/server" not in deps:
                        errors.append(
                            f"{label}: script pack needs @minecraft/server dependency"
                        )
            packs.append((manifest, data))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            errors.append(f"{label}: {e}")
    for manifest, data in packs:
        for d in data.get("dependencies", []):
            if "uuid" in d:
                key = str(d["uuid"]).lower()
                if key not in headers:
                    errors.append(
                        f'{manifest.name}: unresolved pack dependency {d["uuid"]}'
                    )
                elif d.get("version") != headers[key]:
                    errors.append(f"{manifest.name}: dependency version mismatch")
            elif "module_name" in d:
                if not isinstance(d.get("version"), str):
                    errors.append("Script API versions must be strings.")
                elif "beta" in d["version"]:
                    warnings.append(
                        f'Experimental API {d["module_name"]}@{d["version"]}'
                    )
            else:
                errors.append("Dependency requires uuid or module_name.")
        for p in manifest.parent.rglob("*"):
            if p.is_symlink():
                errors.append(f"Symlinks are not allowed in packs: {p}")
            elif p.is_file() and p.suffix == ".json":
                try:
                    read_json(p)
                except (ValueError, UnicodeError) as e:
                    errors.append(f"{p.relative_to(path)}: invalid JSON: {e}")
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "pack_count": len(packs),
        "scope": "Structure, manifest references and JSON syntax. Engine schemas, API execution and client rendering require native tests.",
    }


def zip_bytes(root):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(Path(root).rglob("*")):
            if p.is_symlink():
                raise CraftError("Cannot package symlinks.")
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                if p.suffix not in {
                    ".json",
                    ".js",
                    ".png",
                    ".tga",
                    ".jpg",
                    ".jpeg",
                    ".ogg",
                    ".wav",
                    ".lang",
                    ".txt",
                    ".mcstructure",
                    ".material",
                    ".fsh",
                    ".vsh",
                }:
                    raise CraftError(
                        f"Unexpected pack file {rel}; keep sources, secrets and test tools outside packs."
                    )
                info = zipfile.ZipInfo(rel, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, p.read_bytes())
    return stream.getvalue()


def package(path):
    path = Path(path).resolve()
    report = validate(path)
    if not report["passed"]:
        raise CraftError("Pack validation failed: " + "; ".join(report["errors"]))
    c = read_json(path / "aero-project.json")
    output = path / "dist"
    output.mkdir(exist_ok=True)
    # File name cannot be influenced by an unchecked project ID/version.
    if not re.fullmatch(r"[a-z0-9_]+", c["id"]) or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", c["version"]
    ):
        raise CraftError("Invalid package ID/version.")
    addon = output / (c["id"] + "-" + c["version"] + ".mcaddon")
    fd, temporary = tempfile.mkstemp(prefix=".addon-", dir=output)
    os.close(fd)
    try:
        with zipfile.ZipFile(
            temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        ) as z:
            for manifest in sorted((path / "packs").rglob("manifest.json")):
                info = zipfile.ZipInfo(
                    manifest.parent.relative_to(path / "packs").as_posix() + ".mcpack",
                    (1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, zip_bytes(manifest.parent))
        os.replace(temporary, addon)
    finally:
        Path(temporary).unlink(missing_ok=True)
    result = {
        "artifact": str(addon),
        "sha256": sha256(addon),
        "validation": report,
        "runtime_tested": False,
    }
    write_json(output / "build-report.json", result)
    (output / "SHA256SUMS").write_text(
        result["sha256"] + "  " + addon.name + "\n", encoding="utf-8"
    )
    return result
