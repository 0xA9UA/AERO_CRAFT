"""Artifact and source inventory without executing a mod."""

from __future__ import annotations
from collections import Counter
import hashlib
import io
from pathlib import Path
import re
import struct
import zipfile
from .common import CraftError, check_zip, files, read_json, sha256

META = {
    "fabric.mod.json",
    "quilt.mod.json",
    "mcmod.info",
    "META-INF/mods.toml",
    "META-INF/neoforge.mods.toml",
    "META-INF/MANIFEST.MF",
    "manifest.json",
    "pack.mcmeta",
}


def inspect_artifact(path, members=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise CraftError(f"Artifact does not exist: {path}")
    try:
        with zipfile.ZipFile(path) as z:
            result = _zip_inventory(z, members)
    except zipfile.BadZipFile as e:
        raise CraftError(f"Not a readable JAR/ZIP/MCPACK/MCADDON: {path}") from e
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size": path.stat().st_size,
        **result,
    }


def _zip_inventory(z, include_members=False, depth=0):
    infos = check_zip(z)
    metadata, classes, resources, content_ids, entries = (
        {},
        Counter(),
        Counter(),
        [],
        [],
    )
    nested = []
    for i in infos:
        if i.is_dir():
            continue
        name = i.filename
        if name.endswith(".class"):
            with z.open(i) as f:
                header = f.read(8)
            if len(header) == 8 and header[:4] == b"\xca\xfe\xba\xbe":
                major = struct.unpack(">H", header[6:8])[0]
                classes[str(major - 44 if major >= 49 else f"class-{major}")] += 1
        resources[Path(name).suffix.lower() or "(none)"] += 1
        if Path(name).name in META or name in META:
            if i.file_size <= 2 * 1024**2:
                metadata[name] = z.read(i).decode("utf-8-sig", errors="replace")
        if re.search(
            r"/(items|blocks|recipes|recipe|models|textures|loot_tables)/", "/" + name
        ):
            content_ids.append(name)
        if (
            depth == 0
            and name.lower().endswith(".mcpack")
            and i.file_size < 128 * 1024**2
        ):
            with zipfile.ZipFile(io.BytesIO(z.read(i))) as pack:
                nested.append(
                    {"member": name, **_zip_inventory(pack, False, depth + 1)}
                )
        if include_members:
            with z.open(i) as f:
                digest = hashlib.file_digest(f, "sha256").hexdigest()
            entries.append({"path": name, "size": i.file_size, "sha256": digest})
    loaders = []
    names = set(z.namelist())
    for marker, loader in [
        ("fabric.mod.json", "fabric"),
        ("quilt.mod.json", "quilt"),
        ("mcmod.info", "forge-legacy"),
        ("META-INF/mods.toml", "forge"),
        ("META-INF/neoforge.mods.toml", "neoforge"),
    ]:
        if marker in names:
            loaders.append(loader)
    if any(Path(n).name == "manifest.json" for n in names) or nested:
        loaders.append("bedrock")
    result = {
        "loaders": loaders,
        "file_count": len(infos),
        "class_java_versions": dict(classes),
        "resources": dict(resources),
        "metadata": metadata,
        "content_paths": content_ids[:1000],
        "content_paths_total": len(content_ids),
        "nested_packs": nested,
        "limitations": [
            "Static inventory does not prove behavior, runtime compatibility, or port parity.",
            "Nested dependency JARs are not recursively analyzed.",
        ],
    }
    if include_members:
        result["members"] = entries
    return result


def inspect_project(path):
    root = Path(path).resolve()
    if not root.is_dir():
        raise CraftError(f"Project not found: {root}")
    counts = Counter()
    markers = {}
    examples = {}
    digest = hashlib.sha256()
    total = 0
    for p in files(root):
        name = p.relative_to(root).as_posix()
        total += 1
        counts[p.suffix.lower()] += 1
        if p.name in {
            "aero-project.json",
            "gradle.properties",
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "package.json",
            "manifest.json",
            "fabric.mod.json",
            "mods.toml",
            "neoforge.mods.toml",
            "mcmod.info",
        }:
            if p.stat().st_size < 2 * 1024**2:
                markers[name] = p.read_text(encoding="utf-8-sig", errors="replace")
        if p.suffix in {".java", ".ts", ".js", ".json", ".toml", ".gradle"}:
            examples.setdefault(p.suffix, [])
            if len(examples[p.suffix]) < 20:
                examples[p.suffix].append(name)
        digest.update(name.encode() + b"\0" + sha256(p).encode() + b"\n")
    return {
        "path": str(root),
        "tree_sha256": digest.hexdigest(),
        "file_count": total,
        "extensions": dict(counts),
        "markers": markers,
        "examples": examples,
        "excluded": [
            "symlinks",
            "build outputs",
            "node_modules",
            "Git and managed caches",
        ],
    }


def compare(old, new):
    a, b = inspect_artifact(old, True), inspect_artifact(new, True)
    left = {x["path"]: x["sha256"] for x in a["members"]}
    right = {x["path"]: x["sha256"] for x in b["members"]}
    return {
        "old_sha256": a["sha256"],
        "new_sha256": b["sha256"],
        "added": sorted(right.keys() - left.keys()),
        "removed": sorted(left.keys() - right.keys()),
        "changed": sorted(k for k in left.keys() & right.keys() if left[k] != right[k]),
        "class_versions": {
            "old": a["class_java_versions"],
            "new": b["class_java_versions"],
        },
    }
