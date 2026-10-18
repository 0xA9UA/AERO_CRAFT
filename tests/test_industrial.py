from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from aerocraft.bedrock_checks import validate_content
from aerocraft.common import CraftError, ROOT, read_json
from aerocraft.industrial import create


class IndustrialExampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "industrial"

    def tearDown(self):
        self.temp.cleanup()

    def test_new_reference_is_content_valid_and_pins_ui_dependency(self):
        result = create(self.path, "sample_factory")
        report = validate_content(self.path, [self.path / "packs/behavior", self.path / "packs/resource"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["checks"]["definitions"]["blocks"], 3)
        self.assertEqual(report["checks"]["definitions"]["recipes"], 3)
        manifest = read_json(self.path / "packs/behavior/manifest.json")
        self.assertIn({"module_name": "@minecraft/server-ui", "version": result["config"]["server_ui_api"]}, manifest["dependencies"])
        self.assertFalse(result["reference"]["tested"])
        for image in (self.path / "packs/resource/textures/blocks").glob("*.png"):
            self.assertTrue(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        for script in (self.path / "packs/behavior/scripts").glob("*.js"):
            self.assertNotIn("__MOD_ID__", script.read_text(encoding="utf-8"))

    def test_existing_project_is_never_overwritten(self):
        self.path.mkdir()
        marker = self.path / "user.txt"
        marker.write_text("keep me", encoding="utf-8")
        with self.assertRaises(CraftError):
            create(self.path, "sample_factory")
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep me")
        self.assertFalse((self.path / "packs").exists())

    def test_coordinate_persisted_machines_are_immovable(self):
        create(self.path, "sample_factory")
        for kind in ("generator", "electric_furnace", "cable"):
            block=read_json(self.path / f"packs/behavior/blocks/{kind}.json")
            self.assertEqual(block["minecraft:block"]["components"]["minecraft:movable"], {"movement_type":"immovable"})

    def test_pure_mechanics_tests_execute_without_bedrock_or_npm_install(self):
        managed = ROOT / ".runtime/tools/node/bin/node"
        node = str(managed) if managed.is_file() else shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable; Python generation checks still run")
        create(self.path, "sample_factory")
        result = subprocess.run([node, "--test", "tests/simulation.test.mjs"], cwd=self.path, text=True, encoding="utf-8", capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass 7", result.stdout)


if __name__ == "__main__":
    unittest.main()
