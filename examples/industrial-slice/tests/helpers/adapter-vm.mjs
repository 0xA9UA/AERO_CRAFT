// Evaluate the shipped adapter and entry point unchanged. Only Minecraft's native
// modules are synthetic; simulation.js, machines.js and main.js are real files.
import vm from 'node:vm';
import fs from 'node:fs';

const mode=process.argv[2], props=new Map(), grid=new Map(), drops=[];
let respond, handlers, collected=0;
class ItemStack {constructor(typeId,amount) {this.typeId=typeId;this.amount=amount;}}
class ActionFormData {
  title(){return this;} body(){return this;} button(){return this;}
  show(){return new Promise(resolve=>{respond=resolve;});}
}
const dimension={id:'minecraft:overworld',getBlock:position=>blockAt(position.x),spawnItem:stack=>drops.push(stack)};
function blockAt(x) {return {location:{x,y:80,z:0},dimension,get typeId(){return grid.get(x)??'minecraft:air';}};}
const world={getDynamicProperty:key=>props.get(key),setDynamicProperty:(key,value)=>props.set(key,value),getDimension:()=>dimension,afterEvents:{worldLoad:{subscribe(){}}}};
const system={beforeEvents:{startup:{subscribe(callback){callback({blockComponentRegistry:{registerCustomComponent(name,component){handlers=component;}}});}}},run:callback=>callback()};
const context=vm.createContext({console,Map,Set,JSON,Error,RangeError,Number,Math});
const server=new vm.SyntheticModule(['world','system','ItemStack'],function(){this.setExport('world',world);this.setExport('system',system);this.setExport('ItemStack',ItemStack);},{context});
const ui=new vm.SyntheticModule(['ActionFormData'],function(){this.setExport('ActionFormData',ActionFormData);},{context});
const read=name=>fs.readFileSync(new URL('../../packs/behavior/scripts/'+name,import.meta.url),'utf8');
const simulation=new vm.SourceTextModule(read('simulation.js'),{context});
const machines=new vm.SourceTextModule(read('machines.js'),{context});
await machines.link(name=>name==='@minecraft/server'?server:name==='@minecraft/server-ui'?ui:simulation);
await machines.evaluate();
const main=new vm.SourceTextModule(read('main.js'),{context});
await main.link(name=>name==='@minecraft/server'?server:machines);await main.evaluate();
const m=machines.namespace, id=m.NAMESPACE+':generator';
grid.set(0,id);m.insert(blockAt(0),'fuel',6);
const player={isValid:true,dimension,location:{x:0,y:80,z:0},getComponent:()=>({container:{addItem(stack){if(mode==='full_inventory')return stack;collected+=stack.amount;return undefined;}}}),sendMessage(){}};
if(mode==='on_break') {
  grid.delete(0);
  handlers.onBreak({block:blockAt(0)});
  handlers.onBreak({block:blockAt(0)});
  grid.set(0,id);m.track(blockAt(0));
} else {
  const pending=m.interact(blockAt(0),player);
  if(mode==='stale') {
    grid.delete(0);handlers.onBreak({block:blockAt(0)});
    grid.set(0,id);m.track(blockAt(0));m.insert(blockAt(0),'fuel',9);
  } else if(mode==='out_of_reach') player.location={x:20,y:80,z:0};
  else if(mode==='different_dimension') player.dimension={id:'minecraft:nether'};
  else if(mode==='disconnected') player.isValid=false;
  respond({canceled:false,selection:1});await pending;
}
console.log(JSON.stringify({collected,fuel:m.readMachine(blockAt(0)).fuel,dropped:drops.filter(s=>s.typeId==='minecraft:coal').reduce((sum,s)=>sum+s.amount,0)}));
