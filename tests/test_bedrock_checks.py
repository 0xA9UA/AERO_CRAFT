import json
from pathlib import Path
import tempfile
import unittest

from aerocraft.bedrock_checks import validate_content


class BedrockContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bp = self.root / "packs/behavior"
        self.rp = self.root / "packs/resource"
        self.bp.mkdir(parents=True)
        self.rp.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, value, resource=False):
        path = (self.rp if resource else self.bp) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def block(self, name="aero:machine", components=None, file="blocks/machine.json"):
        return self.write(file, {
            "format_version": "1.26.50",
            "minecraft:block": {
                "description": {"identifier": name},
                "components": components or {},
            },
        })

    def item(self, name="aero:ingot", components=None, file="items/ingot.json"):
        return self.write(file, {
            "format_version": "1.26.50",
            "minecraft:item": {
                "description": {"identifier": name},
                "components": components or {},
            },
        })

    def recipe(self, body=None, kind="minecraft:recipe_shaped", file="recipes/recipe.json"):
        body = body or {
            "description": {"identifier": "aero:recipe"},
            "tags": ["crafting_table"],
            "pattern": ["I"],
            "key": {"I": {"item": "minecraft:iron_ingot"}},
            "result": {"item": "aero:machine", "count": 1},
        }
        if kind in {"minecraft:recipe_shaped", "minecraft:recipe_shapeless"}:
            body.setdefault("unlock", [{"item": "minecraft:iron_ingot"}])
        return self.write(file, {"format_version": "1.20.10", kind: body})

    def check(self, profile=None):
        return validate_content(self.root, [self.bp, self.rp], profile)

    def rules(self, result, level="error"):
        return {key.split(":", 1)[1] for key in result["checks"]["finding_counts"] if key.startswith(level + ":")}

    def test_valid_pack_with_new_block_entity_api_and_ticking_component(self):
        self.block(components={
            "minecraft:block_entity": {"container": {"slot_count": 5}, "dynamic_properties": True},
            "minecraft:tick": {"interval_range": [1, 1]},
            "minecraft:map_color": "#234567",
            "minecraft:geometry": "minecraft:geometry.full_block",
            "minecraft:material_instances": {"*": {"texture": "aero:machine"}},
            "minecraft:loot": "loot_tables/machine.json",
            "aero:machine": {},
        })
        self.write("loot_tables/machine.json", {"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "aero:machine"}]}]})
        self.write("textures/terrain_texture.json", {"texture_data": {"aero:machine": {"textures": "textures/blocks/machine"}}}, resource=True)
        self.write("textures/blocks/machine.png", "image-presence-fixture", resource=True)
        self.write("scripts/main.js", """
import {system, world} from '@minecraft/server';
system.beforeEvents.startup.subscribe(event => {
  event.blockComponentRegistry.registerCustomComponent('aero:machine', {
    onTick(event) { const dp = event.block.getComponent('minecraft:dynamic_properties'); dp?.set('energy', 3); }
  });
});
""")
        self.recipe()
        report = self.check()
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["checks"]["definitions"]["blocks"], 1)
        self.assertFalse(report["checks"]["runtime_executed"])

    def test_java_layout_and_worldgen_are_rejected(self):
        self.block(file="data/techreborn/blocks/machine.json")
        self.item(file="data/techreborn/items/ingot.json")
        self.write("data/techreborn/worldgen/configured_feature/ore.json", {
            "format_version": "1.19.80", "minecraft:configured_feature": {"feature": {"type": "minecraft:ore"}},
        })
        self.write("data/techreborn/loot_tables/a.json", {"pools": []})
        self.assertTrue({"content-location", "java-schema"} <= self.rules(self.check()))

    def test_generated_block_authoring_api_mixups(self):
        self.block(components={
            "minecraft:inventory": {"size": 5},
            "minecraft:dynamic_properties": {},
            "minecraft:map_color": "stone",
            "minecraft:loot": {"table": "loot_tables/machine.json"},
            "minecraft:custom_components": {"component_to_register": ["aero:machine"]},
            "minecraft:queued_ticking": {"interval_range": [1, 1]},
        })
        rules = self.rules(self.check())
        self.assertTrue({"block-api-component", "map-color", "block-loot", "custom-components", "deprecated-component"} <= rules)

    def test_unknown_future_components_warn_without_claiming_invalidity(self):
        self.block(components={"minecraft:future_component": {}})
        self.item(components={"minecraft:future_tool": {}})
        report = self.check()
        self.assertEqual(report["errors"], [])
        self.assertEqual(self.rules(report, "warning"), {"unreviewed-component"})

    def test_render_method_rejects_java_solid_and_accepts_all_current_choices(self):
        self.block(components={"minecraft:material_instances": {"*": {"render_method": "solid"}}})
        self.assertIn("render-method", self.rules(self.check()))
        for value in ("opaque", "double_sided", "blend", "alpha_test", "alpha_test_single_sided", "blend_to_opaque", "alpha_test_to_opaque", "alpha_test_single_sided_to_opaque"):
            with self.subTest(value=value):
                self.block(components={"minecraft:material_instances": {"*": {"render_method": value}}})
                self.assertNotIn("render-method", self.rules(self.check()))

    def test_native_block_tags_are_not_script_component_registrations(self):
        self.block(components={"tag:metal": {}})
        self.assertEqual(self.check()["warnings"], [])

    def test_mining_speed_uses_digger_component(self):
        self.item(components={"minecraft:mining_speed": 8})
        self.assertIn("item-component", self.rules(self.check()))

    def test_duplicate_ids_and_unknown_recipe_loot_feature_references(self):
        self.block(file="blocks/a.json")
        self.block(file="blocks/b.json")
        self.recipe({
            "description": {"identifier": "aero:recipe"}, "tags": ["crafting_table"],
            "pattern": ["I"], "key": {"I": {"item": "aero:missing_input"}},
            "result": {"item": "aero:missing_output"},
        })
        self.write("loot_tables/bad.json", {"pools": [{"entries": [{"type": "item", "name": "aero:missing_loot"}]}]})
        self.write("features/ore.json", {"minecraft:ore_feature": {"description": {"identifier": "aero:ore"}, "replace_rules": [{"places_block": "aero:missing_ore"}]}})
        self.write("feature_rules/ore.json", {"minecraft:feature_rules": {"description": {"identifier": "aero:rule", "places_feature": "aero:missing_feature"}}})
        report = self.check()
        self.assertIn("duplicate-id", self.rules(report))
        for value in ("missing_input", "missing_output", "missing_loot", "missing_ore", "missing_feature"):
            self.assertIn(value, "\n".join(report["errors"]))

    def test_separately_supplied_namespace_is_explicit_warning(self):
        self.recipe({"description": {"identifier": "aero:recipe"}, "tags": ["furnace"], "input": "other:ore", "output": "other:ingot"}, kind="minecraft:recipe_furnace")
        self.assertIn("unknown-reference", self.rules(self.check()))
        report = self.check({"external_namespaces": ["other"]})
        self.assertEqual(report["errors"], [])
        self.assertIn("unknown-reference", self.rules(report, "warning"))

    def test_missing_atlas_and_missing_or_wrong_case_texture(self):
        self.block(components={"minecraft:material_instances": {"*": {"texture": "aero:block/machine"}}})
        self.item(components={"minecraft:icon": "aero:item/ingot"})
        self.assertEqual(self.check()["checks"]["finding_counts"]["error:texture-reference"], 2)
        self.write("textures/item_texture.json", {"texture_data": {"aero:item/ingot": {"textures": "textures/items/Ingot"}}}, resource=True)
        self.write("textures/items/ingot.png", "fixture", resource=True)
        self.assertIn("texture-file", self.rules(self.check()))

    def test_unverified_vanilla_icon_warns_without_rejecting_reuse(self):
        self.item(components={"minecraft:icon": "iron_ingot"})
        report = self.check()
        self.assertEqual(report["errors"], [])
        self.assertIn("texture-reference", self.rules(report, "warning"))

    def test_generator_recipe_mistakes(self):
        self.recipe({
            "description": {"identifier": "aero:craft"}, "tags": ["crafting"],
            "pattern": ["I"], "key": {"I": "minecraft:iron_ingot"},
            "result": "aero:machine", "count": 4,
        })
        self.recipe({"description": {"identifier": "aero:smelt"}, "tags": ["smelting"], "input": "minecraft:iron_ore", "output": "minecraft:iron_ingot"}, kind="minecraft:recipe_smelting", file="recipes/smelt.json")
        self.assertTrue({"recipe-key", "recipe-result", "recipe-count", "recipe-tag", "java-schema"} <= self.rules(self.check()))

    def test_modern_crafting_requires_unlock_without_rejecting_legacy_or_furnace(self):
        self.block()
        path=self.recipe()
        data=json.loads(path.read_text(encoding="utf-8"))
        del data["minecraft:recipe_shaped"]["unlock"]
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("recipe-unlock", self.rules(self.check()))
        data["format_version"]="1.12"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("recipe-unlock", self.rules(self.check()))
        self.recipe({"description":{"identifier":"aero:smelt"},"tags":["furnace"],"input":"minecraft:raw_iron","output":"minecraft:iron_ingot"},kind="minecraft:recipe_furnace",file="recipes/smelt.json")
        self.assertNotIn("recipe-unlock", self.rules(self.check()))

    def test_unlock_array_requires_item_or_tag_ingredients_not_contexts(self):
        self.block()
        path = self.recipe()
        data = json.loads(path.read_text(encoding="utf-8"))
        invalid = [{"context": "AlwaysUnlocked"}, {}, "minecraft:iron_ingot", {"item": 7}, {"tag": ""}, None]
        for ingredient in invalid:
            with self.subTest(ingredient=ingredient):
                data["minecraft:recipe_shaped"]["unlock"] = [ingredient]
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("recipe-unlock", self.rules(self.check()))

    def test_unlock_accepts_ingredient_arrays_and_documented_context_objects(self):
        self.block()
        path = self.recipe()
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = [
            [{"item": "minecraft:wood", "data": 4}],
            [{"tag": "minecraft:logs"}, {"item": "minecraft:iron_ingot"}],
            *({"context": context} for context in ("AlwaysUnlocked", "PlayerInWater", "PlayerHasManyItems", "None")),
        ]
        for unlock in valid:
            with self.subTest(unlock=unlock):
                data["minecraft:recipe_shaped"]["unlock"] = unlock
                path.write_text(json.dumps(data), encoding="utf-8")
                report = self.check()
                self.assertEqual(report["errors"], [])
                self.assertEqual(report["warnings"], [])

    def test_unlock_rejects_malformed_objects_and_warns_on_unknown_context(self):
        self.block()
        path = self.recipe()
        data = json.loads(path.read_text(encoding="utf-8"))
        for unlock in (None, "AlwaysUnlocked", True, {}, {"item": "minecraft:iron_ingot"}, {"context": False}, {"context": ""}):
            with self.subTest(unlock=unlock):
                data["minecraft:recipe_shaped"]["unlock"] = unlock
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIn("recipe-unlock", self.rules(self.check()))
        data["minecraft:recipe_shaped"]["unlock"] = {"context": "FutureContext"}
        path.write_text(json.dumps(data), encoding="utf-8")
        report = self.check()
        self.assertEqual(report["errors"], [])
        self.assertIn("recipe-unlock-context", self.rules(report, "warning"))

    def test_unlock_ingredient_custom_identifiers_are_checked(self):
        self.block()
        self.recipe({
            "description": {"identifier": "aero:unlock_ref"}, "tags": ["crafting_table"],
            "ingredients": [{"item": "minecraft:iron_ingot"}], "result": {"item": "aero:machine"},
            "unlock": [{"item": "aero:missing_item"}],
        }, kind="minecraft:recipe_shapeless")
        self.assertIn("unknown-reference", self.rules(self.check()))

    def test_custom_crafting_table_can_declare_its_own_tag(self):
        self.block(components={"minecraft:crafting_table": {"crafting_tags": ["crafting"]}})
        self.recipe({"description": {"identifier": "aero:craft"}, "tags": ["crafting"], "pattern": ["I"], "key": {"I": {"item": "minecraft:iron_ingot"}}, "result": {"item": "aero:machine"}})
        self.assertNotIn("recipe-tag", self.rules(self.check()))

    def test_runtime_suppression_bad_registry_and_json_import_fail(self):
        self.write("scripts/main.js", """
import { world as gameWorld, system } from '@minecraft/server';
import data from './data.json' with {type: 'json'};
system.beforeEvents.startup.subscribe(() => {
 // @ts-ignore - exists at runtime
 const registry = gameWorld.blockComponentRegistry;
 registry.registerComponent('aero:machine', {onTick(event) {}});
});
""")
        self.write("scripts/data.json", {})
        report = self.check()
        self.assertTrue({"api-suppression", "registry-api", "script-json-import"} <= self.rules(report))

    def test_comments_strings_regex_templates_and_generator_sources_are_not_code(self):
        self.write("scripts/main.js", """
import {world} from '@minecraft/server';
// world.blockComponentRegistry.registerComponent('sample', {});
const example = "world.blockComponentRegistry";
const note = '@ts-ignore';
const template = `import value from './missing.json';`;
const pattern = /world.blockComponentRegistry/;
""")
        source = self.root / "src/gen/build.js"
        source.parent.mkdir(parents=True)
        source.write_text("import data from './definitions.json' with {type:'json'};", encoding="utf-8")
        self.assertEqual(self.check()["errors"], [])

    def test_missing_tick_for_statically_registered_handler(self):
        self.block(components={"aero:machine": {}})
        self.write("scripts/main.js", "import {system} from '@minecraft/server'; system.beforeEvents.startup.subscribe(e => e.blockComponentRegistry.registerCustomComponent('aero:machine', { onTick(e) {} }));")
        self.assertIn("missing-tick", self.rules(self.check()))

    def test_invalid_local_imports_and_node_builtin_fail(self):
        self.write("scripts/main.js", "import './missing.js'; import fs from 'node:fs'; export { x } from '../../../outside.js';")
        self.assertTrue({"script-import", "script-node-import"} <= self.rules(self.check()))

    def test_duplicate_json_keys_are_not_silently_discarded(self):
        self.write("blocks/bad.json", '{"minecraft:block":{"description":{"identifier":"aero:bad"},"components":{},"components":{}}}')
        self.assertIn("duplicate-json-key", self.rules(self.check()))

    def test_invalid_container_bounds_and_missing_loot_path(self):
        self.block(components={"minecraft:block_entity": {"container": {"slot_count": 55}}, "minecraft:loot": "../secret.json"})
        self.assertTrue({"block-container", "block-loot"} <= self.rules(self.check()))

    def test_malformed_json_and_component_values_produce_findings_not_crashes(self):
        self.write("blocks/parse.json", "{")
        self.write("blocks/bad.json", {"minecraft:block": {"description": None, "components": None, "permutations": [{"components": {"aero:x": {}}}]}})
        self.write("models/bad.json", {"minecraft:geometry": [{"description": None}]}, resource=True)
        self.assertTrue({"json", "identifier", "components"} <= self.rules(self.check()))

    def test_large_reports_preserve_total_counts_but_bound_examples(self):
        for i in range(20):
            self.block(name=f"aero:block_{i}", file=f"data/mod/blocks/{i}.json")
        report = self.check()
        self.assertEqual(report["checks"]["finding_counts"]["error:content-location"], 20)
        self.assertEqual(len(report["errors"]), 13)
        self.assertIn("8 additional", report["errors"][-1])


if __name__ == "__main__":
    unittest.main()
