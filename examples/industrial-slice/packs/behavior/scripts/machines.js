import {world, ItemStack} from '@minecraft/server';
import {ActionFormData} from '@minecraft/server-ui';
import {initial, isState, step, CAPACITY} from './simulation.js';

export const NAMESPACE = '__MOD_ID__';
const SAVE_KEY = NAMESPACE + ':network_v1';
const MAX_NODES = 64;
/** @typedef {import('./simulation.js').State} State */
/** @typedef {import('./simulation.js').Kind} Kind */
/** @typedef {{dimension:string,x:number,y:number,z:number,state:State}} Entry */
/** @type {Map<string,Entry>|undefined} */
let cache;

/** @param {import('@minecraft/server').Block} block */
function key(block) {
  const p=block.location;
  return `${block.dimension.id}|${p.x},${p.y},${p.z}`;
}
/** @param {string} id @returns {Kind|undefined} */
function kind(id) {
  for (const value of ['generator','cable','electric_furnace']) {
    if (id === NAMESPACE + ':' + value) {
      if (value === 'generator' || value === 'cable' || value === 'electric_furnace') return value;
    }
  }
  return undefined;
}

function load() {
  if (cache) return cache;
  /** @type {Map<string,Entry>} */
  const result = new Map();
  const saved = world.getDynamicProperty(SAVE_KEY);
  if (typeof saved === 'string') {
    /** @type {unknown} */
    const parsed = JSON.parse(saved);
    if (!parsed || typeof parsed !== 'object' || !('version' in parsed) || parsed.version !== 1 || !('nodes' in parsed) || !Array.isArray(parsed.nodes)) throw new Error('Unsupported industrial save; preserve the world and migrate its state');
    if (parsed.nodes.length > MAX_NODES) throw new Error('Industrial save exceeds supported network size');
    /** @type {unknown[]} */
    const savedNodes=parsed.nodes;
    for (const entry of savedNodes) {
      if (!isEntry(entry)) throw new Error('Invalid industrial saved node; refusing to discard its inventory');
      result.set(`${entry.dimension}|${entry.x},${entry.y},${entry.z}`, entry);
    }
  }
  cache=result;
  return result;
}

/** @param {unknown} value @returns {value is Entry} */
function isEntry(value) {
  return !!value && typeof value==='object' && 'dimension' in value && typeof value.dimension==='string' &&
    'x' in value && typeof value.x==='number' && Number.isInteger(value.x) &&
    'y' in value && typeof value.y==='number' && Number.isInteger(value.y) &&
    'z' in value && typeof value.z==='number' && Number.isInteger(value.z) &&
    'state' in value && isState(value.state);
}

function save() {
  world.setDynamicProperty(SAVE_KEY, JSON.stringify({version:1,nodes:[...load().values()]}));
}

/** Register placed/loaded machines; preserve an existing state of the same kind.
 * @param {import('@minecraft/server').Block} block
 */
export function track(block) {
  const type = kind(block.typeId);
  if (!type) return;
  const nodes=load(), id=key(block), old=nodes.get(id);
  if (old && old.state.kind === type) return;
  if (nodes.size >= MAX_NODES && !old) return;
  const p=block.location;
  nodes.set(id,{dimension:block.dimension.id,x:p.x,y:p.y,z:p.z,state:initial(type)});
  save();
}

/** @param {import('@minecraft/server').Block} block @returns {State} */
export function readMachine(block) {
  track(block);
  const entry=load().get(key(block));
  if (!entry) throw new Error('Not an industrial block, or the 64-block example limit was reached');
  return {...entry.state};
}

/** Atomic slot insertion shared by player interactions and native scenario tests.
 * @param {import('@minecraft/server').Block} block @param {'fuel'|'input'} slot @param {number} amount
 */
export function insert(block,slot,amount) {
  if (!Number.isInteger(amount) || amount < 0) throw new RangeError('Invalid inserted amount');
  const state=readMachine(block);
  if (slot === 'fuel' && state.kind !== 'generator' || slot === 'input' && state.kind !== 'electric_furnace') return 0;
  const entry=load().get(key(block));
  if (!entry) throw new Error('Machine state disappeared');
  const accepted=Math.min(64-state[slot],amount);
  entry.state[slot]+=accepted;
  save();
  return accepted;
}

