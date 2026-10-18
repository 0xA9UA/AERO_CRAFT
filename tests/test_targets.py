import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from aerocraft import projects, targets
from aerocraft.common import read_json


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "addon"
        projects.create(self.project, "bedrock-stable", "sample")

    def fetch(self, url):
        key = next(key for key, value in targets.SOURCES.items() if url == value)
        data = {
            "downloads": {"result": {"links": [
                {"downloadType": "serverBedrockLinux", "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.52.3.zip"},
                {"downloadType": "serverBedrockWindows", "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-win/bedrock-server-1.26.52.3.zip"},
                {"downloadType": "serverBedrockPreviewLinux", "downloadUrl": "https://example.invalid/preview.zip"}]}},
            "samples": {"latest": {"version": "1.26.50.4"}},
            "server_api": {"version": "2.10.0"}, "server_ui_api": {"version": "2.2.0"},
        }
        return data[key], {"url": url, "sha256": "a" * 64}

    def test_stable_hotfix_and_content_baseline_are_distinct(self):
        before = (self.project / "aero-project.json").read_bytes()
        with patch.object(targets, "_fetch", side_effect=self.fetch):
            result = targets.resolve_bedrock(self.project)
        self.assertTrue(result["resolved"] and result["profile_matches_latest"])
        self.assertEqual(result["bedrock_server_version"], "1.26.52.3")
        self.assertEqual(result["content_baseline"], "1.26.50")
        self.assertEqual(before, (self.project / "aero-project.json").read_bytes())

    def test_api_mismatch_is_explicit_and_does_not_upgrade(self):
        original = self.fetch
        def newer(url):
            data, receipt = original(url)
            if url == targets.SOURCES["server_api"]:
                data["version"] = "2.11.0"
            return data, receipt
        with patch.object(targets, "_fetch", side_effect=newer):
            result = targets.resolve_bedrock(self.project)
        self.assertTrue(result["resolved"])
        self.assertFalse(result["profile_matches_latest"])
        self.assertEqual(read_json(self.project / "aero-project.json")["server_api"], "2.10.0")

    def test_metadata_failure_remains_unresolved(self):
        with patch.object(targets, "_fetch", side_effect=OSError("offline")):
            result = targets.resolve_bedrock(self.project)
        self.assertFalse(result["resolved"])
        self.assertFalse(result["profile_matches_latest"])
        self.assertIn("offline", result["error"])


if __name__ == "__main__":
    unittest.main()
