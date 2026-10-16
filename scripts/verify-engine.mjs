import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import assert from 'node:assert/strict';
import { ROOT } from '../lib/core.mjs';
import { answerQuestion } from '../fixtures/demo-app/retrieval.js';

// This script intentionally executes only the authored pure-function fixture.
// It does not launch Electron or execute a third-party target.
const dir = await mkdtemp(join(tmpdir(), 'zhiwei-engine-'));
const transport = new StdioClientTransport({ command: process.execPath, args: [join(ROOT, 'bin/zhiwei.mjs'), 'mcp', '--data-dir', dir], stderr: 'pipe' });
const client = new Client({ name: 'zhiwei-engine-verification', version: '0.1.0' });
async function call(name, args) {
  const result = await client.callTool({ name, arguments: args }, { timeout: 200000 });
  if (result.isError) throw new Error(result.content.map(c => c.text).join('\n'));
  return result.structuredContent;
}
try {
  await client.connect(transport);
  const s = await call('research_create', { title: '演示：无匹配资料的问答行为', question: '在内置虚构样例中，没有匹配资料时如何返回？静态判断能否被函数测试支持？', target: join(ROOT, 'fixtures/demo-app'), demo: true });
  const a = await call('research_analyze', { study_id: s.id, source_paths: ['retrieval.js'] });
  assert.ok(a.statistics.parsed_javascript_files >= 1);
  const found = await call('research_find_nodes', { study_id: s.id, analysis_id: a.id, query: 'answerQuestion', limit: 50 });
  const fn = found.items.find(n => n.kind === 'function' && n.graph_layer === 'semantic'); assert.ok(fn);
  const e = await call('research_capture_node', { study_id: s.id, analysis_id: a.id, node_id: fn.node_id, title: 'answerQuestion 静态函数节点' });
  const source = await call('research_read_source', { study_id: s.id, analysis_id: a.id, node_id: fn.node_id });
  assert.match(source.text, /score >= 0.7/);
  const sourceEvidence = await call('research_add_evidence', { study_id: s.id, title: '经哈希核对的样例函数源码', kind: 'static', content: source.text, source: `${source.source} · SHA-256 ${source.sha256}`, limitation: '仅证明源码包含该分支，尚不证明 Electron 界面行为。' });
  const c = await call('research_add_claim', { study_id: s.id, type: 'fact', text: '样例源码先筛选 score >= 0.7 的资料，保留前 5 条；无引用时返回 no-evidence。', evidence_ids: [e.id, sourceEvidence.id], limitation: '这是虚构样例的源码判断，不是任何真实产品的结论。' });
  const v = await call('research_add_verification', { study_id: s.id, question: '纯函数对空资料、低分资料和阈值资料的返回是否与源码判断一致？', steps: '分别以空数组、score=0.6、score=0.7 和 8 条合格资料调用仓库内的 answerQuestion 纯函数。', expected: '前两种返回 no-evidence；阈值资料返回 ready；合格资料最多返回 5 条引用。', claim_ids: [c.id] });
  const cases = [[], [{ id: 'low', score: 0.6 }], [{ id: 'boundary', score: 0.7 }], Array.from({ length: 8 }, (_, i) => ({ id: `d${i}`, score: 1 }))];
  const observations = cases.map(documents => ({ input: { question: '演示问题', documents }, output: answerQuestion('演示问题', documents) }));
  assert.equal(observations[0].output.status, 'no-evidence'); assert.equal(observations[1].output.status, 'no-evidence'); assert.equal(observations[2].output.status, 'ready'); assert.equal(observations[3].output.citations.length, 5);
  const runtime = await call('research_add_evidence', { study_id: s.id, title: '内置纯函数的 4 组实际测试结果', kind: 'runtime', content: JSON.stringify(observations, null, 2), source: 'scripts/verify-engine.mjs，Node.js 直接调用作者编写的 fixtures/demo-app/retrieval.js', limitation: '只测试内置纯函数；没有启动 Electron，也未检查 IPC、UI 或网络。' });
  await call('research_record_verification', { study_id: s.id, verification_id: v.id, status: 'passed', observed: '4 组断言全部通过。范围仅限内置纯函数，不代表完整应用链路。', evidence_ids: [runtime.id] });
  await call('research_add_claim', { study_id: s.id, type: 'unknown', text: '完整 Electron 界面是否展示该结果、IPC 是否被实际调用，尚未执行验证。' });
  await mkdir(join(ROOT, 'artifacts'), { recursive: true });
  const output = join(ROOT, 'artifacts', `demo-report-${s.id}.md`);
  await call('research_report', { study_id: s.id, output });
  const summary = { success: true, interface: 'actual MCP stdio', study_id: s.id, analysis_id: a.id, study_directory: dir, report: output, parsed_files: a.statistics.parsed_javascript_files, source_selection: ['retrieval.js'], source_digest_verified: source.sha256, pure_function_assertions: 4, limits: 'Synthetic fixture; no Electron app or real product was executed.' };
  await writeFile(join(ROOT, 'artifacts', 'engine-verification.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
} finally { await client.close(); }
