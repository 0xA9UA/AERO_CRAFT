import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const cases=[
  ['stale','stale form cannot collect from a replacement machine',{collected:0,fuel:9,dropped:6}],
  ['out_of_reach','moving beyond reach invalidates a pending form',{collected:0,fuel:6,dropped:0}],
  ['different_dimension','changing dimension invalidates a pending form',{collected:0,fuel:6,dropped:0}],
  ['disconnected','disconnected player cannot use a pending form',{collected:0,fuel:6,dropped:0}],
  ['valid','valid nearby form collects exactly the available fuel',{collected:6,fuel:0,dropped:0}],
  ['full_inventory','full player inventory preserves machine contents',{collected:0,fuel:6,dropped:0}],
  ['on_break','registered onBreak recovers inventory once and clears saved state',{collected:0,fuel:0,dropped:6}],
];
for(const [mode,name,expected] of cases) test(name,()=> {
  const child=spawnSync(process.execPath,['--experimental-vm-modules',fileURLToPath(new URL('./helpers/adapter-vm.mjs',import.meta.url)),mode],{encoding:'utf8'});
  assert.equal(child.status,0,child.stdout+'\n'+child.stderr);
  assert.deepEqual(JSON.parse(child.stdout),expected);
});
