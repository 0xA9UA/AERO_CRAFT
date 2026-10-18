import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from aerocraft import bedrock, docs, inventory, porting, projects, toolchains
from aerocraft.common import ROOT, CraftError, download, extract, read_json, write_json


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, name="mod.jar", entries=None):
        p = self.root / name
        with zipfile.ZipFile(p, "w") as z:
            for k, v in (
                entries
                or {
                    "A.class": b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52),
                    "mcmod.info": "[]",
                }
            ).items():
                z.writestr(k, v)
        return p

    def project(self):
        p = self.root / "addon"
        projects.create(p, "bedrock-stable", "test_addon")
        return p

    def test_inventory_java8(self):
        r = inventory.inspect_artifact(self.archive(), True)
        self.assertEqual(r["class_java_versions"], {"8": 1})
        self.assertEqual(r["loaders"], ["forge-legacy"])
        self.assertEqual(len(r["members"]), 2)

    def test_compare(self):
        a = self.archive()
        b = self.archive("new.jar", {"A.class": b"changed", "new.json": "{}"})
        r = inventory.compare(a, b)
        self.assertEqual(r["changed"], ["A.class"])
        self.assertEqual(r["added"], ["new.json"])
        self.assertEqual(r["removed"], ["mcmod.info"])

    def test_nested_mcaddon_inventory(self):
        p = self.project()
        r = bedrock.package(p)
        info = inventory.inspect_artifact(r["artifact"])
        self.assertEqual(len(info["nested_packs"]), 2)
        self.assertIn("bedrock", info["loaders"])

    def test_zip_traversal_rejected(self):
        for name in ["../escape", "/escape", "C:/escape", "..\\escape"]:
            with self.subTest(name=name):
                a = self.archive(entries={name: "bad"})
                with self.assertRaises(CraftError):
                    extract(a, self.root / "out")
                self.assertFalse((self.root / "out").exists())

    def test_case_collision_rejected(self):
        a = self.archive(entries={"x": "a", "X": "b"})
        with self.assertRaises(CraftError):
            inventory.inspect_artifact(a)

    def test_zip_symlink_rejected(self):
        a = self.root / "link.zip"
        with zipfile.ZipFile(a, "w") as z:
            i = zipfile.ZipInfo("link")
            i.external_attr = 0o120777 << 16
            z.writestr(i, "outside")
        with self.assertRaises(CraftError):
            extract(a, self.root / "out")

    def test_tar_escaping_link_rejected(self):
        a = self.root / "bad.tar.gz"
        with tarfile.open(a, "w:gz") as t:
            m = tarfile.TarInfo("link")
            m.type = tarfile.SYMTYPE
            m.linkname = "../outside"
            t.addfile(m)
        with self.assertRaises(CraftError):
            extract(a, self.root / "out")

    def test_extract_does_not_overwrite(self):
        out = self.root / "existing"
        out.mkdir()
        (out / "keep").write_text("yes")
        with self.assertRaises(CraftError):
            extract(self.archive(), out)
        self.assertEqual((out / "keep").read_text(), "yes")

    def test_verified_download(self):
        class Response(io.BytesIO):
            url = "https://example.com/payload"

        destination = self.root / "cache"
        digest = hashlib.sha256(b"payload").hexdigest()
        with patch("urllib.request.urlopen", return_value=Response(b"payload")):
            download("https://example.com/a", destination, digest)
        self.assertEqual(destination.read_bytes(), b"payload")
        with patch(
            "urllib.request.urlopen", side_effect=AssertionError("must use cache")
        ):
            download("https://example.com/a", destination, digest)

    def test_bad_digest_preserves_existing(self):
        class Response(io.BytesIO):
            url = "https://example.com/payload"

        destination = self.root / "cache"
        destination.write_bytes(b"old")
        with patch("urllib.request.urlopen", return_value=Response(b"new")):
            with self.assertRaises(CraftError):
                download("https://example.com/a", destination, "0" * 64)
        self.assertEqual(destination.read_bytes(), b"old")

    def test_project_refuses_existing(self):
        p = self.project()
        with self.assertRaises(CraftError):
            projects.create(p, "bedrock-stable", "test_addon")

    def test_project_id_injection_rejected(self):
        for mid in ["../bad", "bad';run()", "Upper", "x"]:
            with self.subTest(mid=mid), self.assertRaises(CraftError):
                projects.create(self.root / "bad", "bedrock-stable", mid)

    def test_starter_validation(self):
        self.assertTrue(bedrock.validate(self.project())["passed"])

    def test_missing_script_fails(self):
        p = self.project()
        (p / "packs/behavior/scripts/main.js").unlink()
        self.assertFalse(bedrock.validate(p)["passed"])

    def test_wrong_pack_dependency_fails(self):
        p = self.project()
        manifest = p / "packs/behavior/manifest.json"
        d = read_json(manifest)
        d["dependencies"][0]["version"] = [9, 9, 9]
        write_json(manifest, d)
        self.assertFalse(bedrock.validate(p)["passed"])

    def test_duplicate_uuid_fails(self):
        p = self.project()
        manifest = p / "packs/behavior/manifest.json"
        d = read_json(manifest)
        d["modules"][0]["uuid"] = d["header"]["uuid"]
        write_json(manifest, d)
        self.assertFalse(bedrock.validate(p)["passed"])

    def test_invalid_json_fails(self):
        p = self.project()
        (p / "packs/resource/bad.json").write_text("{bad")
        self.assertFalse(bedrock.validate(p)["passed"])

    def test_missing_pack_fails(self):
        self.assertFalse(bedrock.validate(self.root)["passed"])

    def test_deterministic_addon(self):
        p = self.project()
        a = bedrock.package(p)
        b = bedrock.package(p)
        self.assertEqual(a["sha256"], b["sha256"])
        with zipfile.ZipFile(a["artifact"]) as z:
            self.assertEqual(
                sorted(z.namelist()), ["behavior.mcpack", "resource.mcpack"]
            )
            self.assertEqual(z.infolist()[0].date_time, (1980, 1, 1, 0, 0, 0))

    def test_pack_rejects_unexpected_files(self):
        p = self.project()
        (p / "packs/behavior/.env").write_text("secret")
        with self.assertRaises(CraftError):
            bedrock.package(p)

    def test_failed_package_keeps_previous_artifact(self):
        p = self.project()
        before = bedrock.package(p)
        artifact = Path(before["artifact"])
        data = artifact.read_bytes()
        (p / "packs/behavior/bad.secret").write_text("do not publish")
        with self.assertRaises(CraftError):
            bedrock.package(p)
        self.assertEqual(artifact.read_bytes(), data)

    def test_malformed_manifest_dependencies(self):
        p = self.project()
        manifest = p / "packs/behavior/manifest.json"
        data = read_json(manifest)
        data["dependencies"] = ["bad"]
        write_json(manifest, data)
        self.assertFalse(bedrock.validate(p)["passed"])

    def test_non_object_recipe_rejected(self):
        with self.assertRaises(CraftError):
            porting.convert_recipe([], "java-to-bedrock", "example:r")

    def test_external_wrong_jdk_is_rejected(self):
        home = self.root / "jdk"
        (home / "bin").mkdir(parents=True)
        for name in ["java", "javac"]:
            (home / "bin" / (name + ".exe" if os.name == "nt" else name)).write_text("")
        (home / "release").write_text('JAVA_VERSION="17.0.1"')
        with patch.dict(os.environ, {"AERO_JAVA_21_HOME": str(home)}):
            with self.assertRaises(CraftError):
                toolchains.java_home(21)

    def test_project_skips_cache_and_symlinks(self):
        p = self.project()
        (p / "node_modules").mkdir()
        (p / "node_modules/private.json").write_text("{}")
        info = inventory.inspect_project(p)
        self.assertFalse(
            any("node_modules" in s for s in info["examples"].get(".json", []))
        )

    def test_plan_retains_source_identity(self):
        p = self.archive()
        out = self.root / "plan"
        r = porting.plan(p, "fabric", out, "1.21.1")
        data = read_json(out / "port-plan.json")
        self.assertEqual(data["target"]["jdk"], 21)
        self.assertEqual(
            data["source"]["sha256"], inventory.inspect_artifact(p)["sha256"]
        )
        self.assertTrue(all(f["status"] == "unassessed" for f in data["features"]))

    def test_recipe_roundtrip(self):
        recipe = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["AA"],
            "key": {"A": {"item": "example:copper"}},
            "result": {"id": "example:wire", "count": 2},
        }
        b = porting.convert_recipe(
            recipe,
            "java-to-bedrock",
            "example:wire",
            {"example:copper": "port:copper", "example:wire": "port:wire"},
        )
        j = porting.convert_recipe(
            b,
            "bedrock-to-java",
            "example:wire",
            {"port:copper": "example:copper", "port:wire": "example:wire"},
        )
        self.assertEqual(recipe, j)

    def test_shapeless_conversion(self):
        recipe = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:stone"}],
            "result": {"item": "minecraft:cobblestone"},
        }
        r = porting.convert_recipe(recipe, "java-to-bedrock", "example:stone")
        self.assertIn("minecraft:recipe_shapeless", r)

    def test_recipe_does_not_guess_custom_ids(self):
        r = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "example:input"}],
            "result": {"item": "minecraft:stone"},
        }
        with self.assertRaises(CraftError):
            porting.convert_recipe(r, "java-to-bedrock", "example:r")

    def test_recipe_rejects_tags_nbt_conditions(self):
        base = {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minecraft:stone"}],
            "result": {"item": "minecraft:cobblestone"},
        }
        for recipe in [
            {**base, "ingredients": [{"tag": "forge:stones"}]},
            {**base, "conditions": [{}]},
            {**base, "result": {"item": "minecraft:stone", "nbt": "{}"}},
        ]:
            with self.subTest(recipe=recipe), self.assertRaises(CraftError):
                porting.convert_recipe(recipe, "java-to-bedrock", "example:r")

    def test_recipe_rejects_invalid_grid(self):
        for pattern in [["AB"], ["A", "AA"], ["    "]]:
            with self.subTest(pattern=pattern), self.assertRaises(CraftError):
                porting.convert_recipe(
                    {
                        "type": "minecraft:crafting_shaped",
                        "pattern": pattern,
                        "key": {"A": {"item": "minecraft:stone"}},
                        "result": {"item": "minecraft:stone"},
                    },
                    "java-to-bedrock",
                    "example:r",
                )

    def test_recipe_rejects_station_priority(self):
        r = {
            "format_version": "1.20.10",
            "minecraft:recipe_shapeless": {
                "tags": ["stonecutter"],
                "ingredients": [{"item": "minecraft:stone"}],
                "result": {"item": "minecraft:stone"},
            },
        }
        with self.assertRaises(CraftError):
            porting.convert_recipe(r, "bedrock-to-java", "example:r")

    def test_docs_search_and_local_read(self):
        self.assertTrue(docs.search("persistence"))
        self.assertIn("Java", docs.read("guide:workflows/java.md")["text"])
        with self.assertRaises(CraftError):
            docs.read("guide:../../package.json")

    def test_platform_matrix(self):
        for osname, arch, expected in [
            ("Windows", "AMD64", "windows-x64"),
            ("Darwin", "arm64", "darwin-arm64"),
            ("Linux", "aarch64", "linux-arm64"),
        ]:
            with patch("platform.system", return_value=osname), patch(
                "platform.machine", return_value=arch
            ):
                self.assertEqual(toolchains.host_key(), expected)

    def test_mcp_protocol_and_workspace_boundary(self):
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "inspect_project",
                    "arguments": {"path": str(self.root.parent)},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_profiles", "arguments": {}},
            },
            {"jsonrpc": "2.0", "id": 5, "method": "server/discover"},
        ]
        proc = subprocess.run(
            [sys.executable, ROOT / "aero.py", "mcp", "--workspace", self.root],
            input="".join(json.dumps(r) + "\n" for r in requests),
            text=True,
            capture_output=True,
            check=True,
        )
        replies = [json.loads(x) for x in proc.stdout.splitlines()]
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertTrue({"start_port", "verify_project", "port_status", "discover_runtimes", "decompile_artifact", "cache_docs"}.issubset(names))
        self.assertTrue(replies[2]["result"]["isError"])
        self.assertNotIn("isError", replies[3]["result"])
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_mcp_unicode_resource_with_legacy_pipe_encoding(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "aerocraft://docs/workflows/porting.md"},
        }
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, ROOT / "aero.py", "mcp", "--workspace", self.root],
            input=json.dumps(request) + "\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            env=env,
        )
        result = json.loads(proc.stdout)
        self.assertIn("Java ↔ Bedrock", result["result"]["contents"][0]["text"])

    def test_cli_failed_validation_exit_code(self):
        p = subprocess.run(
            [sys.executable, ROOT / "aero.py", "validate", self.root],
            capture_output=True,
        )
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main()
