"""Resolve current stable Bedrock metadata without a model-provider search key.

Resolution records evidence; it never silently upgrades a project's API lock.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from .common import CraftError, read_json, write_json

SOURCES = {
    "downloads": "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links",
    "samples": "https://raw.githubusercontent.com/Mojang/bedrock-samples/main/version.json",
    "server_api": "https://registry.npmjs.org/@minecraft/server/latest",
    "server_ui_api": "https://registry.npmjs.org/@minecraft/server-ui/latest",
}


def _fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "AERO-CRAFT/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if not response.url.startswith("https://"):
            raise CraftError("Release metadata redirected away from HTTPS.")
        data = response.read(4 * 1024**2 + 1)
        if len(data) > 4 * 1024**2:
            raise CraftError("Release metadata exceeds 4 MiB.")
        receipt = {"url": url, "final_url": response.url, "sha256": hashlib.sha256(data).hexdigest()}
    return json.loads(data), receipt


def resolve_bedrock(project):
    """Record official stable samples, runtime downloads and published API pins."""
    project = Path(project).resolve()
    config = read_json(project / "aero-project.json")
    if config.get("loader") != "bedrock":
        raise CraftError("Target resolution requires a Bedrock project.")
    result = {"resolved": False, "profile_matches_latest": False,
              "checked_at": datetime.now(timezone.utc).isoformat(), "sources": {},
              "scope": "Official stable BDS and samples plus Microsoft npm API releases; client store rollout is separately observed."}
    try:
        data = {}
        for name, url in SOURCES.items():
            data[name], result["sources"][name] = _fetch(url)
        downloads = {row["downloadType"]: row["downloadUrl"] for row in data["downloads"]["result"]["links"]
                     if row["downloadType"] in {"serverBedrockLinux", "serverBedrockWindows"}}
        versions = set()
        for url in downloads.values():
            match = re.fullmatch(r"https://www\.minecraft\.net/bedrockdedicatedserver/bin-(?:linux|win)/bedrock-server-(\d+(?:\.\d+){3})\.zip", url)
            if not match:
                raise CraftError("Official stable download URL shape changed; inspect the metadata before updating the resolver.")
            versions.add(match.group(1))
        if len(downloads) != 2 or len(versions) != 1:
            raise CraftError("Official Linux/Windows stable versions are missing or disagree.")
        sample = data["samples"]["latest"]["version"]
        if not re.fullmatch(r"\d+(?:\.\d+){3}", sample):
            raise CraftError("Official stable sample version is not a numeric release.")
        baseline = ".".join(sample.split(".")[:3])
        server_api = data["server_api"]["version"]
        ui_api = data["server_ui_api"]["version"]
        if any(not re.fullmatch(r"\d+\.\d+\.\d+", v) for v in (server_api, ui_api)):
            raise CraftError("Published latest API tags are not stable releases.")
        result.update(resolved=True, bedrock_server_version=next(iter(versions)),
                      sample_version=sample, content_baseline=baseline,
                      server_api=server_api, server_ui_api=ui_api, downloads=downloads,
                      profile_matches_latest=(config.get("minecraft") == baseline
                          and config.get("engine_version") == [int(x) for x in baseline.split(".")]
                          and config.get("server_api") == server_api and config.get("server_ui_api") == ui_api))
        if not result["profile_matches_latest"]:
            result["action"] = "Project pins differ from current stable metadata. Upgrade manifests, dependencies and APIs deliberately, then rerun resolution and all verification. No files were silently upgraded."
    except (OSError, ValueError, KeyError, TypeError, CraftError) as exc:
        result["error"] = str(exc)
        result["action"] = "Resolve this metadata failure before claiming latest-version support; a pinned profile alone is insufficient."
    result["passed"] = result["resolved"] and result["profile_matches_latest"]
    write_json(project / ".aero/target-resolution.json", result)
    contract_path = project / "aero-port.json"
    if contract_path.is_file():
        contract = read_json(contract_path)
        contract["target"]["resolution"] = result
        write_json(contract_path, contract)
    return result
