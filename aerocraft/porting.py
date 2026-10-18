"""Explicit port plans and deliberately narrow, loss-aware recipe translation."""

from __future__ import annotations
import json
from pathlib import Path
import re
from .common import ROOT, CraftError, atomic_write, read_json, write_json
from .inventory import inspect_artifact, inspect_project

FEATURES = {
    "registries": "Map block/item/entity identifiers, states and metadata; registrations alone do not establish mechanics.",
    "recipes": "Translate supported data recipes; implement custom serializers, tags, remainders and machine recipes separately.",
    "simulation": "Extract pure machine state transitions; verify ticks, energy/fluid conservation, failure and inventory ownership.",
    "persistence": "Version saves and test migration plus a real stop/start; preserve Bedrock pack UUIDs.",
    "networking": "Rebuild synchronization for the target engine; Java packets and Bedrock script events are not interchangeable.",
    "ui": "Adapt Java screens to Bedrock forms or vice versa; test real player inventory interactions and controller/touch input.",
    "assets": "Resolve model parents and face UVs; verify texture licensing, sounds, particles and client rendering.",
    "worldgen": "Map biome, feature and placement semantics; test newly generated chunks.",
    "runtime": "Test dedicated server loading, restart, multiplayer and a connected client; record each unobserved layer.",
}


def plan(source, target, output, minecraft=None):
    if target not in {"bedrock", "fabric", "neoforge", "forge"}:
        raise CraftError("Target must be bedrock, fabric, neoforge or forge.")
    output = Path(output).resolve()
    if output.exists():
        raise CraftError("Plan output must be a new directory.")
    src = Path(source).resolve()
    inventory = inspect_project(src) if src.is_dir() else inspect_artifact(src)
    profiles = read_json(ROOT / "catalog/profiles.json")
    candidates = [
        x
        for x in profiles.values()
        if x["loader"] == target and (not minecraft or x["minecraft"] == minecraft)
    ]
    profile = candidates[0] if candidates else None
    rows = [
        {
            "feature": k,
            "status": "unassessed",
            "source_evidence": [],
            "target_implementation": [],
            "tests": [],
            "guidance": v,
        }
        for k, v in FEATURES.items()
    ]
    result = {
        "schema_version": 1,
        "source": inventory,
        "target": {
            "loader": target,
            "minecraft": minecraft or (profile or {}).get("minecraft"),
            "jdk": (profile or {}).get("jdk"),
        },
        "features": rows,
        "status": "assessment_required",
        "constraints": [
            "Changing Java bytecode level does not migrate Minecraft/loader APIs.",
            "No blanket 1:1 parity claim; unsupported behavior remains explicit.",
            "Source and third-party assets stay local unless redistribution rights are established.",
        ],
        "validation_layers": [
            "unit",
            "static",
            "build",
            "server",
            "restart",
            "connected-client",
        ],
    }
    output.mkdir(parents=True)
    write_json(output / "port-plan.json", result)
    atomic_write(
        output / "PARITY.md",
        "# Port / migration ledger\n\nSource identity and inventory: `port-plan.json`. All features begin unassessed.\n\n| Feature | Status | Required work |\n|---|---|---|\n"
        + "".join(f"| {k} | Unassessed | {v} |\n" for k, v in FEATURES.items())
        + "\nRecord exact source members, hashes, API versions, tests and observed runtime behavior for each change. Keep adaptations separate from verified equivalence.\n",
    )
    return {
        "output": str(output),
        "plan": str(output / "port-plan.json"),
        "target": result["target"],
        "feature_count": len(rows),
    }


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9_.-]+:[a-z0-9_./-]+", value
    ):
        raise CraftError(f"Invalid identifier: {value!r}")
    if ".." in value.split(":")[1].split("/"):
        raise CraftError("Identifier contains parent traversal.")
    return value


