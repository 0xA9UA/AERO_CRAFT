import {system,world} from '@minecraft/server';
import {track,tickNetwork,breakMachine,interact} from './machines.js';

system.beforeEvents.startup.subscribe(event => {
  event.blockComponentRegistry.registerCustomComponent('__MOD_ID__:industrial', {
    onPlace(event) { track(event.block); },
    onTick(event) { track(event.block); },
    onBreak(event) { breakMachine(event.block); },
    onPlayerInteract(event) {
      const player=event.player;
      if (player) system.run(()=>interact(event.block,player).catch(error=>console.error('Industrial interaction failed: '+error)));
    },
  });
});

world.afterEvents.worldLoad.subscribe(()=> {
  console.warn('[AERO_CRAFT_READY] Industrial reference: generator → cable → electric furnace');
  system.runInterval(()=>tickNetwork(),5);
});
