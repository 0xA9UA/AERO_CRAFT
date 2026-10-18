"""Offline checks for common Java-to-Bedrock porting mistakes.

This is a deliberately bounded validator, not a replacement for Minecraft's
schemas or its content log. Reference snapshot: Microsoft Creator documentation,
2026-10-18, Bedrock 1.26.50 / Script API 2.10.0. Unknown components are warnings;
known authoring/API mix-ups are errors. No third-party parser or runtime needed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re


SOURCES = {
    "blocks": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/blockcomponentslist",
    "block_entity": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_block_entity",
    "items": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/itemreference/examples/itemcomponentlist",
    "recipes": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/recipereference/examples/recipedefinitions/minecraftrecipe_shaped",
    "furnace": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/recipereference/examples/recipedefinitions/minecraftrecipe_furnace",
    "features": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/featuresreference/examples/features/minecraftore_feature",
    "registry": "https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/blockcomponentregistry",
    "startup": "https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/startupevent",
    "tick": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_tick",
    "materials": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_material_instances",
    "recipe_unlock": "https://github.com/Mojang/bedrock-samples/blob/main/behavior_pack/recipes/iron_ingot_from_nuggets.json",
    "recipe_unlock_forms": "https://learn.microsoft.com/en-us/minecraft/creator/documents/recipeintroduction?view=minecraft-bedrock-stable#recipe-unlocking",
    "recipe_unlock_contexts": "https://learn.microsoft.com/en-us/minecraft/creator/reference/content/recipereference/examples/recipedefinitions/recipe_shapeless?view=minecraft-bedrock-stable#unlock",
}

BLOCK_COMPONENTS = set("""
block_entity block_light_absorption block_light_emission chest_obstruction
collision_box connection_rule crafting_table destroy_time destructible_by_explosion
destructible_by_mining destruction_particles display_name embedded_visual
entity_fall_on explosion_resistance flammable flower_pottable friction geometry
instrument_sound item_visual light_dampening light_emission liquid_detection loot
map_color material_instances movable placement_filter precipitation_interactions
random_offset redstone_conductivity redstone_consumer redstone_producer replaceable
selection_box support tick transformation bone_visibility breathability
custom_components queued_ticking random_ticking unit_cube
""".split())
ITEM_COMPONENTS = set("""
allow_off_hand block_placer bundle_interaction can_destroy_in_creative compostable
cooldown damage damage_absorption digger display_name durability durability_sensor
dyeable enchantable entity_placer fire_resistant food fuel glint hand_equipped
hover_text_color icon interact_button kinetic_weapon liquid_clipped max_stack_size
piercing_weapon projectile rarity record repairable seed shooter should_despawn
stacked_by_data storage_item storage_weight_limit storage_weight_modifier
swing_duration swing_sounds tags throwable use_animation use_modifiers wearable
chargeable custom_components render_offsets use_duration weapon
""".split())
RECIPE_TYPES = {
    "minecraft:recipe_shaped", "minecraft:recipe_shapeless",
    "minecraft:recipe_furnace", "minecraft:recipe_brewing_mix",
    "minecraft:recipe_brewing_container", "minecraft:recipe_smithing_transform",
    "minecraft:recipe_smithing_trim", "minecraft:recipe_material_reduction",
}
JAVA_TYPES = {
    "minecraft:configured_feature", "minecraft:placed_feature", "minecraft:biome_modifier",
    "minecraft:recipe_smelting", "minecraft:recipe_blasting",
    "minecraft:crafting_shaped", "minecraft:crafting_shapeless",
}
RENDER_METHODS = {"opaque", "double_sided", "blend", "alpha_test", "alpha_test_single_sided", "blend_to_opaque", "alpha_test_to_opaque", "alpha_test_single_sided_to_opaque"}
RECIPE_UNLOCK_CONTEXTS = {"AlwaysUnlocked", "PlayerInWater", "PlayerHasManyItems", "None"}
SCOPE = (
    "Offline targeted content checks: pack locations, known authoring mistakes, "
    "local identifiers/assets and literal script imports/API mistakes. Not full "
    "engine schemas, vanilla identifier validation, rendering, gameplay or runtime proof."
)


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    start: int
    end: int


def _tokens(source):
    """Small lexer for literal-import checks, not a JavaScript parser.

    Comments and strings are kept separate so examples in comments/strings do
    not become API findings. Template expressions and computed APIs are outside
    this check's coverage; typechecking and native execution remain required.
    """
    out = []
    i = 0
    while i < len(source):
        start = i
        c = source[i]
        if c.isspace():
            i += 1
            continue
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            out.append(_Token("comment", source[start:i], start, i))
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = len(source) if end < 0 else end + 2
            out.append(_Token("comment", source[start:i], start, i))
        elif c in "\"'`":
            quote = c
            i += 1
            while i < len(source):
                if source[i] == "\\":
                    i += 2
                elif source[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            out.append(_Token("template" if quote == "`" else "string", source[start + 1:i - 1], start, i))
        elif c == "/" and (not out or out[-1].value in {"=", "(", "[", "{", ",", ":", "!", "return"}):
            # Skip common regular-expression literals as well as quoted examples.
            i += 1
            char_class = False
            while i < len(source) and source[i] != "\n":
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == "[":
                    char_class = True
                elif source[i] == "]":
                    char_class = False
                elif source[i] == "/" and not char_class:
                    i += 1
                    while i < len(source) and source[i].isalpha():
                        i += 1
                    break
                i += 1
            out.append(_Token("regex", source[start:i], start, i))
        elif c.isalpha() or c in "_$":
            i += 1
            while i < len(source) and (source[i].isalnum() or source[i] in "_$"):
                i += 1
            out.append(_Token("word", source[start:i], start, i))
        else:
            i += 1
            out.append(_Token("punct", c, start, i))
    return out


def _exact_file(root, relative, extensions=()):
    """Require a relative, case-correct file path even on Windows/macOS."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        return False
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or ":" in relative:
        return False
    for candidate in (relative, *(relative + suffix for suffix in extensions)):
        current = root
        try:
            for part in PurePosixPath(candidate).parts:
                if part not in {p.name for p in current.iterdir()}:
                    break
                current = current / part
                if current.is_symlink():
                    break
            else:
                if current.is_file():
                    return True
        except (OSError, NotADirectoryError):
            pass
    return False


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_content(project, pack_paths, profile=None):
    """Check pack root directories (or manifest paths) without modifying them.

    Optional ``profile.external_namespaces`` lists separately supplied packs;
    unresolved IDs in those namespaces are warnings rather than local errors.
    Returned diagnostic lists retain up to 12 examples per rule, with exact
    counts in ``checks.finding_counts`` to keep large generated failures usable.
    """
    project = Path(project).resolve()
    profile = profile if isinstance(profile, dict) else {}
    roots = sorted({Path(p).resolve().parent if Path(p).name == "manifest.json" else Path(p).resolve() for p in pack_paths})
    errors, warnings = [], []
    counts = Counter()
    documents = []
    definitions = {name: {} for name in ("blocks", "items", "recipes", "features", "feature_rules")}
    registered = set()
    ticking = set()
    custom_uses = []
    external = {v for v in profile.get("external_namespaces", []) if isinstance(v, str)} if isinstance(profile.get("external_namespaces", []), list) else set()
    atlases = {"block": {}, "item": {}}
    geometry = set()
    references = []
    craft_tags = set()
    scripts = []

    def label(path):
        try:
            return Path(path).relative_to(project).as_posix()
        except ValueError:
            return str(path)

    def issue(rule, path, message, warning=False):
        level = "warning" if warning else "error"
        counts[level + ":" + rule] += 1
        if counts[level + ":" + rule] <= 12:
            (warnings if warning else errors).append(f"{label(path)}: [{rule}] {message}")

    def ref(value, path, kind="items"):
        if isinstance(value, dict):
            value = value.get("name", value.get("item"))
        if isinstance(value, str) and ":" in value and not value.startswith("minecraft:"):
            references.append((value, path, kind))

    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if path.suffix == ".js":
                scripts.append((root, path))
            if path.suffix != ".json" or path.name == "manifest.json":
                continue
            duplicate_keys = []

            def object_pairs(pairs):
                data = {}
                for key, value in pairs:
                    if key in data:
                        duplicate_keys.append(key)
                    data[key] = value
                return data

            try:
                data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=object_pairs)
            except (ValueError, UnicodeError, OSError) as exc:
                issue("json", path, f"Cannot parse JSON: {exc}")
                continue
            for key in duplicate_keys:
                issue("duplicate-json-key", path, f"Duplicate JSON key {key!r} silently overwrites content.")
            if not isinstance(data, dict):
                continue
            documents.append((root, path, data))
            for value in data.get("minecraft:geometry", []) if isinstance(data.get("minecraft:geometry"), list) else []:
                if isinstance(value, dict):
                    description = value.get("description", {})
                    name = description.get("identifier") if isinstance(description, dict) else None
                    if isinstance(name, str):
                        geometry.add(name)
            if path.relative_to(root).as_posix() in {"textures/terrain_texture.json", "textures/item_texture.json"}:
                kind = "block" if path.name == "terrain_texture.json" else "item"
                entries = data.get("texture_data", {})
                if not isinstance(entries, dict):
                    issue("texture-atlas", path, "texture_data must be an object.")
                    continue
                for name, entry in entries.items():
                    atlases[kind][name] = (root, path)
                    textures = entry.get("textures") if isinstance(entry, dict) else None
                    variants = textures if isinstance(textures, list) else [textures]
                    for image in variants:
                        if isinstance(image, dict):
                            image = image.get("path")
                        if not _exact_file(root, image, (".png", ".tga", ".jpg", ".jpeg")):
                            issue("texture-file", path, f"Atlas entry {name!r} refers to missing, escaping or case-mismatched texture {image!r}.")

    def texture(value, kind, path):
        if not isinstance(value, str):
            issue("texture-reference", path, "Texture atlas keys must be strings.")
        elif value not in atlases[kind]:
            # Vanilla aliases are supplied by the base resource pack. A namespace
            # or slash is an unambiguous custom alias/path; plain names may be vanilla.
            custom = ":" in value or "/" in value
            issue("texture-reference", path, f"{value!r} has no entry in {'terrain_texture' if kind == 'block' else 'item_texture'}.json." + (" Vanilla aliases require native verification." if not custom else " PNG files alone do not register an atlas key."), warning=not custom)

    for root, path, data in documents:
        location = path.relative_to(root).parts[0]
        for key, body in data.items():
            if key in JAVA_TYPES:
                issue("java-schema", path, f"{key} is not a Bedrock content type; translate the Java data model.")
            kind = (
                "blocks" if key == "minecraft:block" else
                "items" if key == "minecraft:item" else
                "recipes" if key.startswith("minecraft:recipe_") else
                "feature_rules" if key == "minecraft:feature_rules" else
                "features" if key.startswith("minecraft:") and key.endswith("_feature") else None
            )
            if kind is None:
                continue
            if location != kind:
                issue("content-location", path, f"{key} must be under the pack's {kind}/ directory, not {location}/. Java data/<namespace>/ trees are not loaded by Bedrock.")
            if not isinstance(body, dict):
                issue("content-object", path, f"{key} must be an object.")
                continue
            description = body.get("description", {})
            identifier = description.get("identifier") if isinstance(description, dict) else None
            if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9_.-]+:[a-z0-9_./-]+", identifier):
                issue("identifier", path, f"{key} needs a valid namespaced description.identifier.")
            elif identifier in definitions[kind]:
                issue("duplicate-id", path, f"Duplicate {kind} identifier {identifier}; first defined by {label(definitions[kind][identifier])}.")
            else:
                definitions[kind][identifier] = path
            if kind == "blocks":
                components = body.get("components", {})
                if isinstance(components, dict):
                    table = components.get("minecraft:crafting_table", {})
                    if isinstance(table, dict) and isinstance(table.get("crafting_tags"), list):
                        craft_tags.update(t for t in table["crafting_tags"] if isinstance(t, str))

        if "pools" in data and location != "loot_tables":
            issue("content-location", path, "Loot tables must be under the pack's loot_tables/ directory.")

    # Scan real runtime scripts, not Node-only generator sources outside packs.
    for root, path in scripts:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issue("script-read", path, str(exc))
            continue
        tokens = _tokens(source)
        for token in tokens:
            if token.kind == "comment" and re.search(r"@ts-(?:ignore|nocheck|expect-error)\b", token.value):
                line = source.count("\n", 0, token.start) + 1
                issue("api-suppression", path, f"Line {line}: TypeScript suppression hides runtime API mistakes; remove it and typecheck the real pinned API.")
        # Use a token-spaced version to retain word boundaries.
        code = " ".join(t.value if t.kind in {"word", "punct"} else " " for t in tokens)
        semantic = [t for t in tokens if t.kind not in {"comment", "template", "regex"}]
        world_aliases = set()
        for i, token in enumerate(semantic):
            if token.value not in {"import", "export"} or token.kind != "word":
                continue
            tail = semantic[i + 1:]
            specifier = None
            import_tokens = []
            if tail and tail[0].kind == "string":
                specifier = tail[0]
            elif len(tail) > 1 and tail[0].value == "(" and tail[1].kind == "string":
                specifier = tail[1]
            else:
                for j, part in enumerate(tail):
                    if part.value == ";":
                        break
                    if part.value == "from" and j + 1 < len(tail) and tail[j + 1].kind == "string":
                        specifier = tail[j + 1]
                        import_tokens = tail[:j]
                        break
            if specifier is None:
                continue
            name = specifier.value
            if name == "@minecraft/server":
                for j, part in enumerate(import_tokens):
                    if part.value == "world":
                        alias = import_tokens[j + 2].value if j + 2 < len(import_tokens) and import_tokens[j + 1].value == "as" else "world"
                        world_aliases.add(alias)
            if name.endswith(".json"):
                issue("script-json-import", path, f"Runtime import {name!r}: bundle JSON as JavaScript data; Bedrock's runtime is not Node's JSON-module loader.")
            elif name.startswith("node:"):
                issue("script-node-import", path, f"Runtime import {name!r}: Node builtins are unavailable in Bedrock.")
            elif name.startswith("."):
                target = path.parent / name
                try:
                    relative = target.resolve().relative_to(root).as_posix()
                except ValueError:
                    relative = "../escape"
                if not _exact_file(root, relative):
                    issue("script-import", path, f"Missing or escaping relative runtime import {name!r}; ship the JavaScript dependency inside this pack.")
        for alias in world_aliases:
            if re.search(rf"\b{re.escape(alias)}\s*\.\s*(?:block|item)ComponentRegistry\b", code):
                issue("registry-api", path, "Component registries belong to the system.beforeEvents.startup event, not world.")
        registry_aliases = set(re.findall(r"\b(?:const|let|var)\s+(\w+)\s*=\s*\w+\s*\.\s*(?:block|item)ComponentRegistry\b", code))
        for alias in registry_aliases:
            if re.search(rf"\b{re.escape(alias)}\s*\.\s*registerComponent\s*\(", code):
                issue("registry-api", path, "Use registerCustomComponent(name, handlers); registerComponent is not a Script API registry method.")
        if re.search(r"\b(?:block|item)ComponentRegistry\s*\.\s*registerComponent\s*\(", code):
            issue("registry-api", path, "Use registerCustomComponent, not registerComponent.")
        for i, token in enumerate(semantic):
            if token.kind != "word" or token.value not in {"registerCustomComponent", "registerComponent"}:
                continue
            tail = semantic[i + 1:]
            if len(tail) < 4 or tail[0].value != "(" or tail[1].kind != "string" or tail[2].value != ",":
                continue
            component = tail[1].value
            if token.value == "registerCustomComponent":
                registered.add(component)
            if tail[3].value != "{":
                continue
            depth = 0
            for part in tail[3:]:
                if part.value == "{":
                    depth += 1
                elif part.value == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1 and part.value == "onTick":
                    ticking.add(component)

    for root, path, data in documents:
        for key in ("minecraft:block", "minecraft:item"):
            body = data.get(key)
            if not isinstance(body, dict):
                continue
            kind = "block" if key == "minecraft:block" else "item"
            base = body.get("components", {})
            sets = [base]
            if kind == "block" and isinstance(body.get("permutations"), list):
                sets += [p.get("components", {}) for p in body["permutations"] if isinstance(p, dict)]
            for components in sets:
                if not isinstance(components, dict):
                    issue("components", path, "components must be an object.")
                    continue
                for component, value in components.items():
                    if component.startswith("tag:"):
                        continue  # Native block tags are not script custom components.
                    if not component.startswith("minecraft:"):
                        custom_uses.append((component, path, components, base if isinstance(base, dict) else {}, kind))
                        continue
                    name = component.split(":", 1)[1]
                    if kind == "block" and name in {"inventory", "dynamic_properties"}:
                        issue("block-api-component", path, f"{component} is a Script API component, not this JSON authoring component. Use minecraft:block_entity with container.slot_count / dynamic_properties when supported by the target engine.")
                    elif name in {"queued_ticking", "random_ticking"} and kind == "block":
                        issue("deprecated-component", path, f"{component} is deprecated for current targets; use Script API custom components and minecraft:tick/onRandomTick.")
                    elif name == "mining_speed" and kind == "item":
                        issue("item-component", path, "minecraft:mining_speed is not an item authoring component; use minecraft:digger.destroy_speeds.")
                    elif name not in (BLOCK_COMPONENTS if kind == "block" else ITEM_COMPONENTS):
                        issue("unreviewed-component", path, f"{component} is outside the reviewed {kind} component snapshot; verify against the target engine schema.", warning=True)
                    if name == "custom_components":
                        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                            issue("custom-components", path, "Legacy minecraft:custom_components must be an array of names, not component_to_register or another object. Prefer direct custom components with current format versions.")
                        else:
                            custom_uses.extend((v, path, components, base if isinstance(base, dict) else {}, kind) for v in value)
                    elif name == "loot" and kind == "block":
                        if not isinstance(value, str):
                            issue("block-loot", path, "minecraft:loot must be the pack-relative loot-table path string.")
                        elif not _exact_file(root, value):
                            issue("block-loot", path, f"Missing or escaping loot table {value!r}.")
                    elif name == "map_color" and kind == "block":
                        color = value.get("color") if isinstance(value, dict) else value
                        valid = (isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)) or (isinstance(color, list) and len(color) == 3 and all(type(c) in {int, float} and 0 <= c <= 255 for c in color))
                        if not valid:
                            issue("map-color", path, "minecraft:map_color requires #RRGGBB or RGB values; Java named map colors such as 'stone' are invalid.")
                    elif name == "block_entity" and kind == "block" and isinstance(value, dict):
                        container = value.get("container")
                        if container is not None and (not isinstance(container, dict) or type(container.get("slot_count")) is not int or not 1 <= container["slot_count"] <= 54):
                            issue("block-container", path, "block_entity.container.slot_count must be an integer from 1 to 54.")
                    elif name == "tick" and kind == "block":
                        interval = value.get("interval_range") if isinstance(value, dict) else None
                        if not isinstance(interval, list) or len(interval) != 2 or any(type(n) is not int or n < 0 for n in interval) or interval[0] > interval[1]:
                            issue("block-tick", path, "minecraft:tick needs an ordered nonnegative interval_range of two integers.")
                    elif name == "material_instances" and isinstance(value, dict):
                        for material in value.values():
                            if isinstance(material, dict):
                                if "texture" in material:
                                    texture(material["texture"], "block", path)
                                if "render_method" in material and (not isinstance(material["render_method"], str) or material["render_method"] not in RENDER_METHODS):
                                    issue("render-method", path, f"Invalid render_method {material['render_method']!r}; use a documented Bedrock material render method such as 'opaque', not 'solid'.")
                    elif name == "geometry" and kind == "block":
                        name = value.get("identifier") if isinstance(value, dict) else value
                        if isinstance(name, str) and not name.startswith("minecraft:") and name not in geometry:
                            issue("geometry-reference", path, f"Geometry {name!r} has no definition in supplied resource packs.")
                    elif name == "icon" and kind == "item":
                        if isinstance(value, str):
                            texture(value, "item", path)
                        elif isinstance(value, dict):
                            entries = value.get("textures", value)
                            if isinstance(entries, dict):
                                for icon in entries.values():
                                    texture(icon, "item", path)
                    elif name == "block_placer" and kind == "item" and isinstance(value, dict):
                        ref(value.get("block"), path, "blocks")

        for key, recipe in data.items():
            if not key.startswith("minecraft:recipe_") or not isinstance(recipe, dict):
                continue
            if key not in RECIPE_TYPES and key not in JAVA_TYPES:
                issue("unreviewed-recipe", path, f"Unreviewed recipe type {key}; verify native schema.", warning=True)
            tags = recipe.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str) and tag in {"crafting", "smelting", "blasting"} and tag not in craft_tags:
                        issue("recipe-tag", path, f"Tag {tag!r} has no matching table; vanilla Bedrock uses crafting_table, furnace or blast_furnace.")
            if "count" in recipe:
                issue("recipe-count", path, "Output count belongs inside the result item descriptor, not beside result.")
            if key in {"minecraft:recipe_shaped", "minecraft:recipe_shapeless"}:
                version = str(data.get("format_version", ""))
                if re.fullmatch(r"\d+(?:\.\d+){1,2}", version):
                    numbers = tuple(int(n) for n in version.split("."))
                    if numbers >= (1, 20, 10) and "unlock" not in recipe:
                        issue("recipe-unlock", path, "Crafting recipes with format_version >= 1.20.10 require unlock data, for example [{item: 'minecraft:iron_ingot'}]. Native BDS reports missing unlock as a content error.")
                if "unlock" in recipe:
                    unlock = recipe["unlock"]
                    if isinstance(unlock, list):
                        # Arrays contain ingredients. Native BDS rejects a context-only
                        # array entry as an invalid recipe ingredient; contexts use an object.
                        for ingredient in unlock:
                            descriptors = [ingredient[field] for field in ("item", "tag") if field in ingredient] if isinstance(ingredient, dict) else []
                            if not descriptors or any(not isinstance(value, str) or not value.strip() for value in descriptors):
                                issue("recipe-unlock", path, "Unlock array entries must be item/tag ingredient descriptors with nonempty string values; use unlock: {context: 'AlwaysUnlocked'} for a context, without an array.")
                    elif isinstance(unlock, dict):
                        context = unlock.get("context")
                        if not isinstance(context, str) or not context.strip():
                            issue("recipe-unlock", path, "Unlock objects require a string context; put item/tag ingredients inside an unlock array.")
                        elif context not in RECIPE_UNLOCK_CONTEXTS:
                            issue("recipe-unlock-context", path, f"Unreviewed unlock context {context!r}; documented spellings are {', '.join(sorted(RECIPE_UNLOCK_CONTEXTS))}. Verify the target engine accepts this context.", warning=True)
                    else:
                        issue("recipe-unlock", path, "Unlock must be an item/tag ingredient array or a context object.")
                result = recipe.get("result")
                results = result if isinstance(result, list) else [result]
                for item in results:
                    if not isinstance(item, dict) or not isinstance(item.get("item"), str):
                        issue("recipe-result", path, "Crafting result must be an item descriptor {item, count}, or a supported array of descriptors.")
                    else:
                        ref(item["item"], path)
                        if "count" in item and (type(item["count"]) is not int or item["count"] < 1):
                            issue("recipe-count", path, "Result count must be a positive integer.")
                if key.endswith("_shaped"):
                    keys = recipe.get("key", {})
                    if not isinstance(keys, dict):
                        issue("recipe-key", path, "Shaped recipe key must be an object of item/tag descriptors.")
                    else:
                        for value in keys.values():
                            if not isinstance(value, dict) or not ("item" in value or "tag" in value):
                                issue("recipe-key", path, "Each shaped recipe key needs an {item: ...} or {tag: ...} descriptor, not a Java item string.")
                            elif "item" in value:
                                ref(value["item"], path)
                        pattern = recipe.get("pattern")
                        if isinstance(pattern, list) and all(isinstance(row, str) for row in pattern):
                            used = set("".join(pattern)) - {" "}
                            if used - keys.keys():
                                issue("recipe-key", path, f"Pattern symbols have no ingredient: {sorted(used - keys.keys())}.")
                else:
                    ingredients = recipe.get("ingredients", [])
                    if isinstance(ingredients, list):
                        if len(ingredients) > 9:
                            issue("recipe-ingredients", path, "Shapeless crafting has more than 9 ingredients; do not expand tag alternatives into simultaneous requirements.")
                        for value in ingredients:
                            if not isinstance(value, dict) or not ("item" in value or "tag" in value):
                                issue("recipe-ingredients", path, "Shapeless ingredients need item/tag descriptors.")
            for node in _walk(recipe):
                for key in ("item", "input", "output", "reagent", "base", "addition", "template"):
                    if key in node:
                        ref(node[key], path)

        if "pools" in data:
            for node in _walk(data):
                if node.get("type") == "item":
                    ref(node.get("name"), path)
                elif node.get("type") == "loot_table" and not _exact_file(root, node.get("name")):
                    issue("loot-reference", path, f"Missing referenced loot table {node.get('name')!r}.")
        for key, body in data.items():
            if not isinstance(body, dict) or not (key == "minecraft:feature_rules" or key.startswith("minecraft:") and key.endswith("_feature")):
                continue
            for node in _walk(body):
                for field in ("places_block", "may_replace", "may_place_on", "may_attach_to"):
                    values = node.get(field, [])
                    for value in values if isinstance(values, list) else [values]:
                        ref(value, path, "blocks")
                for field in ("feature", "places_feature", "feature_to_snap", "feature_to_place"):
                    if field in node:
                        ref(node[field], path, "features")

    for component, path, components, base, kind in custom_uses:
        if component not in registered:
            issue("custom-registration", path, f"No literal registerCustomComponent call found for {component!r}; dynamic registration needs native verification.", warning=True)
        if kind == "block" and component in ticking and "minecraft:tick" not in components and "minecraft:tick" not in base:
            issue("missing-tick", path, f"{component} handles onTick but the block has no minecraft:tick component.")

    for value, path, kind in sorted(set(references), key=lambda r: (str(r[1]), r[0], r[2])):
        known = definitions[kind]
        if value in known or kind == "items" and value in definitions["blocks"]:
            continue
        namespace = value.split(":", 1)[0]
        issue("unknown-reference", path, f"Unknown {kind} identifier {value!r} in supplied packs." + (" External dependency needs native verification." if namespace in external else ""), warning=namespace in external)
    for key, count in sorted(counts.items()):
        if count > 12:
            level, rule = key.split(":", 1)
            (warnings if level == "warning" else errors).append(f"[{rule}] {count - 12} additional findings omitted; {count} total.")
    return {
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "snapshot": "2026-10-18",
            "json_files": len(documents),
            "script_files": len(scripts),
            "definitions": {kind: len(values) for kind, values in definitions.items()},
            "texture_atlas_entries": {kind: len(values) for kind, values in atlases.items()},
            "finding_counts": dict(sorted(counts.items())),
            "vanilla_identifiers_validated": False,
            "runtime_executed": False,
        },
        "scope": SCOPE,
    }
