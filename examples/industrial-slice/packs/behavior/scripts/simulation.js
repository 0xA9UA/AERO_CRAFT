/** Pure transitions. No Bedrock globals: the same code runs in Node tests. */
export const CAPACITY = 64;
export const GENERATION = 8;
export const FUEL_STEPS = 20;
export const TRANSFER = 8;
export const COST = 2;
export const RECIPE_STEPS = 10;
/** @typedef {'generator'|'cable'|'electric_furnace'} Kind */
/** @typedef {{kind:Kind, energy:number, fuel:number, burn:number, input:number, output:number, progress:number}} State */

/** @param {Kind} kind @returns {State} */
export function initial(kind) {
  return {kind, energy:0, fuel:0, burn:0, input:0, output:0, progress:0};
}

/** Validate saved state instead of trusting JSON or silently resetting a save.
 * @param {unknown} value @returns {value is State}
 */
export function isState(value) {
  if (!value || typeof value !== 'object') return false;
  if (!('kind' in value) || typeof value.kind !== 'string' || !['generator','cable','electric_furnace'].includes(value.kind)) return false;
  for (const key of ['energy','fuel','burn','input','output','progress']) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || typeof descriptor.value !== 'number' || !Number.isInteger(descriptor.value) || descriptor.value < 0) return false;
  }
  return 'energy' in value && Number(value.energy) <= CAPACITY &&
    'fuel' in value && Number(value.fuel) <= 64 && 'burn' in value && Number(value.burn) <= FUEL_STEPS &&
    'input' in value && Number(value.input) <= 64 && 'output' in value && Number(value.output) <= 64 &&
    'progress' in value && Number(value.progress) < RECIPE_STEPS;
}

/** One network step. Links describe actual face-adjacent loaded blocks.
 * Energy does not duplicate in cable loops: each generator has one transfer budget.
 * @param {State[]} before @param {[number,number][]} links
 */
export function step(before, links) {
  if (!before.every(isState)) throw new Error('Invalid industrial state');
  const nodes = before.map(node => ({...node}));
  let generated = 0, consumed = 0, transferred = 0;
  const adjacency = nodes.map(() => /** @type {number[]} */ ([]));
  for (const [a,b] of links) {
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 0 || a >= nodes.length || b >= nodes.length) throw new RangeError('Invalid network edge');
    if (a !== b) { adjacency[a].push(b); adjacency[b].push(a); }
  }
  for (const node of nodes) {
    if (node.kind !== 'generator' || node.energy > CAPACITY - GENERATION) continue;
    if (node.burn === 0 && node.fuel > 0) { node.fuel--; node.burn = FUEL_STEPS; }
    if (node.burn > 0) { node.burn--; node.energy += GENERATION; generated += GENERATION; }
  }
  const seen = new Set();
  for (let start=0; start<nodes.length; start++) {
    if (seen.has(start)) continue;
    const connected = [], queue = [start];
    seen.add(start);
    while (queue.length) {
      const index = queue.shift();
      if (index === undefined) break;
      connected.push(index);
      for (const neighbor of adjacency[index]) if (!seen.has(neighbor)) { seen.add(neighbor); queue.push(neighbor); }
    }
    const furnaces = connected.filter(i => nodes[i].kind === 'electric_furnace');
    for (const index of connected) {
      const generator = nodes[index];
      if (generator.kind !== 'generator') continue;
      let budget = Math.min(TRANSFER, generator.energy);
      for (const index of furnaces) {
        const target = nodes[index], amount = Math.min(budget, CAPACITY - target.energy);
        generator.energy -= amount; target.energy += amount; budget -= amount; transferred += amount;
      }
    }
  }
  for (const node of nodes) {
    if (node.kind !== 'electric_furnace' || node.input === 0 || node.output >= 64 || node.energy < COST) continue;
    node.energy -= COST; consumed += COST; node.progress++;
    if (node.progress === RECIPE_STEPS) { node.input--; node.output++; node.progress = 0; }
  }
  return {nodes, generated, consumed, transferred};
}
