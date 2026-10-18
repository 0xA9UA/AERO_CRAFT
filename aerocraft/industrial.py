"""Create a runnable, original industrial reference slice for Bedrock ports."""

from pathlib import Path
import struct
import zlib

from .common import ROOT, atomic_write, read_json, write_json
from . import projects


def _texture(base, accent):
    """Original 16px machine panel: deterministic PNG, no graphics dependency."""
    raw = bytearray()
    for y in range(16):
        raw.append(0)
        for x in range(16):
            if x in (0, 15) or y in (0, 15):
                color = (27, 31, 37)
            elif 3 <= x <= 12 and 3 <= y <= 9:
                color = accent if (x + y) % 4 else tuple(max(0, v - 30) for v in accent)
            elif y in (11, 13) and 3 <= x <= 12:
                color = (32, 40, 48)
            else:
                color = base
            raw.extend(color)

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def create(path, mod_id):
    """Create a new project, preserving every existing project and world."""
    result = projects.create(path, "bedrock-stable", mod_id, name="AERO Industrial Reference")
    path = Path(result["project"])
    template = ROOT / "examples/industrial-slice"
    for source in sorted(template.rglob("*")):
        if source.is_file():
            atomic_write(path / source.relative_to(template), source.read_text(encoding="utf-8").replace("__MOD_ID__", mod_id))
    manifest_path = path / "packs/behavior/manifest.json"
    manifest = read_json(manifest_path)
    manifest["dependencies"].append({"module_name": "@minecraft/server-ui", "version": result["config"]["server_ui_api"]})
    write_json(manifest_path, manifest)
    colors = {"generator": (237, 145, 47), "cable": (44, 195, 183), "electric_furnace": (66, 139, 231)}
    for name, accent in colors.items():
        target = path / "packs/resource/textures/blocks" / (name + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_texture((112, 125, 137), accent))
    result["reference"] = {
        "kind": "industrial-slice",
        "scope": "Original coal generator, cable network and raw-iron electric furnace; not a Tech Reborn port.",
        "native_scenario": "tests/native-smoke.js",
        "tested": False,
    }
    return result
