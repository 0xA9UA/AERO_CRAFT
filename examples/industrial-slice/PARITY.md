# Reference scope and acceptance

This example has no third-party source mod. It demonstrates implementation and
validation patterns for a later source-backed port.

| Behavior | Implementation | Evidence to run |
|---|---|---|
| Fuel generation, caps and pause | scripts/simulation.js | generator fuel tests; native fuel accounting |
| Face-adjacent cable transfer without duplication | scripts/machines.js and simulation.js | branched/cyclic graph conservation; native connected network |
| Raw iron to iron ingot, blocked output, no-energy pause | scripts/simulation.js | recipe/full-output/pause tests; native processing and isolated furnace |
| Versioned persistent state | scripts/machines.js | native restart assertions for fuel, energy, progress, inventories |
| Piston movement prevention | block minecraft:movable components | powered-piston native control and inventory-preservation assertions |
| Inventory recovery on destruction | scripts/main.js onBreak → machines.js | native destroy-command and explosion inventory-drop assertions |
| Player insertion/collection and stale forms | scripts/machines.js | seven real-adapter VM tests; connected desktop/touch client observation remains required |
| Textures and forms | resource atlas + ActionFormData | Requires connected client observation |

Do not describe the example as a completed port. Actual verification results are
stored separately by AERO_CRAFT, bound to the tested source tree.
