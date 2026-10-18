"""Runtime provenance, isolation and native-test failure regression tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aerocraft import projects, runtimes, smoke
from aerocraft.common import CraftError, read_json, sha256, write_json


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'state'
        self.mock_home = patch.object(runtimes, 'RUNTIME', self.home)
        self.mock_home.start()

    def tearDown(self):
        self.mock_home.stop()
        self.tmp.cleanup()

    def server(self, path=None, content=b'fixture executable'):
        path = path or self.root / 'server'
        path.mkdir(parents=True)
        binary = path / ('bedrock_server.exe' if os.name == 'nt' else 'bedrock_server')
        binary.write_bytes(content)
        binary.chmod(0o755)
        return path

    def test_registration_never_changes_original_and_detects_replacement(self):
        server = self.server()
        binary = runtimes._binary(server)
        before = sha256(binary)
        row = runtimes.register_bedrock(binary, expected_version='1.26.52.3')
        self.assertEqual(before, sha256(binary))
        self.assertEqual(row['sha256'], before)
        self.assertTrue((self.home / 'runtimes.json').is_file())
        binary.write_bytes(b'changed runtime')
        listing = runtimes.discover_bedrock()['runtimes']
        self.assertTrue(listing[0]['changed'])
        self.assertFalse(listing[0]['usable'])
        with self.assertRaisesRegex(CraftError, 'changed'):
            runtimes.resolve_bedrock('default')

    def test_discovery_is_bounded_and_preserves_registration_aliases(self):
        server = self.server(self.home / 'smoke-previous/server')
        self.server(self.root / 'outside-home/secret-server')
        runtimes.register_bedrock(server)
        runtimes.register_bedrock(server, name='named')
        rows = runtimes.discover_bedrock()['runtimes']
        self.assertEqual({r.get('name') for r in rows}, {'default', 'named'})
        self.assertEqual({r['path'] for r in rows}, {str(server)})

    def test_versions_require_hash_bound_evidence(self):
        server = self.server(self.home / 'smoke-version/server')
        (server.parent / 'server.log').write_text('Version: 1.26.52.3\n')
        write_json(server.parent / 'report.json', {'server_sha256': 'wrong'})
        self.assertIsNone(runtimes._evidence(server)['observed_version'])
        write_json(server.parent / 'report.json', {'server_sha256': sha256(runtimes._binary(server))})
        self.assertEqual(runtimes._evidence(server)['observed_version'], '1.26.52.3')

    def test_copy_excludes_old_worlds_custom_packs_and_nested_logs(self):
        server = self.server()
        for rel in ['behavior_packs/vanilla/keep.json', 'behavior_packs/ic2-development/remove.json', 'resource_packs/aero-old/remove.json', 'worlds/old/level.dat', 'logs/nested/ContentLog-old.txt', 'config/default/permissions.json', 'data/ContentLog-old.txt']:
            p = server / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        stage = self.root / 'stage'
        excluded = smoke._copy_runtime(server, stage)
        self.assertTrue((stage / 'behavior_packs/vanilla/keep.json').is_file())
        self.assertFalse((stage / 'worlds').exists())
        self.assertFalse((stage / 'config').exists())
        self.assertFalse((stage / 'behavior_packs/ic2-development').exists())
        self.assertFalse((stage / 'resource_packs/aero-old').exists())
        self.assertFalse((stage / 'data/ContentLog-old.txt').exists())
        self.assertIn('behavior_packs/ic2-development', excluded)
        self.assertTrue((server / 'worlds/old/level.dat').exists())

    def test_probe_assertion_cannot_skip_declared_content(self):
        report = {'boots': 1, 'passed': True, 'blocks': [], 'items': []}
        with self.assertRaisesRegex(CraftError, 'inventory'):
            smoke._check_assertion(report, 1, {'test:machine'}, set(), False)
        report['blocks'] = [{'id': 'test:machine', 'registered': True, 'resolved': True, 'placed': False}]
        with self.assertRaisesRegex(CraftError, 'placement'):
            smoke._check_assertion(report, 1, {'test:machine'}, set(), False)
        report['blocks'][0]['placed'] = True
        with self.assertRaisesRegex(CraftError, 'named assertions'):
            smoke._check_assertion(report, 1, {'test:machine'}, set(), True)

    def fake_native(self, mode):
        project = self.root / 'addon'
        projects.create(project, 'bedrock-stable', 'test_addon')
        server = self.server()
        (server / 'mode.txt').write_text(mode)
        script = self.root / 'fake_bds.py'
        script.write_text(r'''
import json, re, sys
from pathlib import Path
root=Path.cwd()
count=root/'worlds/AERO-validation/count.txt'
boot=int(count.read_text())+1 if count.exists() else 1
count.write_text(str(boot))
source=next(root.glob('behavior_packs/aero-*/scripts/__aero_smoke_*.js')).read_text()
token=json.loads(re.search(r'const token = ("[^"]+")',source).group(1))
mode=(root/'mode.txt').read_text()
marker='[AERO_CRAFT_SCRIPT] '+json.dumps({'token':token,'module':'packs/behavior/scripts/main.js'})
log=root/'logs/nested/ContentLog-fixture.txt'
log.parent.mkdir(parents=True,exist_ok=True)
print('Version: 1.26.52.3',flush=True)
if not (mode=='missing-second-marker' and boot==2):
 with log.open('a') as handle: handle.write(marker+'\n')
 print(marker,flush=True)
print('[AERO_CRAFT_SMOKE] '+json.dumps({'token':token,'boots':boot,'passed':True,'blocks':[],'items':[],'assertions':[]}),flush=True)
for line in sys.stdin:
 if line.strip()=='stop':
  if mode=='late-content-error':
   with log.open('a') as handle: handle.write('[Blocks][error]-fixture invalid component\n')
  break
''', encoding='utf-8')
        real_popen = subprocess.Popen
        runtime = {'path': str(server), 'binary': str(runtimes._binary(server)), 'sha256': sha256(runtimes._binary(server))}
        output = self.root / 'native-result'
        before = {p.relative_to(project).as_posix(): sha256(p) for p in (project / 'packs').rglob('*') if p.is_file()}
        with patch.object(smoke, 'resolve_bedrock', return_value=runtime), patch.object(smoke.subprocess, 'Popen', side_effect=lambda args, **kw: real_popen([sys.executable, str(script)], **kw)):
            report = smoke.bedrock_smoke(project, server, output, timeout=5)
        after = {p.relative_to(project).as_posix(): sha256(p) for p in (project / 'packs').rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(report['source_packs'], before)
        self.assertEqual(read_json(output / 'report.json')['passed'], report['passed'])
        return report

    def test_native_scenario_requires_named_boolean_passes(self):
        report = {'boots': 1, 'passed': True, 'blocks': [], 'items': [], 'assertions': []}
        for assertion in ({'name': '', 'passed': True}, {'name': True, 'passed': True}, {'name': 'scenario', 'passed': 'true'}):
            report['assertions'] = [assertion]
            with self.subTest(assertion=assertion), self.assertRaises(CraftError):
                smoke._check_assertion(report, 1, set(), set(), True)

    def test_native_success_requires_both_boots_and_preserves_sources(self):
        report = self.fake_native('success')
        self.assertTrue(report['passed'], report.get('failure'))
        self.assertEqual(report['observed_boots'], [1, 2])
        self.assertFalse(report['client_rendering_observed'])
        self.assertFalse(report['mechanics_assertions_observed'])

    def test_late_nested_content_error_fails_otherwise_successful_run(self):
        report = self.fake_native('late-content-error')
        self.assertFalse(report['passed'])
        self.assertTrue(any('fixture invalid component' in e for e in report['errors']))
        self.assertIn('logs/nested/ContentLog-fixture.txt', report['content_logs'])

    def test_prior_boot_log_cannot_satisfy_missing_second_script_marker(self):
        report = self.fake_native('missing-second-marker')
        self.assertFalse(report['passed'])
        self.assertIn('missing script markers', report['failure'])
        self.assertEqual(report['observed_boots'], [1])


if __name__ == '__main__':
    unittest.main()
