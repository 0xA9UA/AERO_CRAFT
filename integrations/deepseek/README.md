# DeepSeek Harness integration

Runtime: `@deepseek-ai/dsh@0.2.1-rc.2`, corresponding to `dsh-v0.2.1-rc.2`, commit `687f282e8625c6b8d11ff58211a90524be2e4317`.

`aerocraft/harness.py` generates a YAML-compatible JSON patch with two root `insert` rows for `@deepseek-ai/dsh-mcp-client`. Each uses stdio transport, its own `serverName`, explicit command/args/cwd/env, and a stable row ID. This is the documented patch format for the selected release, rather than a generic mcpServers JSON file that DSH would not load.

`python aero.py harness --workspace PATH --dump-config` shows the composed configuration without starting the Web UI. Ordinary launch passes `web --patch PATH --host 127.0.0.1 --port 3080`; `--no-open` suppresses automatic browser opening. The Web UI's printed URL contains the login token. Do not publish that URL or the generated DSH files.

The launcher supplies no model key and makes no paid model call during setup or validation. Configure a provider in the Web UI. Built-in permissions are unchanged. Read upstream release documentation before upgrading because DSH is a developer preview and patch formats may change.