/** Run only loaded networks. Unloaded chunks retain their data and stop work. */
export function tickNetwork() {
  const entries=load();
  /** @type {Entry[]} */
  const active=[];
  let changed=false;
  for (const [id,entry] of entries) {
    try {
      const block=world.getDimension(entry.dimension).getBlock(entry);
      if (!block) continue;
      if (block.typeId !== NAMESPACE+':'+entry.state.kind) { entries.delete(id); changed=true; continue; }
      active.push(entry);
    } catch (error) {
      if (error instanceof Error && /unloaded|out of world|out of bounds/i.test(error.message)) continue;
      throw error;
    }
  }
  /** @type {[number,number][]} */
  const links=[];
  for (let a=0;a<active.length;a++) for (let b=a+1;b<active.length;b++) {
    const left=active[a],right=active[b];
    if (left.dimension===right.dimension && Math.abs(left.x-right.x)+Math.abs(left.y-right.y)+Math.abs(left.z-right.z)===1) links.push([a,b]);
  }
  const after=step(active.map(e=>e.state),links);
  for (let i=0;i<active.length;i++) {
    if (JSON.stringify(active[i].state)!==JSON.stringify(after.nodes[i])) changed=true;
    active[i].state=after.nodes[i];
  }
  if (changed) save();
}

/** @param {import('@minecraft/server').Block} block */
export function breakMachine(block) {
  const entries=load(), id=key(block), entry=entries.get(id);
  if (!entry) return;
  entries.delete(id); save();
  const s=entry.state;
  for (const [item,count] of /** @type {[string,number][]} */ ([['minecraft:coal',s.fuel],['minecraft:raw_iron',s.input],['minecraft:iron_ingot',s.output]])) {
    if (count) block.dimension.spawnItem(new ItemStack(item,count),{x:entry.x+0.5,y:entry.y+0.5,z:entry.z+0.5});
  }
}

/** Forms make the example usable on touch and desktop clients.
 * The native scenario tests mechanics; it does not certify visual/touch behavior.
 * @param {import('@minecraft/server').Block} block @param {import('@minecraft/server').Player} player
 */
export async function interact(block,player) {
  const state=readMachine(block);
  const machineKey=key(block), originalEntry=load().get(machineKey);
  const dimension=block.dimension, position={...block.location};
  if (!originalEntry) return;
  const body=`Energy: ${state.energy}/${CAPACITY}\nCoal: ${state.fuel} (+${state.burn} burn steps)\nRaw iron: ${state.input}\nIron ingots: ${state.output}\nProgress: ${state.progress}/10\n\nConnect generator → cable → electric furnace by touching faces.`;
  const form=new ActionFormData().title(state.kind.replaceAll('_',' ')).body(body);
  if (state.kind==='generator') form.button('Insert held coal').button('Collect unused coal');
  else if (state.kind==='electric_furnace') form.button('Insert held raw iron').button('Collect iron ingots');
  else form.button('Close');
  const response=await form.show(player);
  if (response.canceled || response.selection===undefined || state.kind==='cable') return;
  // Forms can stay open while another player destroys/replaces the machine or
  // this player moves away. Never apply an old form to the replacement's slots.
  if (!player.isValid || player.dimension.id!==dimension.id) return;
  const location=player.location;
  if ((location.x-position.x-0.5)**2+(location.y-position.y-0.5)**2+(location.z-position.z-0.5)**2>64) return;
  let currentBlock;
  try { currentBlock=dimension.getBlock(position); } catch { return; }
  if (!currentBlock || currentBlock.typeId!==NAMESPACE+':'+state.kind || load().get(machineKey)!==originalEntry) return;
  const container=player.getComponent('minecraft:inventory')?.container;
  if (!container) return;
  const current={...originalEntry.state}, entry=originalEntry;
  if (response.selection===0) {
    const slot=state.kind==='generator' ? 'fuel' : 'input';
    const item=state.kind==='generator' ? 'minecraft:coal' : 'minecraft:raw_iron';
    const held=container.getItem(player.selectedSlotIndex);
    if (!held || held.typeId!==item) { player.sendMessage('Hold '+item+' before inserting.'); return; }
    const accepted=Math.min(64-current[slot],held.amount);
    if (!accepted) { player.sendMessage('The input slot is full.'); return; }
    if (accepted===held.amount) container.setItem(player.selectedSlotIndex,undefined);
    else { held.amount-=accepted; container.setItem(player.selectedSlotIndex,held); }
    insert(currentBlock,slot,accepted);
    player.sendMessage('Inserted '+accepted+'.');
  } else {
    const slot=state.kind==='generator' ? 'fuel' : 'output';
    const item=state.kind==='generator' ? 'minecraft:coal' : 'minecraft:iron_ingot';
    if (current[slot]===0) { player.sendMessage('Nothing to collect yet.'); return; }
    const remaining=container.addItem(new ItemStack(item,current[slot]));
    const taken=current[slot]-(remaining?.amount ?? 0);
    entry.state[slot]-=taken; save();
    player.sendMessage('Collected '+taken+'.');
  }
}
