// Copied beside main.js by AERO_CRAFT's native runner; imports resolve there.
import {BlockPermutation,MovementType} from '@minecraft/server';
import {NAMESPACE,readMachine,insert} from './machines.js';

export async function run(ctx) {
  const generatorPos={x:4,y:82,z:4}, cablePos={x:5,y:82,z:4}, furnacePos={x:6,y:82,z:4};
  const isolatedPos={x:12,y:82,z:4};
  const get=position=> {
    const block=ctx.dimension.getBlock(position);
    if (!block) throw new Error('Reference scenario area is unloaded');
    return block;
  };
  const generator=get(generatorPos), cable=get(cablePos), furnace=get(furnacePos), isolated=get(isolatedPos);
  const itemCount=(position,type)=>ctx.dimension.getEntities({type:'minecraft:item',location:position,maxDistance:3}).reduce((total,entity)=> {
    const stack=entity.getComponent('minecraft:item')?.itemStack;
    return total+(stack?.typeId===type ? stack.amount : 0);
  },0);
  if(ctx.boot===1) {
    generator.setPermutation(BlockPermutation.resolve(NAMESPACE+':generator'));
    cable.setPermutation(BlockPermutation.resolve(NAMESPACE+':cable'));
    furnace.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    isolated.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    ctx.assert(insert(generator,'fuel',1)===1,'generator accepts one coal unit');
    ctx.assert(insert(furnace,'input',2)===2,'furnace accepts two raw iron units');
    insert(isolated,'input',1);
    for(let i=0;i<160;i++) {
      await ctx.waitTicks(1);
      if(readMachine(furnace).output===2 && readMachine(generator).burn===0) break;
    }
    const gen=readMachine(generator), out=readMachine(furnace), paused=readMachine(isolated);
    ctx.assert(out.output===2 && out.input===0 && out.progress===0,'native generator cable furnace produces two ingots',out);
    ctx.assert(gen.fuel===0 && gen.burn===0 && gen.energy+out.energy===120,'native fuel and recipe energy accounting',{gen,out});
    ctx.assert(paused.input===1 && paused.output===0 && paused.progress===0 && paused.energy===0,'native disconnected furnace pauses without loss',paused);
    for(const block of [generator,cable,furnace]) ctx.assert(block.getComponent('minecraft:movable')?.movementType===MovementType.Immovable,'native immovable component '+block.typeId);
    // A powered stone control proves that the piston setup actually attempts a push.
    ctx.dimension.runCommand('fill 3 84 10 7 84 12 minecraft:air');
    const piston=BlockPermutation.resolve('minecraft:piston',{'facing_direction':4});
    get({x:4,y:84,z:10}).setPermutation(piston);
    get({x:4,y:84,z:12}).setPermutation(piston);
    const protectedMachine=get({x:5,y:84,z:10});
    protectedMachine.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    insert(protectedMachine,'input',3);
    get({x:5,y:84,z:12}).setPermutation(BlockPermutation.resolve('minecraft:stone'));
    get({x:4,y:83,z:10}).setPermutation(BlockPermutation.resolve('minecraft:redstone_block'));
    get({x:4,y:83,z:12}).setPermutation(BlockPermutation.resolve('minecraft:redstone_block'));
    await ctx.waitTicks(20);
    ctx.assert(get({x:6,y:84,z:12}).typeId==='minecraft:stone','native piston control pushes ordinary stone',{piston:get({x:4,y:84,z:12}).getComponent('minecraft:piston')?.state,line:[3,4,5,6,7].map(x=>get({x,y:84,z:12}).typeId)});
    ctx.assert(protectedMachine.typeId===NAMESPACE+':electric_furnace' && get({x:6,y:84,z:10}).typeId==='minecraft:air' && readMachine(protectedMachine).input===3,'native powered piston cannot move machine or lose its input');
    // Destroy mode must exercise the component callback, not call breakMachine directly.
    const destroyedPos={x:10,y:86,z:10}, destroyed=get(destroyedPos);
    destroyed.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    insert(destroyed,'input',4);
    const beforeDrops=itemCount(destroyedPos,'minecraft:raw_iron');
    ctx.dimension.runCommand('setblock 10 86 10 minecraft:air destroy');
    await ctx.waitTicks(2);
    ctx.assert(itemCount(destroyedPos,'minecraft:raw_iron')-beforeDrops===4,'native destroy command drops machine input exactly once');
    destroyed.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    ctx.assert(readMachine(destroyed).input===0,'native destroyed machine cannot recover a duplicate saved input');
    const blastPos={x:10,y:92,z:10}, blasted=get(blastPos);
    blasted.setPermutation(BlockPermutation.resolve(NAMESPACE+':electric_furnace'));
    insert(blasted,'input',5);
    const beforeBlast=itemCount(blastPos,'minecraft:raw_iron');
    ctx.dimension.createExplosion({x:10.5,y:92.5,z:10.5},3,{breaksBlocks:true,causesFire:false});
    await ctx.waitTicks(2);
    ctx.assert(blasted.typeId==='minecraft:air','native explosion destroys the test machine');
    ctx.assert(itemCount(blastPos,'minecraft:raw_iron')-beforeBlast===5,'native explosion drops machine input exactly once');
    // Let the final transfer settle; the full furnace buffer makes this stable.
    await ctx.waitTicks(20);
    ctx.world.setDynamicProperty(NAMESPACE+':expected_restart',JSON.stringify({generator:readMachine(generator),furnace:readMachine(furnace),isolated:readMachine(isolated)}));
  } else {
    const encoded=ctx.world.getDynamicProperty(NAMESPACE+':expected_restart');
    ctx.assert(typeof encoded==='string','native restart expectation was persisted');
    const expected=JSON.parse(encoded);
    ctx.assert(generator.typeId===NAMESPACE+':generator' && cable.typeId===NAMESPACE+':cable' && furnace.typeId===NAMESPACE+':electric_furnace','native placed industrial network survives restart');
    ctx.assert(JSON.stringify(readMachine(generator))===JSON.stringify(expected.generator),'native generator energy and fuel persist across restart');
    ctx.assert(JSON.stringify(readMachine(furnace))===JSON.stringify(expected.furnace),'native furnace outputs and progress persist across restart');
    ctx.assert(JSON.stringify(readMachine(isolated))===JSON.stringify(expected.isolated),'native paused machine input persists across restart');
    const beforeOutput=itemCount(furnacePos,'minecraft:iron_ingot');
    ctx.dimension.runCommand('setblock 6 82 4 minecraft:air destroy');
    await ctx.waitTicks(2);
    ctx.assert(itemCount(furnacePos,'minecraft:iron_ingot')-beforeOutput===2,'native destroy command drops finished outputs exactly once');
  }
}
