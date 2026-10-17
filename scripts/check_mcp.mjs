// Exercise the same MCP SDK used by the pinned DeepSeek release; no model key required.
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const python = process.env.AERO_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
for (const kind of ['aerocraft', 'rea']) {
  const client = new Client({name:'aero-craft-validation',version:'0.1.0'});
  const transport = new StdioClientTransport({
    command: kind === 'aerocraft' ? python : process.execPath,
    args: kind === 'aerocraft' ? [resolve(root,'aero.py'),'mcp','--workspace',root] : [resolve(root,'node_modules/rea-agents/scripts/rea.mjs'),'mcp'],
    cwd: root,
    env: {...process.env},
    stderr: 'pipe'
  });
  try {
    await client.connect(transport);
    const {tools} = await client.listTools();
    assert.ok(tools.length > 0);
    if (kind === 'aerocraft') {
      const value = await client.callTool({name:'list_profiles',arguments:{}});
      assert.ok(!value.isError);
      assert.ok(JSON.parse(value.content[0].text)['bedrock-stable']);
      const resources = await client.listResources();
      assert.ok(resources.resources.length >= 4);
      const guide = await client.readResource({uri:'aerocraft://docs/workflows/porting.md'});
      assert.ok(guide.contents[0].text.includes('Java ↔ Bedrock'));
    } else {
      assert.ok(tools.some(t=>t.name==='binary_session'));
      const value = await client.callTool({name:'binary_session',arguments:{}});
      assert.ok(!value.isError);
    }
    console.log(`${kind}: negotiated, discovered ${tools.length} tools, called a tool successfully`);
  } finally { await client.close(); }
}
