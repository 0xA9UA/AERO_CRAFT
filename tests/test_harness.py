"""Harness policy tests exercise real child-process gates without a model server."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from aerocraft import harness
from aerocraft.common import ROOT, CraftError


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def bundle(self):
        source = self.root / "node_modules/rea-agents/skills/reverse-engineer-anything"
        (source / "references").mkdir(parents=True)
        (source / "SKILL.md").write_text("pinned skill", encoding="utf-8")
        (source / "references/guide.md").write_text("reference", encoding="utf-8")
        (source / "private.key").write_text("not an instruction", encoding="utf-8")
        return source

    def test_bundled_skill_copies_only_instructions_and_preserves_user_edits(self):
        self.bundle()
        home = self.root / "dsh"
        with patch.object(harness, "ROOT", self.root):
            harness.install_bundled_skills(home)
            dest = home / "skills/reverse-engineer-anything"
            self.assertEqual((dest / "references/guide.md").read_text(), "reference")
            self.assertFalse((dest / "private.key").exists())
            (dest / "SKILL.md").write_text("user skill", encoding="utf-8")
            harness.install_bundled_skills(home)
            self.assertEqual((dest / "SKILL.md").read_text(), "user skill")

    def test_missing_skill_fails_setup_instead_of_advertising_it(self):
        with patch.object(harness, "ROOT", self.root):
            with self.assertRaisesRegex(CraftError, "REA skill is missing"):
                harness.install_bundled_skills(self.root / "dsh")

    def test_prepare_injects_policy_and_preserves_saved_provider_settings(self):
        self.bundle()
        runtime = self.root / "runtime"
        home = runtime / "dsh"
        home.mkdir(parents=True)
        saved = home / "profiles/web/cordis.patch.yml"
        saved.parent.mkdir(parents=True)
        saved.write_text("saved provider settings", encoding="utf-8")
        entry = self.root / "node_modules/@deepseek-ai/dsh/lib/bin.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("", encoding="utf-8")
        with patch.object(harness, "ROOT", self.root), \
             patch.object(harness, "RUNTIME", runtime), \
             patch.object(harness, "environment", return_value={"PATH": "test-path"}), \
             patch.object(harness, "node", return_value=Path(sys.executable)), \
             patch.object(harness, "java_home", side_effect=CraftError("not installed")):
            _, overlay, env = harness.prepare(self.root)
        rows = json.loads(overlay.read_text())[0]["insert"]
        policy = next(row for row in rows if row["id"] == "aero-craft-policy")
        self.assertEqual(policy["name"], (self.root / "plugins/aero-policy.mjs").as_uri())
        self.assertEqual(policy["config"]["python"], sys.executable)
        self.assertEqual(policy["config"]["workspace"], str(self.root))
        self.assertEqual(env["DSH_HOME"], str(home))
        self.assertEqual(saved.read_text(), "saved provider settings")
        self.assertEqual({row["id"] for row in rows},
                         {"aero-craft-policy", "aero-craft-mcp", "aero-rea-mcp"})
        bridge = next(row for row in rows if row["id"] == "aero-craft-mcp")
        self.assertGreaterEqual(bridge["config"]["toolCallTimeoutMs"], 600000)

    def test_policy_runs_gate_and_retains_session_targets_across_restart(self):
        managed_node = ROOT / ".runtime/tools/node/bin/node"
        executable = str(managed_node) if managed_node.is_file() else shutil.which("node")
        if not executable:
            self.skipTest("Node is not installed")
        cli = self.root / "fake gate.py"
        cli.write_text(textwrap.dedent("""\
            import json
            from pathlib import Path
            import sys
            assert sys.argv[1] == 'gate' and sys.argv[3] == '--json'
            project = Path(sys.argv[2])
            state = json.loads((project / '.gate.json').read_text())
            if state.get('invalid'):
                print('not JSON')
            else:
                print(json.dumps(state))
            raise SystemExit(state.get('exit', 0))
            """), encoding="utf-8")
        config = {
            "python": sys.executable,
            "cli": str(cli),
            "workspace": str(self.root),
            "stateDirectory": str(self.root / "policy-state"),
            "guide": str(self.root / "workflow.md"),
        }
        (self.root / "workflow.md").write_text("Acceptance workflow", encoding="utf-8")
        script = self.root / "exercise.mjs"
        script.write_text(textwrap.dedent("""\
            import assert from 'node:assert/strict';
            import { createHash } from 'node:crypto';
            import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
            import { join } from 'node:path';
            const { createPolicy, apply } = await import(process.argv[2]);
            const config = JSON.parse(process.argv[3]);
            const root = config.workspace;
            function project(name, state = {ready: false, blockers: ['machine test missing'], exit: 1}) {
              const path = join(root, name);
              mkdirSync(join(path, 'dist'), {recursive: true});
              writeFileSync(join(path, 'aero-project.json'), '{}');
              writeFileSync(join(path, 'aero-port.json'), '{}');
              writeFileSync(join(path, '.gate.json'), JSON.stringify(state));
              writeFileSync(join(path, 'dist', 'test.mcaddon'), 'artifact');
              return path;
            }
            function call(name, args = {}, session = 's1', cwd = root) {
              return {name, arguments: args, agent: {session: {header: {id: session, cwd}}},
                signal: new AbortController().signal};
            }
            let delegated = 0;
            const next = async () => { delegated++; return {kind: 'allow'}; };
            let policy = createPolicy(config);
            const bad = project('port with spaces; safe');
            const complete = call('update_goal', {action: 'complete'});
            assert.equal((await policy.before(complete, next)).kind, 'allow', 'unrelated goals are unchanged');
            policy.observe(call('mcp__aerocraft__start_port', {path: bad}), {isError: true});
            assert.equal((await policy.before(complete, next)).kind, 'allow', 'failed starts are not registered');
            policy.observe(call('mcp__aerocraft__start_port', {path: bad}), {isError: false, value: {}});
            let result = await policy.before(complete, next);
            assert.equal(result.kind, 'deny');
            assert.match(result.reason, /machine test missing/);
            policy = createPolicy(config); // Simulated harness process restart.
            assert.equal((await policy.before(complete, next)).kind, 'deny', 'target persists');
            assert.equal((await policy.before(call('update_goal', {action: 'complete'}, 'other'), next)).kind,
              'allow', 'session projects remain isolated');
            assert.equal((await policy.before(call('update_goal', {action: 'pause'}), next)).kind, 'allow');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: false, exit: 0}));
            assert.equal((await policy.before(complete, next)).kind, 'deny', 'exit zero alone is insufficient');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: true, exit: 1}));
            assert.equal((await policy.before(complete, next)).kind, 'deny', 'nonzero status fails closed');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({invalid: true}));
            assert.equal((await policy.before(complete, next)).kind, 'deny', 'malformed output fails closed');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: true}));
            result = await policy.before(complete, async () => ({kind: 'deny', reason: 'existing policy'}));
            assert.equal(result.reason, 'existing policy', 'other security decisions are preserved');
            assert.equal((await policy.before(complete, next)).kind, 'allow');
            const artifact = {path: join(bad, 'dist/test.mcaddon'),
              sha256: createHash('sha256').update('artifact').digest('hex')};
            const deliver = call('present', {files: [{path: artifact.path}]});
            assert.equal((await policy.before(deliver, next)).kind, 'deny', 'ready alone cannot identify an artifact');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: true, artifact}));
            assert.equal((await policy.before(deliver, next)).kind, 'allow', 'verified bytes are deliverable');
            writeFileSync(artifact.path, 'unverified edit');
            assert.equal((await policy.before(deliver, next)).kind, 'deny', 'stale or substituted bytes cannot be delivered');
            writeFileSync(artifact.path, 'artifact');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: false,
              candidate_ready: true, artifact, exit: 1, blockers: ['client checks pending']}));
            assert.equal((await policy.before(deliver, next)).kind, 'deny', 'partial candidate cannot be called finished');
            const candidate = call('present', {files: [{path: artifact.path,
              description: 'TEST CANDIDATE: client checks pending'}]});
            assert.equal((await policy.before(candidate, next)).kind, 'allow', 'verified candidate enables client testing');
            assert.equal((await policy.before(complete, next)).kind, 'deny', 'candidate delivery cannot complete the goal');
            const mixed = call('present', {files: [...candidate.arguments.files,
              {path: join(root, 'notes.txt'), description: 'Finished port'}]});
            assert.equal((await policy.before(mixed, next)).kind, 'deny', 'every presented file must carry candidate labeling');
            writeFileSync(artifact.path, 'changed candidate');
            assert.equal((await policy.before(candidate, next)).kind, 'deny', 'test candidates remain hash bound');
            writeFileSync(artifact.path, 'artifact');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: false,
              candidate_ready: false, artifact, exit: 1, blockers: ['native tests failed']}));
            assert.equal((await policy.before(candidate, next)).kind, 'deny', 'a label cannot bypass failed technical checks');
            writeFileSync(join(bad, '.gate.json'), JSON.stringify({ready: false,
              candidate_ready: true, artifact, exit: 137}));
            assert.equal((await policy.before(candidate, next)).kind, 'deny', 'abnormal gate termination fails closed');
            const missing = call('present', {files: [{path: join(root, 'orphan.mcaddon')}]});
            assert.equal((await policy.before(missing, next)).kind, 'deny', 'orphan artifacts are not accepted');
            const legacy = project('legacy');
            policy.observe(call('mcp__aerocraft__start_port', {path: 'unknown'}, 'returned'),
              {isError: false, value: {content: [{type: 'text', text: JSON.stringify({project: legacy})}]}});
            assert.equal((await policy.before(call('update_goal', {action: 'complete'}, 'returned'), next)).kind,
              'deny', 'authoritative MCP returned path is used');
            const show = call('present', {files: [{path: join(legacy, 'dist/test.mcaddon')}]}, 'delivery');
            assert.equal((await policy.before(show, next)).kind, 'deny', 'legacy artifacts are gated too');
            policy = createPolicy(config);
            assert.equal((await policy.before(call('update_goal', {action: 'complete'}, 'delivery'), next)).kind,
              'deny', 'rejected presentation still associates its source project');
            assert.equal((await policy.before(call('update_goal', {action: 'complete'}, 'cwd', legacy), next)).kind,
              'deny', 'project working directory is a registration fallback');
            const controller = new AbortController(); controller.abort();
            result = await policy.before({...show, signal: controller.signal}, next);
            assert.equal(result.kind, 'cancel', 'cancellation never becomes permission');
            const sections = [], handlers = {};
            apply({systemPrompt: {section: value => sections.push(value)},
              on: (event, fn) => {handlers[event] = fn;}}, config);
            assert.equal(sections.length, 1);
            assert.equal(sections[0].interpolate, false);
            assert.match(sections[0].text, /Acceptance workflow/);
            assert.match(sections[0].text, /reverse-engineer-anything/);
            assert.equal(typeof handlers['tools/pre-execute'], 'function');
            assert.equal(typeof handlers['tools/result'], 'function');
            console.log('policy assertions passed');
            """), encoding="utf-8")
        completed = subprocess.run(
            [executable, str(script), (ROOT / "plugins/aero-policy.mjs").as_uri(), json.dumps(config)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("policy assertions passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