def convert_recipe(data, direction, identifier, mapping=None):
    """Translate crafting recipes with simple item ingredients only; reject lost semantics."""
    if not isinstance(data, dict) or (
        mapping is not None and not isinstance(mapping, dict)
    ):
        raise CraftError("Recipe and item mapping must be JSON objects.")
    mapping = mapping or {}
    _id(identifier)

    def mapped(value):
        value = _id(value)
        if value in mapping:
            return _id(mapping[value])
        if value.startswith("minecraft:"):
            return value
        raise CraftError(f"Missing explicit item mapping: {value}")

    def ingredient(value):
        if not isinstance(value, dict) or set(value) != {"item"}:
            raise CraftError(
                "Only plain item ingredients are supported; resolve tags, alternatives, counts and metadata explicitly."
            )
        return {"item": mapped(value["item"])}

    def result(value, to_java):
        if (
            not isinstance(value, dict)
            or set(value) - {"item", "id", "count"}
            or ("item" in value) == ("id" in value)
        ):
            raise CraftError(
                "Result must contain exactly one item/id and optional count; NBT/components/data need implementation."
            )
        count = value.get("count", 1)
        if type(count) is not int or not 1 <= count <= 64:
            raise CraftError("Result count must be 1..64.")
        return {
            "id" if to_java else "item": mapped(value.get("item", value.get("id"))),
            "count": count,
        }

    if direction == "java-to-bedrock":
        if set(data) - {
            "type",
            "pattern",
            "key",
            "ingredients",
            "result",
            "group",
            "category",
            "show_notification",
        }:
            raise CraftError(
                "Unsupported Java recipe fields/conditions; refusing a lossy conversion."
            )
        kind = data.get("type", "").removeprefix("minecraft:")
        if kind not in {"crafting_shaped", "crafting_shapeless"}:
            raise CraftError(
                "Only shaped/shapeless crafting is supported; cooking XP/times and custom serializers need review."
            )
        body = {"description": {"identifier": identifier}, "tags": ["crafting_table"],
                "unlock": {"context": "AlwaysUnlocked"}}
        if kind == "crafting_shaped":
            body.update(
                pattern=data.get("pattern"),
                key={k: ingredient(v) for k, v in data.get("key", {}).items()},
            )
        else:
            body["ingredients"] = [ingredient(x) for x in data.get("ingredients", [])]
        body["result"] = result(data.get("result"), False)
        _shape(body, kind == "crafting_shaped")
        return {
            "format_version": "1.20.10",
            "minecraft:recipe_" + kind.removeprefix("crafting_"): body,
        }
    if direction != "bedrock-to-java":
        raise CraftError("Unknown recipe direction.")
    kinds = [
        k
        for k in data
        if k in {"minecraft:recipe_shaped", "minecraft:recipe_shapeless"}
    ]
    if len(kinds) != 1 or set(data) - {"format_version", *kinds}:
        raise CraftError(
            "Only shaped/shapeless Bedrock crafting recipes are supported."
        )
    body = data[kinds[0]]
    if not isinstance(body, dict):
        raise CraftError("Bedrock recipe body must be an object.")
    if (
        set(body)
        - {"description", "tags", "pattern", "key", "ingredients", "result", "priority", "unlock"}
        or body.get("priority", 0) != 0
        or body.get("tags") != ["crafting_table"]
        or ("unlock" in body and body["unlock"] != {"context": "AlwaysUnlocked"})
    ):
        raise CraftError(
            "Unsupported recipe station/priority/fields; refusing a lossy conversion."
        )
    shaped = kinds[0].endswith("_shaped")
    _shape(body, shaped)
    out = {
        "type": "minecraft:crafting_" + ("shaped" if shaped else "shapeless"),
        "result": result(body.get("result"), True),
    }
    if shaped:
        out.update(
            pattern=body["pattern"],
            key={k: ingredient(v) for k, v in body["key"].items()},
        )
    else:
        out["ingredients"] = [ingredient(v) for v in body["ingredients"]]
    return out


def _shape(body, shaped):
    if shaped:
        p = body.get("pattern")
        keys = body.get("key", {})
        if (
            not isinstance(p, list)
            or not 1 <= len(p) <= 3
            or any(not isinstance(r, str) or not 1 <= len(r) <= 3 for r in p)
            or len({len(r) for r in p}) != 1
        ):
            raise CraftError("Pattern must be a rectangular 1..3 by 1..3 grid.")
        used = set("".join(p)) - {" "}
        if not used or used != set(keys) or any(len(k) != 1 or k == " " for k in keys):
            raise CraftError("Pattern symbols and key entries must match exactly.")
    elif (
        not isinstance(body.get("ingredients"), list)
        or not 1 <= len(body["ingredients"]) <= 9
    ):
        raise CraftError("Shapeless recipes require 1..9 ingredients.")
