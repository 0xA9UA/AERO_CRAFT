import test from 'node:test';
import assert from 'node:assert/strict';
import {initial,step,CAPACITY,COST,RECIPE_STEPS,FUEL_STEPS,GENERATION,isState} from '../packs/behavior/scripts/simulation.js';

const energy=nodes=>nodes.reduce((sum,node)=>sum+node.energy,0);
test('generator cable furnace consumes one raw iron and produces one ingot',()=> {
  let nodes=[{...initial('generator'),fuel:1},initial('cable'),{...initial('electric_furnace'),input:1}];
  const original=nodes, before=structuredClone(nodes);
  let consumed=0;
  for(let i=0;i<RECIPE_STEPS;i++) {const result=step(nodes,[[0,1],[1,2]]); nodes=result.nodes; consumed+=result.consumed;}
  assert.equal(nodes[2].input,0); assert.equal(nodes[2].output,1); assert.equal(nodes[2].progress,0);
  assert.equal(consumed,COST*RECIPE_STEPS);
  assert.deepEqual(original,before);
});
test('energy is conserved through branched cables and duplicate cyclic links',()=> {
  let nodes=[{...initial('generator'),fuel:1},initial('cable'),initial('cable'),{...initial('electric_furnace'),input:3},{...initial('electric_furnace'),input:3}];
  let generated=0,consumed=0;
  for(let i=0;i<80;i++) {
    const before=energy(nodes), result=step(nodes,[[0,1],[1,2],[2,1],[1,3],[2,4],[1,3]]);
    assert.equal(energy(result.nodes),before+result.generated-result.consumed);
    assert.ok(result.nodes.every(n=>n.energy>=0 && n.energy<=CAPACITY));
    generated+=result.generated; consumed+=result.consumed; nodes=result.nodes;
  }
  assert.equal(generated,FUEL_STEPS*GENERATION); assert.equal(energy(nodes),generated-consumed);
});
test('full output preserves input progress and energy',()=> {
  const state={...initial('electric_furnace'),input:4,output:64,energy:30,progress:7};
  const result=step([state],[]);
  assert.deepEqual(result.nodes[0],state); assert.equal(result.consumed,0);
});
test('no energy pauses progress and resumes without losing input',()=> {
  const state={...initial('electric_furnace'),input:1,energy:0,progress:9};
  assert.deepEqual(step([state],[]).nodes[0],state);
  const resumed=step([{...state,energy:COST}],[]).nodes[0];
  assert.equal(resumed.input,0); assert.equal(resumed.output,1); assert.equal(resumed.energy,0); assert.equal(resumed.progress,0);
});
test('disconnected furnace receives no energy',()=> {
  const result=step([{...initial('generator'),fuel:1},initial('cable'),{...initial('electric_furnace'),input:1}],[[0,1]]);
  assert.equal(result.nodes[2].energy,0); assert.equal(result.nodes[2].progress,0); assert.equal(result.transferred,0);
});
test('full generator pauses burning instead of consuming fuel without capacity',()=> {
  const state={...initial('generator'),energy:CAPACITY,fuel:1};
  assert.deepEqual(step([state],[]).nodes[0],state);
});
test('invalid persisted values and graph edges fail visibly',()=> {
  assert.equal(isState({...initial('generator'),energy:NaN}),false);
  assert.equal(isState({...initial('generator'),fuel:-1}),false);
  assert.equal(isState({...initial('electric_furnace'),output:65}),false);
  assert.throws(()=>step([initial('cable')],[[0,4]]),RangeError);
  assert.throws(()=>step([{...initial('cable'),energy:-1}],[]));
});
