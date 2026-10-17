"""Versioned source index, offline guides and installed Bedrock API declarations."""

from __future__ import annotations
import hashlib
from pathlib import Path
import re
import urllib.request
from .common import ROOT, RUNTIME, CraftError, atomic_write, read_json, write_json


def search(query, limit=12):
    terms = query.lower().split()
    hits = []
    for row in read_json(ROOT / "catalog/docs.json"):
        text = " ".join(str(x) for x in row.values()).lower()
        score = sum(text.count(term) for term in terms)
        if score:
            hits.append({"score": score, **row})
    for p in sorted((ROOT / "docs").rglob("*.md")):
        content = p.read_text(encoding="utf-8")
        score = sum(content.lower().count(t) for t in terms)
        if score:
            hits.append(
                {
                    "score": score,
                    "id": "guide:" + p.relative_to(ROOT / "docs").as_posix(),
                    "title": content.splitlines()[0].lstrip("# "),
                    "source": "bundled",
                    "summary": content[:500],
                }
            )
    return sorted(hits, key=lambda x: -x["score"])[:limit]


def read(identifier):
    if identifier.startswith("guide:"):
        path = (ROOT / "docs" / identifier[6:]).resolve()
        if (
            not path.is_relative_to(ROOT / "docs")
            or path.suffix != ".md"
            or not path.is_file()
        ):
            raise CraftError("Unknown guide.")
        return {"id": identifier, "text": path.read_text(encoding="utf-8")}
    row = next(
        (x for x in read_json(ROOT / "catalog/docs.json") if x["id"] == identifier),
        None,
    )
    if row is None:
        raise CraftError("Unknown documentation ID. Use docs search.")
    cached = RUNTIME / "docs" / (identifier + ".txt")
    return {
        **row,
        "cached_text": cached.read_text(encoding="utf-8") if cached.exists() else None,
    }


def cache(identifier):
    row = read(identifier)
    if "url" not in row:
        raise CraftError("This is already a bundled guide.")
    request = urllib.request.Request(
        row["url"], headers={"User-Agent": "AERO-CRAFT/0.1"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(4 * 1024**2 + 1)
        if len(data) > 4 * 1024**2:
            raise CraftError("Documentation exceeds the 4 MiB cache limit.")
        final = response.url
    path = RUNTIME / "docs" / (identifier + ".txt")
    atomic_write(path, data.decode("utf-8", errors="replace"))
    receipt = {
        "source": row["url"],
        "final_url": final,
        "sha256": hashlib.sha256(data).hexdigest(),
        "local": str(path),
        "note": "Local reference cache only; upstream licensing applies. Date-sensitive pages are not an API version lock.",
    }
    write_json(path.with_suffix(".provenance.json"), receipt)
    return receipt


def api_search(query, limit=12):
    if not query.strip():
        raise CraftError("API query cannot be empty.")
    hits = []
    for module in ("@minecraft/server", "@minecraft/server-ui"):
        p = ROOT / "node_modules" / module / "index.d.ts"
        if not p.is_file():
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        version = read_json(p.parent / "package.json")["version"]
        for i, line in enumerate(lines):
            if query.lower() in line.lower():
                hits.append(
                    {
                        "module": module,
                        "version": version,
                        "file": str(p),
                        "line": i + 1,
                        "context": "\n".join(lines[max(0, i - 3) : i + 7]),
                    }
                )
                if len(hits) >= limit:
                    return hits
    return hits
