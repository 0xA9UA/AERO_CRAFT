# Architecture

```text
DeepSeek Harness 0.2.1-rc.2 (local authenticated Web UI)
  ├─ normal file/terminal tools → aero.py CLI → build / decompile / smoke
  ├─ AERO_CRAFT MCP → inventories, project starters, validation, plans, API references
  └─ REA MCP → archive / JavaScript / native evidence and provider workflows

catalog/                    reviewed versions, downloads, hashes and primary-source index
aerocraft/                  portable Python CLI implementation
integrations/deepseek/      integration contract and configuration notes
docs/workflows/            Java, Bedrock and cross-engine development procedures
.runtime/                   generated runtimes, DSH state, credentials, downloads and caches
projects/                   generated local projects (ignored by this repository)
```

The harness is composed through a generated Cordis patch, never by editing the upstream package. Each MCP bridge has an explicit executable and absolute paths. The overlay is keyed by workspace so two launch configurations cannot overwrite one another. `DSH_HOME` is set only for the child process. The requested release is pinned in both the npm manifest/lock and the tool catalog with the upstream Git commit.

AERO_CRAFT's MCP server negotiates legacy MCP JSON-RPC over stdio. DeepSeek's installed MCP SDK probes modern discovery and falls back to the supported revision; `scripts/check_mcp.mjs` exercises that exact path, tool discovery, resource listing and tool calls for both servers. MCP stdout contains only protocol messages. Build commands are exposed through the CLI rather than a long-running synchronous MCP tool.

The Java profiles are minimal source starters authored for this suite, using official loader build plugins and mappings. They are not redistributed Minecraft source trees. JDKs and Gradle distributions are resolved into separate directories. The Gradle JVM is selected explicitly; user global Java preferences remain untouched. Bedrock starters use JavaScript with checked JSDoc and pinned API declarations, letting the same pure simulation module run in Node tests and the game.

Inventories and port plans record identities rather than claiming recovered behavior. Bytecode analysis, code reconstruction, engine adaptation and native execution are separate evidence types. Deterministic ZIP assembly fixes timestamps, ordering and file permissions. Package validation deliberately states its scope; it is not a complete engine schema validator. Native smoke adds a test fixture only to a copied runtime, retains logs, and proves its own narrowly stated assertions.
