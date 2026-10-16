import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { ROOT } from '../lib/core.mjs';

test('actual MCP stdio discovery, schema validation, persistence, prompt and report', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'zhiwei-mcp-'));
  const transport = new StdioClientTransport({ command: process.execPath, args: [join(ROOT, 'bin/zhiwei.mjs'), 'mcp', '--data-dir', dir], stderr: 'pipe' });
  const client = new Client({ name: 'zhiwei-test-client', version: '1.0.0' });
  t.after(async () => { await client.close(); await rm(dir, { recursive: true, force: true }); });
  await client.connect(transport);
  const catalog = await client.listTools(); assert.equal(catalog.tools.length, 15);
  const prompts = await client.listPrompts(); assert.equal(prompts.prompts[0].name, 'feature-investigation');
  const prompt = await client.getPrompt({ name: 'feature-investigation', arguments: { question: '如何处理引用？' } });
  assert.match(prompt.messages[0].content.text, /静态分析/);
  const call = async (name, args) => client.callTool({ name, arguments: args });
  const created = await call('research_create', { title: 'MCP test', question: 'How are references handled?' });
  assert.ok(!created.isError); const study_id = created.structuredContent.id;
  const refused = await call('research_add_claim', { study_id, text: 'No evidence', type: 'fact' }); assert.equal(refused.isError, true);
  const saved = await call('research_add_evidence', { study_id, title: 'Provided observation', kind: 'runtime', source: 'Test fixture', content: 'Displayed no-evidence message' });
  assert.ok(!saved.isError);
  const claim = await call('research_add_claim', { study_id, text: 'Fixture observation', type: 'fact', evidence_ids: [saved.structuredContent.id] }); assert.ok(!claim.isError);
  const report = await call('research_report', { study_id }); assert.match(report.structuredContent.text, /Fixture observation/);
  const list = await call('research_list', {}); assert.equal(list.structuredContent.items.length, 1);
});
