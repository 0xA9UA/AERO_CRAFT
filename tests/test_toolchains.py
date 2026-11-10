"""Managed runtime upgrades preserve the previous installation on failure."""

import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from aerocraft import toolchains
from aerocraft.common import CraftError, read_json, write_json


class DownloadResponse(io.BytesIO):
    url = "https://example.com/node.zip"


class ToolchainUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.destination = self.runtime / "tools/node"
        self.relative_binary = Path("node.exe" if os.name == "nt" else "bin/node")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("node-new/" + self.relative_binary.as_posix(), "new runtime")
        self.payload = stream.getvalue()
        self.row = {"version": "24.22.1", "url": "https://example.com/node.zip",
                    "sha256": hashlib.sha256(self.payload).hexdigest(), "archive": "zip"}
        self.binary = self.destination / self.relative_binary
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text("old runtime", encoding="utf-8")
        write_json(self.destination / "aero-install.json", {**self.row, "version": "24.22.0", "sha256": "0" * 64})
        for patcher in (patch.object(toolchains, "RUNTIME", self.runtime),
                        patch.object(toolchains, "spec", return_value=self.row),
                        patch("urllib.request.urlopen", side_effect=lambda *a, **kw: DownloadResponse(self.payload))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_ensure_node_upgrades_existing_binary_and_retains_backup(self):
        self.assertEqual(toolchains.node(ensure=True), self.binary)
        self.assertEqual(self.binary.read_text(), "new runtime")
        self.assertEqual(read_json(self.destination / "aero-install.json"), self.row)
        backups = list((self.runtime / "tool-backups").glob("*/node"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / self.relative_binary).read_text(), "old runtime")
        toolchains.node(ensure=True)
        self.assertEqual(len(list((self.runtime / "tool-backups").iterdir())), 1)

    def test_failed_download_preserves_existing_runtime(self):
        with patch("urllib.request.urlopen", return_value=DownloadResponse(b"wrong checksum")):
            with self.assertRaises(CraftError):
                toolchains.node(ensure=True)
        self.assertEqual(self.binary.read_text(), "old runtime")
        self.assertFalse(self.destination.with_suffix(".installing").exists())

    def test_failed_publication_restores_runtime_and_can_be_retried(self):
        rename = Path.rename

        def fail_publication(path, target):
            if path.name == "node-new":
                raise OSError("publication failed")
            return rename(path, target)

        with patch.object(Path, "rename", fail_publication):
            with self.assertRaisesRegex(OSError, "publication failed"):
                toolchains.node(ensure=True)
        self.assertEqual(self.binary.read_text(), "old runtime")
        self.assertFalse(self.destination.with_suffix(".installing").exists())
        toolchains.node(ensure=True)
        self.assertEqual(self.binary.read_text(), "new runtime")

    def test_unmanaged_runtime_is_preserved(self):
        (self.destination / "aero-install.json").unlink()
        with self.assertRaisesRegex(CraftError, "no managed installation receipt"):
            toolchains.node(ensure=True)
        self.assertEqual(self.binary.read_text(), "old runtime")

    def test_concurrent_upgrade_is_refused(self):
        self.destination.with_suffix(".installing").mkdir()
        with self.assertRaisesRegex(CraftError, "Install already in progress"):
            toolchains.node(ensure=True)
        self.assertEqual(self.binary.read_text(), "old runtime")
