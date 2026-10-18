"""Release-gate regressions; all receipts below are isolated synthetic fixtures.

These tests do not claim engine or client observations. Tests of build_checks run
real Node test files, with dependency installation and the compiler fixture local.
"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from aerocraft import bedrock, porting, verification
from aerocraft.common import ROOT, CraftError, read_json, sha256, write_json


class VerificationGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "synthetic-source.jar"
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("example/Mod.class", b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 61))
            archive.writestr("fabric.mod.json", json.dumps({"id": "fixture", "version": "1.0.0"}))
        self.project = self.root / "port"
        verification.start_port(self.source, self.project, "fixture_port")
        self.contract = read_json(self.project / "aero-port.json")
        for feature in self.contract["features"]:
            feature.update(status="verified", source_evidence=["example/Mod.class#fixture"],
                           target_implementation=["packs/behavior/scripts/simulation.js"],
                           tests=["fixture mechanics"], native_assertions=["fixture round trip"])
        write_json(self.project / "aero-port.json", self.contract)
        package = bedrock.package(self.project)
        self.artifact = Path(package["artifact"])
        # This is deliberately labelled synthetic and never escapes this tempdir.
        evidence = self.project / ".aero/client/fixture.txt"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("Synthetic unit-test receipt, not an observed client run.", encoding="utf-8")
        self.client = {
            "artifact_sha256": sha256(self.artifact), "platform": "android",
            "observed": True, "observer": "synthetic unit-test fixture",
            "minecraft_version": self.contract["target"]["minecraft"],
            "passed_checks": ["import", "activation", "visible_content", "textures", "interaction", "restart"],
            "evidence": [".aero/client/fixture.txt"],
        }
        write_json(self.project / ".aero/client-evidence.json", self.client)
        self.report = {
            "schema_version": 1, "passed": True, "inputs": verification.fingerprint(self.project),
            "artifact": {"path": self.artifact.relative_to(self.project).as_posix(), "sha256": sha256(self.artifact)},
            "layers": {name: {"passed": True} for name in ("static", "api", "unit", "build", "native")},
        }
        self.report["layers"]["unit"]["passed_tests"] = ["fixture mechanics"]
        self.report["layers"]["build"]["deterministic"] = True
        self.report["layers"]["native"].update(
            observed_boots=[1, 2], scenario={"assertions": [{"name": "fixture round trip", "passed": True}]})
        self.save_report()

    def tearDown(self):
        self.temporary.cleanup()

    def save_report(self, refresh_inputs=False):
        if refresh_inputs:
            self.report["inputs"] = verification.fingerprint(self.project)
        write_json(self.project / ".aero/verification/latest.json", self.report)

    def save_contract(self):
        write_json(self.project / "aero-port.json", self.contract)
        self.save_report(refresh_inputs=True)

    def denied(self, phrase=None):
        verdict = verification.gate(self.project)
        self.assertIs(verdict["ready"], False)
        self.assertIs(verdict["passed"], False)
        if phrase:
            self.assertIn(phrase, "\n".join(verdict["blockers"]))
        return verdict

    def test_ready_fixture_is_read_only_and_returns_exact_artifact_identity(self):
        before = {p.relative_to(self.project): p.read_bytes()
                  for p in self.project.rglob("*") if p.is_file()}
        verdict = verification.gate(self.project)
        self.assertIs(verdict["ready"], True, verdict["blockers"])
        self.assertEqual(verdict["artifact"], {"path": str(self.artifact), "sha256": sha256(self.artifact)})
        after = {p.relative_to(self.project): p.read_bytes()
                 for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_report_and_contract_do_not_pass(self):
        (self.project / ".aero/verification/latest.json").unlink()
        self.denied("missing or stale")
        (self.project / "aero-port.json").unlink()
        self.denied("No aero-port.json")

    def test_pack_generator_test_and_configuration_edits_invalidate_receipt(self):
        for relative in ("packs/behavior/scripts/simulation.js", "src/generator.js",
                         "tests/new.test.mjs", "package.json", "tsconfig.json", "aero-port.json"):
            with self.subTest(relative=relative):
                target = self.project / relative
                old = target.read_bytes() if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.suffix == ".json":
                    data = read_json(target)
                    data["fixture_change"] = True
                    write_json(target, data)
                else:
                    target.write_bytes((old or b"") + b"\n// changed verification input\n")
                self.denied("missing or stale")
                if old is None:
                    target.unlink()
                else:
                    target.write_bytes(old)
                self.assertTrue(verification.gate(self.project)["ready"])

    def test_source_bytes_and_artifact_bytes_are_independently_bound(self):
        with self.source.open("ab") as handle:
            handle.write(b"changed")
        self.assertIs(self.denied("source artifact").get("candidate_ready"), False)
        self.source.write_bytes(self.source.read_bytes()[:-7])
        self.artifact.write_bytes(self.artifact.read_bytes() + b"changed")
        self.denied("hash-bound addon")

    def test_malformed_saved_evidence_returns_not_ready_instead_of_accepting_it(self):
        path = self.project / ".aero/verification/latest.json"
        for text in ("not JSON", "null", "[]", '{"passed": true, "layers": []}'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                self.denied()
        self.save_report()
        for field, value in (("features", None), ("features", [None]), ("acceptance", [])):
            with self.subTest(field=field, value=value):
                contract = {**self.contract, field: value}
                write_json(self.project / "aero-port.json", contract)
                self.save_report(refresh_inputs=True)
                self.denied()

    def test_symlink_inputs_cannot_escape_verification_fingerprint(self):
        outside = self.root / "outside.test.mjs"
        outside.write_text("// external mutable test fixture\n", encoding="utf-8")
        link = self.project / "tests/linked.test.mjs"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this host")
        self.denied()

    def test_failed_missing_or_string_pass_layers_fail_closed(self):
        for layer in ("static", "api", "unit", "build", "native"):
            previous = deepcopy(self.report["layers"][layer])
            for value in (False, "true", None):
                with self.subTest(layer=layer, value=value):
                    self.report["layers"][layer]["passed"] = value
                    self.save_report()
                    self.denied(f"Required {layer}")
            self.report["layers"][layer] = previous
        self.report["layers"].pop("native")
        self.save_report()
        self.denied("Required native")

    def test_failed_overall_receipt_cannot_release_even_when_layers_claim_pass(self):
        self.report["passed"] = False
        self.report["failure"] = "Inputs changed during the observed verification run."
        self.save_report()
        self.denied()

    def test_deterministic_build_evidence_is_required(self):
        self.report["layers"]["build"]["deterministic"] = False
        self.save_report()
        self.denied()

    def test_required_feature_cannot_be_removed_or_marked_optional(self):
        self.contract["features"].pop()
        self.save_contract()
        self.denied("was removed")
        self.contract["features"][0]["required"] = False
        self.save_contract()
        self.denied("removing required scope")

    def test_required_feature_must_have_implementation_evidence_and_passing_tests(self):
        feature = self.contract["features"][0]
        for field, value, phrase in (
            ("status", "unassessed", "status is unassessed"),
            ("source_evidence", ["invented/Member.class"], "actual source archive members"),
            ("target_implementation", ["missing.js"], "existing project files"),
            ("target_implementation", [str(self.source)], "existing project files"),
            ("tests", ["unexecuted test"], "unit tests did not pass"),
            ("native_assertions", ["unobserved assertion"], "native scenario assertions did not pass"),
        ):
            with self.subTest(field=field, value=value):
                old = feature[field]
                feature[field] = value
                self.save_contract()
                self.denied(phrase)
                feature[field] = old
        feature.update(tests=[], native_assertions=[])
        self.save_contract()
        self.denied("no executable acceptance test")

    def test_adaptation_requires_explanation(self):
        self.contract["features"][0].update(status="adapted", adaptation="  ")
        self.save_contract()
        self.denied("describe the target adaptation")

    def test_starter_only_tests_are_not_port_evidence(self):
        starter = "energy caps without mutating the saved state"
        for feature in self.contract["features"]:
            feature["tests"] = [starter]
        self.report["layers"]["unit"]["passed_tests"] = [starter]
        self.save_contract()
        self.denied("unchanged starter test")

    def test_native_boot_success_does_not_replace_scenario_assertions(self):
        self.report["layers"]["native"]["scenario"] = {"assertions": []}
        self.save_report()
        self.denied("generic boot checks are insufficient")
        self.report["layers"]["native"]["scenario"]["assertions"] = [
            {"name": "fixture round trip", "passed": False}]
        self.save_report()
        self.denied("native scenario assertions did not pass")

    def test_acceptance_scope_cannot_disable_native_or_client_requirements(self):
        for field in ("native_scenario_required", "connected_client_required"):
            with self.subTest(field=field):
                self.contract["acceptance"][field] = False
                self.save_contract()
                self.denied()
                self.contract["acceptance"][field] = True

    def test_latest_target_needs_resolved_matching_profile(self):
        self.contract["target"]["requested_latest"] = True
        for resolution in (None, {"resolved": False}, {"resolved": True},
                           {"resolved": True, "checked_at": "2026-10-18", "profile_matches_latest": False}):
            with self.subTest(resolution=resolution):
                self.contract["target"]["resolution"] = resolution
                self.save_contract()
                self.denied()
        self.contract["target"]["resolution"] = {
            "resolved": True, "checked_at": "2026-10-18", "profile_matches_latest": True}
        self.save_contract()
        self.assertTrue(verification.gate(self.project)["ready"])

    def test_client_evidence_is_bound_to_artifact_platform_and_observations(self):
        for field, value in (("artifact_sha256", "0" * 64), ("platform", "windows"),
                             ("observed", False), ("observer", ""), ("minecraft_version", ""),
                             ("minecraft_version", "0.0.1"),
                             ("passed_checks", ["import", "activation"]),
                             ("evidence", ["missing.png"]), ("evidence", [str(self.source)])):
            with self.subTest(field=field):
                client = {**self.client, field: value}
                write_json(self.project / ".aero/client-evidence.json", client)
                self.denied()

    def test_test_candidate_can_remain_incomplete_without_false_release_claim(self):
        (self.project / ".aero/client-evidence.json").unlink()
        self.contract["features"][0]["status"] = "unassessed"
        self.save_contract()
        verdict = self.denied()
        self.assertIs(verdict.get("candidate_ready"), True)
        self.artifact.write_bytes(b"not the verified candidate")
        self.assertIs(self.denied().get("candidate_ready"), False)


class DirectBuildChecksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        managed_node = ROOT / ".runtime/tools/node/bin/node"
        self.node = str(managed_node) if managed_node.is_file() else shutil.which("node")
        if not self.node:
            self.temporary.cleanup()
            self.skipTest("Node is not installed")
        self.project = self.root / "project"
        (self.project / "tests").mkdir(parents=True)
        (self.project / "packs/behavior/scripts").mkdir(parents=True)
        self.output = self.root / "results"
        config = {"server_api": "2.10.0", "server_ui_api": "2.2.0", "typescript": "7.0.2"}
        write_json(self.project / "aero-project.json", config)
        write_json(self.project / "package.json", {"type": "module", "scripts": {
            "test": "node -e 'process.exit(0)'", "typecheck": "node -e 'process.exit(0)'"}})
        write_json(self.project / "tsconfig.json", {"compilerOptions": {"checkJs": False}, "include": []})
        for package, version in (("@minecraft/server", "2.10.0"),
                                 ("@minecraft/server-ui", "2.2.0"), ("typescript", "7.0.2")):
            write_json(self.project / "node_modules" / package / "package.json", {"version": version})
        self.compiler = self.project / "node_modules/typescript/bin/tsc"
        self.compiler.parent.mkdir(parents=True)
        self.compiler.write_text("console.log('synthetic compiler fixture');\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def checks(self):
        with patch.object(verification.toolchains, "npm") as npm, \
             patch.object(verification.toolchains, "node", return_value=Path(self.node)):
            result = verification.build_checks(self.project, self.output)
        self.assertEqual(npm.call_args.args[0], ["ci", "--no-audit", "--no-fund"])
        return result

    def test_empty_test_directory_and_empty_test_file_cannot_pass(self):
        self.assertFalse(self.checks()["unit"]["passed"])
        (self.project / "tests/empty.test.mjs").write_text("// No tests.\n", encoding="utf-8")
        self.assertFalse(self.checks()["unit"]["passed"])

    def test_real_test_failure_cannot_be_hidden_by_successful_npm_alias(self):
        (self.project / "tests/machine.test.mjs").write_text(
            "import test from 'node:test'; import assert from 'node:assert/strict';\n"
            "test('machine conservation', () => assert.equal(2, 3));\n", encoding="utf-8")
        result = self.checks()
        self.assertFalse(result["unit"]["passed"])
        self.assertNotIn("machine conservation", result["unit"]["passed_tests"])

    def test_direct_test_names_and_forced_typecheck_ignore_project_script_shortcuts(self):
        (self.project / "tests/machine.test.mjs").write_text(
            "import test from 'node:test'; import assert from 'node:assert/strict';\n"
            "test('machine conservation', () => assert.equal(2, 2));\n", encoding="utf-8")
        result = self.checks()
        self.assertTrue(result["unit"]["passed"])
        self.assertIn("machine conservation", result["unit"]["passed_tests"])
        forced = read_json(self.output / "tsconfig.json")
        self.assertIs(forced["compilerOptions"]["checkJs"], True)
        self.assertIs(forced["compilerOptions"]["strict"], True)
        self.assertIn((self.project / "packs/**/*.js").as_posix(), forced["include"])
        self.compiler.write_text("process.exit(9);\n", encoding="utf-8")
        self.assertFalse(self.checks()["api"]["passed"])

    def test_dependency_version_drift_is_rejected(self):
        write_json(self.project / "node_modules/@minecraft/server/package.json", {"version": "0.0.1"})
        with self.assertRaisesRegex(CraftError, "does not match"):
            self.checks()


if __name__ == "__main__":
    unittest.main()
