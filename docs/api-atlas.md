# Minecraft API navigation

There is no single interchangeable “Minecraft API.” Select engine, Minecraft version, loader and mappings first. `docs search QUERY` returns version-scoped primary references. `docs api QUERY` searches the installed Bedrock declarations offline. `docs cache ID` retains one reference page locally with its URL and SHA-256; upstream pages and licenses remain authoritative.

| Feature | Java starting point | Bedrock starting point | Porting constraint |
|---|---|---|---|
| Registration | Fabric initializer/Registry; Forge/NeoForge DeferredRegister | Pack items, blocks and entities; custom component registration | Identifier registration does not implement behavior |
| Ticks | Loader tick events and block/entity ticking | `system.run`, `runInterval`, `runJob` | Tick budget, unloaded chunks and scheduling differ |
| World lifecycle | Loader server/world lifecycle events | `world.afterEvents.worldLoad` | Startup registration can precede usable world access |
| Inventory | ItemStack, containers, capabilities/transfer APIs | `Container`, `ItemStack`, inventory components | Revalidate slots and handle uninserted leftovers |
| Persistent state | NBT/components, SavedData, block entities | World/entity/item dynamic properties | Preserve schema versions and behavior-pack UUID |
| Blocks | Block states, block entities, registry lookup | `Dimension.getBlock`, `BlockPermutation`, components | Block state sets and mutation permissions differ |
| UI | Menus/screens and network synchronization | `@minecraft/server-ui` form classes | Async form replies can refer to stale state |
| Networking | Loader payload/channel APIs | Engine synchronization and supported script events | Arbitrary Java packets have no direct addon equivalent |
| Recipes | Datapack JSON and custom serializers | `minecraft:recipe_shaped`, `recipe_shapeless`, furnace | Tags, metadata, conditions and cooking semantics differ |
| Assets | Java model inheritance and texture references | Bedrock geometry, material instances and texture atlases | Resolve parents and verify each face/UV in a client |

Java generated sources and loader JavaDocs are fetched by the build environment; copyrighted Minecraft game code is not vendored. REA evidence should cite concrete artifact members and hashes. Decompiler output is an interpretation that can lose synthetic constructs or misrepresent control flow; corroborate critical behavior with bytecode and focused tests.
