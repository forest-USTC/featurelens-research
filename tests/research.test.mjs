import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { ResearchService, ResearchStore, runCommand, ROOT } from '../lib/core.mjs';
import { invoke } from '../lib/tools.mjs';

async function fixture(t) {
  const directory = await mkdtemp(join(tmpdir(), 'zhiwei-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const service = new ResearchService({ store: new ResearchStore(directory) });
  const study = await service.create({ title: '测试研究', question: '资料不足时发生什么？' });
  return { directory, service, study };
}
test('requires same-study evidence and explicitly bounded inference', async t => {
  const { service, study } = await fixture(t);
  await assert.rejects(service.claim({ study_id: study.id, type: 'fact', text: '没有证据的事实' }), /必须引用/);
  const other = await service.create({ title: '另一个研究', question: '其他问题' });
  const e = await service.addEvidence({ study_id: other.id, title: '片段', kind: 'static', content: 'return []', source: '手工片段' });
  await assert.rejects(service.claim({ study_id: study.id, type: 'fact', text: '跨研究引用', evidence_ids: [e.id] }), /不属于/);
  await assert.rejects(service.claim({ study_id: other.id, type: 'inference', text: '推断', evidence_ids: [e.id] }), /局限/);
  await service.claim({ study_id: study.id, type: 'unknown', text: '运行时是否拒答仍未知' });
  assert.equal((await service.get({ study_id: study.id })).claims[0].type, 'unknown');
});
test('verification requires evidence, preserves attempts and does not upgrade claims', async t => {
  const { service, study } = await fixture(t);
  const c = await service.claim({ study_id: study.id, text: '实际输出未知', type: 'unknown' });
  const v = await service.verification({ study_id: study.id, question: '实际输出？', steps: '输入不存在的资料', expected: '提示资料不足', claim_ids: [c.id] });
  await assert.rejects(service.recordVerification({ study_id: study.id, verification_id: v.id, status: 'passed', observed: '正常' }), /附实际证据/);
  await service.recordVerification({ study_id: study.id, verification_id: v.id, status: 'blocked', observed: '尚未获取运行权限' });
  const e = await service.addEvidence({ study_id: study.id, title: '人工测试记录', kind: 'runtime', content: '观察到资料不足', source: '测试人员提供' });
  await service.recordVerification({ study_id: study.id, verification_id: v.id, status: 'passed', observed: '返回资料不足', evidence_ids: [e.id] });
  const updated = await service.get({ study_id: study.id });
  assert.equal(updated.verifications[0].attempts.length, 2);
  assert.equal(updated.claims[0].type, 'unknown');
  const report = await service.report({ study_id: study.id });
  assert.match(report.text, /研究者记录通过/); assert.match(report.text, /待确认/);
});
test('concurrent writers preserve updates across store instances', async t => {
  const { service, study, directory } = await fixture(t);
  await Promise.all(Array.from({ length: 12 }, (_, i) => new ResearchService({ store: new ResearchStore(directory) }).claim({ study_id: study.id, type: 'unknown', text: `未知 ${i}` })));
  assert.equal((await service.get({ study_id: study.id })).claims.length, 12);
});
test('reports do not overwrite files and strict schemas reject invalid paging', async t => {
  const { service, study, directory } = await fixture(t);
  const output = join(directory, 'report.md'); await writeFile(output, 'keep');
  await assert.rejects(service.report({ study_id: study.id, output }), /EEXIST/);
  assert.equal(await readFile(output, 'utf8'), 'keep');
  await assert.rejects(invoke(service, 'research_evidence', { study_id: study.id, limit: -1 }));
  await assert.rejects(invoke(service, 'research_create', { title: 'x', question: 'x', arbitrary: true }));
});
test('imports retain exact bytes, refuse forged source access and detect later tampering', async t => {
  const { service, study, directory } = await fixture(t);
  const path = join(directory, 'analysis.json');
  const doc = { evidence_id: 'ev_test', operation: 'analyze_javascript_application', normalized_result: { graph: { nodes: [{ node_id: 'n_1', kind: 'file', observations: [] }], edges: [] } }, limitations: ['fixture only'] };
  await writeFile(path, JSON.stringify(doc));
  const a = await service.importAnalysis({ study_id: study.id, path });
  const again = await service.importAnalysis({ study_id: study.id, path }); assert.equal(again.id, a.id);
  const e = await service.captureNode({ study_id: study.id, analysis_id: a.id, node_id: 'n_1', title: '片段' });
  const duplicate = await service.captureNode({ study_id: study.id, analysis_id: a.id, node_id: 'n_1', title: '重复' }); assert.equal(e.id, duplicate.id);
  await assert.rejects(service.readSource({ study_id: study.id, analysis_id: a.id, node_id: 'n_1' }), /只允许读取/);
  await writeFile(a.raw_file, '{}');
  await assert.rejects(service.findNodes({ study_id: study.id, analysis_id: a.id }), /内容已变化/);
});
test('process runner times out and supports cancellation without spawning a shell', async () => {
  await assert.rejects(runCommand(process.execPath, ['-e', 'setInterval(()=>{}, 1000)'], { timeout: 40 }), /超时/);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(runCommand(process.execPath, ['-e', 'console.log(1)'], { signal: controller.signal }), /取消/);
});
test('semantic evidence resolves its context and source reads reject changes and traversal', async t => {
  const { service, directory } = await fixture(t);
  const s = await service.create({ title: '源码定位', question: '函数有什么行为', target: directory });
  const content = 'export function answer() { return 42; }';
  const digest = createHash('sha256').update(content).digest('hex');
  await writeFile(join(directory, 'sample.js'), content);
  const doc = { evidence_id: 'ev_semantic', operation: 'analyze_javascript_application', normalized_result: { graph: { nodes: [], edges: [] }, semantic_graph: { evidence_contexts: [{ context_id: 'ctx1', artifact: { sha256: digest }, limitations: ['synthetic fixture'] }], nodes: [{ node_id: 'fn1', kind: 'function', label: 'answer', evidence: { context_id: 'ctx1', location: { value: { kind: 'source-range', source: 'sample.js', start: { line: 1 }, end: { line: 1 } } } } }] } } };
  const a = await service.retainAnalysis(s.id, doc, Buffer.from(JSON.stringify(doc)), 'local-run');
  const found = await service.findNodes({ study_id: s.id, analysis_id: a.id, query: 'answer' });
  assert.equal(found.items[0].graph_layer, 'semantic');
  const source = await service.readSource({ study_id: s.id, analysis_id: a.id, node_id: 'fn1' }); assert.match(source.text, /return 42/);
  const capture = await service.captureNode({ study_id: s.id, analysis_id: a.id, node_id: 'fn1', title: '语义节点' }); assert.match(capture.content, /synthetic fixture/);
  await writeFile(join(directory, 'sample.js'), 'changed');
  await assert.rejects(service.readSource({ study_id: s.id, analysis_id: a.id, node_id: 'fn1' }), /已在分析后改变/);
  doc.normalized_result.semantic_graph.nodes[0].evidence.location.value.source = '../outside.js';
  const b = await service.retainAnalysis(s.id, doc, Buffer.from(JSON.stringify(doc)), 'local-run');
  // Existing file outside the selected target must not be read even if named by a node.
  const outside = join(directory, '..', `outside-${s.id}.js`); await writeFile(outside, content); t.after(() => rm(outside));
  doc.normalized_result.semantic_graph.nodes[0].evidence.location.value.source = `../outside-${s.id}.js`;
  const c = await service.retainAnalysis(s.id, doc, Buffer.from(JSON.stringify(doc)), 'local-run');
  await assert.rejects(service.readSource({ study_id: s.id, analysis_id: c.id, node_id: 'fn1' }), /超出选定/);
});
test('CLI uses the same research and validation rules', async t => {
  const { directory } = await fixture(t);
  const args = [join(ROOT, 'bin/zhiwei.mjs'), 'create', '--title', 'CLI test', '--question', 'empty references?', '--data-dir', directory, '--json'];
  const run = await runCommand(process.execPath, args); assert.equal(run.code, 0);
  const created = JSON.parse(run.stdout); assert.match(created.id, /^r_/);
  const result = await runCommand(process.execPath, [join(ROOT, 'bin/zhiwei.mjs'), 'add-claim', '--study-id', created.id, '--type', 'fact', '--text', 'unsupported', '--data-dir', directory]);
  assert.equal(result.code, 1); assert.match(result.stderr, /必须引用/);
});
