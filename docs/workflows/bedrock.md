# Bedrock development and native validation

`new PATH --profile bedrock-stable --id example_addon` creates behavior/resource packs, stable UUIDs, JavaScript checked against `@minecraft/server 2.10.0`, a pure simulation test and a Node dependency lock. The profile requires Bedrock 1.26.50 or newer in that API line. `build PATH` runs `npm ci`, API typechecking and unit tests, validates manifests and emits a deterministic `dist/*.mcaddon` with SHA-256. `package PATH` only validates and packages; it does not replace a full build.

Import the `.mcaddon` into a supported Minecraft client and activate both packs. Keep each header UUID on updates and increment pack versions consistently with pack dependencies. UUIDs identify persistent script state. Keep source/test code outside `packs`; only release assets belong there.

The starter uses `world.afterEvents.worldLoad` for world access, `system.runInterval` for scheduling and dynamic properties for a boot counter. `docs api worldLoad` searches the actual installed declaration package and returns module version, file and line. `docs search persistence` finds official references and local workflow notes. Stable documentation URLs can change; installed pinned declarations and engine tests determine what this project can actually call.

Native smoke testing uses a separately obtained official Bedrock Dedicated Server:

```sh
python aero.py smoke projects/example_addon --server /path/to/extracted/bedrock-server --output .runtime/smoke-example
```

The output directory must be new and outside the project/server. The runner copies the runtime, creates a disposable `AERO-validation` world with an empty allowlist and disabled LAN advertisement, copies the built packs, and injects a test-only persistence assertion into that copy. It starts the process twice, requires boot counts 1 and 2, scans runtime/content errors and saves hashes and logs. Original server files, user worlds and the distributable packs are unchanged. The runner selects the current NetherNet transport with server-ip=127.0.0.1 and port 29981, plus an empty allowlist. This configuration targets the pinned 26.50+ engine line. Confirm transport behavior separately when adapting it to an older BDS release.

This test establishes script loading and world dynamic-property persistence. Add project-specific native fixture assertions for inventories, block updates, recipes, entities and failed mutations. A generic smoke pass does not verify those mechanics. Use an actual client for texture orientation, model geometry, sounds, screens and touch/controller interactions. Desktop Java and Bedrock Android/iOS/Xbox/PlayStation/Switch are different runtime environments; this toolkit runs on development computers and creates artifacts for supported game import mechanisms.
