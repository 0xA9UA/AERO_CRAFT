#!/usr/bin/env python3
"""Maintainer-only resolver. Review and commit changed hashes; never runs at install."""

import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "linux-x64": ("linux", "x64"),
    "linux-arm64": ("linux", "aarch64"),
    "darwin-x64": ("mac", "x64"),
    "darwin-arm64": ("mac", "aarch64"),
    "windows-x64": ("windows", "x64"),
}


def read(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AERO-CRAFT/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def jdk(task):
    major, key, (osname, arch) = task
    url = f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture={arch}&image_type=jdk&os={osname}&vendor=eclipse"
    records = json.loads(read(url))
    if not records:
        return major, key, None
    result = records[0]
    p = result["binary"]["package"]
    return (
        major,
        key,
        {
            "url": p["link"],
            "sha256": p["checksum"],
            "version": result["version"]["semver"],
            "archive": "zip" if osname == "windows" else "tar.gz",
            "license": "GPL-2.0-with-classpath-exception",
            "source": url,
        },
    )


def hashed(url, version, license, archive="jar"):
    data = read(url)
    return {
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": version,
        "archive": archive,
        "license": license,
    }


def main():
    tools = {}
    v = "24.22.0"
    sums = {
        row.split()[1]: row.split()[0]
        for row in read(f"https://nodejs.org/dist/v{v}/SHASUMS256.txt")
        .decode()
        .splitlines()
    }
    nodes = {}
    for key in PLATFORMS:
        osname, arch = key.split("-")
        filename = f'node-v{v}-{"win" if osname == "windows" else osname}-{arch}.{"zip" if osname == "windows" else "tar.gz"}'
        nodes[key] = {
            "version": v,
            "url": f"https://nodejs.org/dist/v{v}/{filename}",
            "sha256": sums[filename],
            "archive": "zip" if osname == "windows" else "tar.gz",
            "license": "MIT and bundled dependency notices",
        }
    tools["node"] = {"platforms": nodes}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for major, key, item in pool.map(
            jdk, [(m, k, p) for m in (8, 17, 21, 25) for k, p in PLATFORMS.items()]
        ):
            if item is not None:
                tools.setdefault(f"jdk{major}", {"platforms": {}})["platforms"][
                    key
                ] = item
    tools["cfr"] = {
        "all": hashed("https://www.benf.org/other/cfr/cfr-0.152.jar", "0.152", "MIT")
    }
    tools["vineflower"] = {
        "all": hashed(
            "https://github.com/Vineflower/vineflower/releases/download/1.12.0/vineflower-1.12.0.jar",
            "1.12.0",
            "Apache-2.0",
        )
    }
    for v in ("8.14.3", "9.2.1"):
        url = f"https://services.gradle.org/distributions/gradle-{v}-bin.zip"
        tools[f"gradle{v}"] = {
            "all": {
                "version": v,
                "url": url,
                "sha256": read(url + ".sha256").decode().strip(),
                "archive": "zip",
                "license": "Apache-2.0",
            }
        }
    release = json.loads(
        read(
            "https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest"
        )
    )
    asset = next(a for a in release["assets"] if a["name"].endswith(".zip"))
    digest = asset.get("digest", "")
    if digest.startswith("sha256:"):
        tools["ghidra"] = {
            "all": {
                "url": asset["browser_download_url"],
                "sha256": digest[7:],
                "version": release["tag_name"],
                "archive": "zip",
                "license": "Apache-2.0 and bundled notices",
            }
        }
    result = {
        "schema_version": 1,
        "resolved_on": "2026-10-17",
        "harness": {
            "npm": "@deepseek-ai/dsh",
            "version": "0.2.1-rc.2",
            "tag": "dsh-v0.2.1-rc.2",
            "commit": "687f282e8625c6b8d11ff58211a90524be2e4317",
        },
        "tools": tools,
    }
    (ROOT / "catalog/toolchains.lock.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(f"Resolved {len(tools)} tool families")


if __name__ == "__main__":
    main()
