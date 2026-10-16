import { mkdir, readFile, writeFile, rename, rm, stat, realpath } from 'node:fs/promises';
import { join, resolve, dirname, isAbsolute, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const now = () => new Date().toISOString();
const uid = (prefix) => `${prefix}_${randomUUID().slice(0, 8)}`;
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const clone = (x) => structuredClone(x);
const inside = (root, file) => { const r = relative(root, file); return r !== '..' && !r.startsWith(`..${sep}`) && !isAbsolute(r); };
const assert = (test, message) => { if (!test) throw new Error(message); };
const nonempty = (value, label, max = 10000) => { assert(typeof value === 'string' && value.trim().length && value.length <= max, `${label}不能为空，且不得超过 ${max} 字符`); return value.trim(); };
const idPattern = /^(r|e|a|c|v)_[a-f0-9]{8}$/;
function analysisNodes(evidence) {
  const n = evidence.normalized_result;
  const contexts = new Map((n.semantic_graph?.evidence_contexts || []).map(c => [c.context_id, c]));
  return [
    ...n.graph.nodes.map(node => ({ ...node, graph_layer: 'application' })),
    ...(n.semantic_graph?.nodes || []).map(node => ({ ...node, graph_layer: 'semantic', resolved_evidence_context: contexts.get(node.evidence?.context_id) ?? null })),
  ];
}
function observationsOf(node) {
  if (!node) return [];
  if (node.graph_layer === 'semantic') return [{ label: node.label, properties: node.properties, evidence: { ...node.resolved_evidence_context, ...node.evidence } }];
  return node.observations || [];
}

export class ResearchStore {
  constructor(directory = process.env.ZHIWEI_DATA_DIR || join(ROOT, 'data')) { this.directory = resolve(directory); }
  async init() { await mkdir(join(this.directory, 'raw'), { recursive: true }); }
  async read() {
    await this.init();
    try { return JSON.parse(await readFile(join(this.directory, 'research.json'), 'utf8')); }
    catch (e) { if (e.code === 'ENOENT') return { version: 1, studies: [] }; throw e; }
  }
  async change(fn) {
    await this.init();
    const lock = join(this.directory, '.write-lock');
    let locked = false;
    for (let i = 0; i < 80; i++) {
      try { await mkdir(lock); locked = true; break; }
      catch (e) { if (e.code !== 'EEXIST') throw e; await new Promise(r => setTimeout(r, 50)); }
    }
    assert(locked, `研究库正在写入。若上次进程异常退出，请确认没有其他知微进程，再移除 ${lock} 后重试。`);
    try {
      const db = await this.read();
      const value = await fn(db);
      const temp = join(this.directory, `research.${randomUUID()}.tmp`);
      await writeFile(temp, JSON.stringify(db, null, 2), { mode: 0o600 });
      await rename(temp, join(this.directory, 'research.json'));
      return clone(value);
    } finally { await rm(lock, { recursive: true }); }
  }
  pick(db, id) { assert(idPattern.test(id), '无效的研究 ID'); const s = db.studies.find(x => x.id === id); assert(s, '找不到研究项目'); return s; }
  async get(id) { return this.pick(await this.read(), id); }
  async mutate(id, fn) { return this.change(db => { const s = this.pick(db, id); const value = fn(s); s.updated_at = now(); return value; }); }
}

export class ResearchService {
  constructor({ store = new ResearchStore() } = {}) { this.store = store; }
  async create({ title, question, target, demo = false }) {
    title = nonempty(title, '研究标题', 200); question = nonempty(question, '研究问题', 3000);
    if (target) assert(isAbsolute(target), '目标必须是用户指定的绝对路径');
    const study = { id: uid('r'), title, question, target: target || null, demo, created_at: now(), updated_at: now(), evidence: [], analyses: [], claims: [], verifications: [] };
    await this.store.change(db => { db.studies.push(study); return study; });
    return { ...study, next: '明确研究问题的输入、分支、输出与失败条件。对目标运行 research_analyze，或先 research_add_evidence 记录材料。' };
  }
  async list() { return (await this.store.read()).studies.map(s => ({ id: s.id, title: s.title, question: s.question, demo: s.demo, evidence_count: s.evidence.length, claim_count: s.claims.length, updated_at: s.updated_at })); }
  async get({ study_id }) {
    const s = await this.store.get(study_id);
    return { ...s, evidence: s.evidence.map(e => ({ id: e.id, title: e.title, kind: e.kind, provenance: e.provenance, source: e.source })), boundary: '判断与验证结果由研究者记录。工具检查引用关系，不证明业务结论为真。静态代码不等于运行行为。' };
  }
  async addEvidence({ study_id, title, kind, content, source, limitation = '' }) {
    title = nonempty(title, '证据标题', 300); content = nonempty(content, '证据内容', 60000); source = nonempty(source, '证据来源', 4000);
    assert(['document', 'static', 'runtime', 'interview'].includes(kind), '不支持的证据类型');
    const e = { id: uid('e'), title, kind, content, source, limitation, provenance: 'researcher-supplied', created_at: now(), digest: sha(content) };
    await this.store.mutate(study_id, s => { s.evidence.push(e); return e; });
    return { ...e, note: '已记录研究者提供的材料，尚未独立核验其真实性。' };
  }
  async evidence({ study_id, evidence_id, query = '', offset = 0, limit = 20 }) {
    const s = await this.store.get(study_id);
    if (evidence_id) { const e = s.evidence.find(x => x.id === evidence_id); assert(e, '找不到证据'); return e; }
    const rows = s.evidence.filter(e => JSON.stringify(e).toLowerCase().includes(query.toLowerCase()));
    return { total: rows.length, offset, items: rows.slice(offset, offset + limit), next_offset: offset + limit < rows.length ? offset + limit : null };
  }
  async claim({ study_id, text, type, evidence_ids = [], limitation = '' }) {
    text = nonempty(text, '判断内容', 10000);
    assert(['fact', 'inference', 'unknown'].includes(type), '判断类型必须是 fact、inference 或 unknown');
    assert(type === 'unknown' || evidence_ids.length > 0, '材料事实和分析推断必须引用证据；没有证据请记录为 unknown');
    if (type === 'inference') nonempty(limitation, '推断的局限或待验证条件', 4000);
    return this.store.mutate(study_id, s => {
      for (const id of evidence_ids) assert(s.evidence.some(e => e.id === id), `证据 ${id} 不属于当前研究`);
      const c = { id: uid('c'), text, type, evidence_ids: [...new Set(evidence_ids)], limitation, provenance: 'researcher-authored', created_at: now() };
      s.claims.push(c); return c;
    });
  }
  async verification({ study_id, question, steps, expected, claim_ids = [] }) {
    question = nonempty(question, '验证问题'); steps = nonempty(steps, '验证步骤'); expected = nonempty(expected, '预期结果');
    return this.store.mutate(study_id, s => {
      for (const id of claim_ids) assert(s.claims.some(c => c.id === id), `判断 ${id} 不属于当前研究`);
      const v = { id: uid('v'), question, steps, expected, claim_ids, status: 'pending', attempts: [], created_at: now() };
      s.verifications.push(v); return v;
    });
  }
  async recordVerification({ study_id, verification_id, status, observed, evidence_ids = [] }) {
    assert(['passed', 'failed', 'blocked'].includes(status), '验证结果必须是 passed、failed 或 blocked');
    observed = nonempty(observed, '实际观察或阻塞原因');
    assert(status === 'blocked' || evidence_ids.length > 0, '通过或失败必须附实际证据');
    return this.store.mutate(study_id, s => {
      const v = s.verifications.find(x => x.id === verification_id); assert(v, '找不到验证项');
      for (const id of evidence_ids) assert(s.evidence.some(e => e.id === id), `证据 ${id} 不属于当前研究`);
      v.attempts.push({ status, observed, evidence_ids, recorded_at: now(), provenance: 'researcher-recorded' }); v.status = status;
      return { ...v, note: '已保留验证记录，未自动改变任何判断的类型。' };
    });
  }
  async importAnalysis({ study_id, path }) {
    assert(isAbsolute(path), '导入文件需要绝对路径');
    assert((await stat(path)).size <= 64 * 1024 * 1024, '导入文件超过 64 MiB，请先缩小分析范围');
    const bytes = await readFile(path); const envelope = JSON.parse(bytes);
    return this.retainAnalysis(study_id, envelope, bytes, 'imported');
  }
  async retainAnalysis(studyId, envelope, bytes, origin) {
    const e = envelope?.evidence_id ? envelope : envelope?.result?.evidence_id ? envelope.result : null;
    assert(e && e.operation === 'analyze_javascript_application' && Array.isArray(e.normalized_result?.graph?.nodes), '需要 analyze_javascript_application 的完整 Evidence JSON；无法识别或内容被截断');
    const digest = sha(bytes);
    const existing = (await this.store.get(studyId)).analyses.find(a => a.sha256 === digest);
    if (existing) return { ...existing, reused: true };
    const id = uid('a'); const file = join(this.store.directory, 'raw', `${id}.json`);
    await this.store.init(); await writeFile(file, bytes, { flag: 'wx', mode: 0o600 });
    const n = e.normalized_result;
    const analysis = { id, origin, evidence_id: e.evidence_id, sha256: digest, operation: e.operation, subject: e.subject, provider: e.provider, node_count: n.graph.nodes.length, semantic_node_count: n.semantic_graph?.nodes?.length ?? 0, edge_count: n.graph.edges?.length ?? 0, statistics: n.statistics ?? null, limitations: [...new Set([...(e.limitations ?? []), ...(n.limitations ?? [])])], coverage: n.graph.coverage ?? null, raw_file: file, created_at: now() };
    await this.store.mutate(studyId, s => { s.analyses.push(analysis); return analysis; });
    return { ...analysis, next: '用 research_find_nodes 按术语检索线索，再用 research_capture_node 将选定线索保存为证据。节点只是静态线索，不等于功能已经执行。' };
  }
  async analysisDocument(studyId, analysisId) {
    const s = await this.store.get(studyId); const a = s.analyses.find(x => x.id === analysisId); assert(a, '找不到分析记录');
    const bytes = await readFile(a.raw_file); assert(sha(bytes) === a.sha256, '原始分析文件内容已变化，不能继续沿用原证据身份');
    const envelope = JSON.parse(bytes); return { s, a, evidence: envelope.evidence_id ? envelope : envelope.result };
  }
  async findNodes({ study_id, analysis_id, query = '', offset = 0, limit = 15, node_id }) {
    const { a, evidence } = await this.analysisDocument(study_id, analysis_id);
    let nodes = analysisNodes(evidence);
    if (node_id) { const n = nodes.find(n => n.node_id === node_id); assert(n, '节点不存在'); return { analysis_id, node: n, boundary: '仅为静态分析线索，未知与覆盖限制见节点 observations[].evidence' }; }
    nodes = nodes.filter(n => JSON.stringify(n).toLowerCase().includes(query.toLowerCase()));
    return { analysis_id, total: nodes.length, offset, items: nodes.slice(offset, offset + limit).map(n => ({ node_id: n.node_id, kind: n.kind, graph_layer: n.graph_layer, observations: observationsOf(n).slice(0, 3).map(o => ({ label: o.label, properties: o.properties, location: o.evidence?.location, limitations: o.evidence?.limitations })), observation_count: observationsOf(n).length })), next_offset: offset + limit < nodes.length ? offset + limit : null, analysis_limitations: a.limitations };
  }
  async captureNode({ study_id, analysis_id, node_id, title }) {
    const { a, evidence } = await this.analysisDocument(study_id, analysis_id);
    const node = analysisNodes(evidence).find(n => n.node_id === node_id); assert(node, '节点不存在');
    const item = { id: uid('e'), title: nonempty(title, '证据标题', 300), kind: 'static', content: JSON.stringify(node, null, 2), source: `${a.subject?.local_path || a.subject?.name || 'artifact'} · ${node_id}`, provenance: 'analyzer-output', analysis_id, parent_evidence_id: a.evidence_id, node_id, created_at: now(), digest: sha(JSON.stringify(node)), limitation: '静态分析线索；未观察实际执行。节点原始覆盖边界已保留。' };
    return this.store.mutate(study_id, s => { const old = s.evidence.find(e => e.analysis_id === analysis_id && e.node_id === node_id); if (old) return old; s.evidence.push(item); return item; });
  }
  async readSource({ study_id, analysis_id, node_id, observation_index = 0, context = 3 }) {
    const { s, a, evidence } = await this.analysisDocument(study_id, analysis_id);
    assert(s.target && a.origin === 'local-run', '只允许读取当前研究明确指定、由本工具实际分析的目标；导入的 JSON 不能授权读取本地路径');
    const node = analysisNodes(evidence).find(n => n.node_id === node_id);
    const o = observationsOf(node)[observation_index]; const loc = o?.evidence?.location?.value;
    assert(loc?.kind === 'source-range' && loc.source && Number.isInteger(loc.start?.line), '该线索没有可读的源码行位置');
    const root = await realpath(s.target); assert((await stat(root)).isDirectory() && !root.endsWith('.app'), '当前源码读取支持已解包的目录。ASAR / .app 请使用原始节点证据或另行明确解包目标');
    const file = await realpath(resolve(root, loc.source)); assert(inside(root, file), '证据位置超出选定目标目录');
    assert((await stat(file)).size < 16 * 1024 * 1024, '源文件超过 16 MiB，暂不直接读取');
    const bytes = await readFile(file); const actual = sha(bytes); const expected = o.evidence?.artifact?.sha256;
    assert(expected && actual === expected, '源文件缺少可校验身份或已在分析后改变，请重新分析');
    const lines = bytes.toString('utf8').split('\n'); const start = Math.max(1, loc.start.line - context); const end = Math.min(lines.length, (loc.end?.line || loc.start.line) + context, start + 99);
    const selected = lines.slice(start - 1, end).map((l, i) => `${start + i}: ${l}`).join('\n');
    return { source: file, sha256: actual, start_line: start, end_line: end, text: selected.slice(0, 30000), truncated: selected.length > 30000 || end < (loc.end?.line || loc.start.line), authority: 'source-text', boundary: '源码文本，不证明目标曾执行这条分支。' };
  }
  async analyze({ study_id, source_paths = [] }, { signal } = {}) {
    const s = await this.store.get(study_id); assert(s.target, '研究尚未指定目标，请新建带 target 的研究，或导入已有分析 JSON');
    const target = await realpath(s.target);
    for (const p of source_paths) assert(!isAbsolute(p) && !p.split(/[\\/]/).includes('..') && p.length < 4000, 'source_paths 只能包含目标内的相对路径');
    const result = await runCommand(process.execPath, ['--max-old-space-size=512', join(ROOT, 'lib/analyzer.mjs'), target, JSON.stringify(source_paths)], { timeout: 180000, maxBytes: 64 * 1024 * 1024, signal });
    if (result.code !== 0) {
      let detail;
      try { const e = JSON.parse(result.stdout); detail = JSON.stringify({ code: e.code, message: e.message, remediation: e.remediation, cleanup_reason: e.details?.cleanup_reason, diagnostics: e.details?.diagnostics?.reason }); } catch {}
      throw new Error(`分析引擎运行失败（${result.code}）：${detail || result.stderr.slice(-4000) || result.stdout.slice(-2000)}`);
    }
    let data; try { data = JSON.parse(result.stdout); } catch { throw new Error('分析引擎未返回完整 JSON；未生成任何业务结论'); }
    return this.retainAnalysis(study_id, data, Buffer.from(result.stdout), 'local-run');
  }
  async report({ study_id, format = 'markdown', output }) {
    const s = await this.store.get(study_id);
    const text = format === 'json' ? JSON.stringify(s, null, 2) : markdownReport(s);
    if (output) {
      assert(isAbsolute(output), '导出位置必须是绝对路径');
      await writeFile(output, text, { flag: 'wx', mode: 0o600 });
      return { path: output, format, bytes: Buffer.byteLength(text), note: '已导出；导出文件可能含本地路径和材料原文，分享前请检查。' };
    }
    return { format, text };
  }
  async doctor() {
    return { name: '知微', version: '0.1.0', node: process.version, data_directory: this.store.directory, engine: { name: 'featurelens-acorn', builtin: true, available: true }, interface: ['cli', 'mcp-stdio'], analysis: ['unpacked-javascript-directory'], model: '由 MCP 客户端提供，本工具不调用模型 API', note: '内置语法扫描，不执行目标；不支持直接分析 ASAR、.app、TypeScript 或 JSX。' };
  }
}

export function runCommand(command, args, { timeout = 10000, maxBytes = 1024 * 1024, signal } = {}) {
  return new Promise((resolveResult, reject) => {
    if (signal?.aborted) return reject(new Error('操作已取消'));
    const child = spawn(command, args, { shell: false, stdio: ['ignore', 'pipe', 'pipe'], detached: process.platform !== 'win32' });
    let stdout = '', stderr = '', size = 0, failure = null, forceTimer;
    const kill = (reason) => {
      if (failure) return; failure = reason;
      const stop = (sig) => { try { if (process.platform !== 'win32' && child.pid) process.kill(-child.pid, sig); else child.kill(sig); } catch {} };
      stop('SIGTERM'); forceTimer = setTimeout(() => stop('SIGKILL'), 1500); forceTimer.unref();
    };
    const timer = setTimeout(() => kill('分析超时，已终止本次分析进程；请缩小文件范围后重试'), timeout);
    const cancel = () => kill('操作已取消'); signal?.addEventListener('abort', cancel, { once: true });
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', data => { size += Buffer.byteLength(data); if (size > maxBytes) kill('结果超过 64 MiB 限制，请使用 source_paths 缩小范围'); else stdout += data; });
    child.stderr.on('data', data => { stderr = (stderr + data).slice(-32000); });
    const cleanup = () => { clearTimeout(timer); clearTimeout(forceTimer); signal?.removeEventListener('abort', cancel); };
    child.on('error', e => { cleanup(); reject(e); });
    child.on('close', code => { cleanup(); if (failure) reject(new Error(failure)); else resolveResult({ code, stdout, stderr }); });
  });
}

export function markdownReport(s) {
  const labels = { fact: '材料事实（研究者判断）', inference: '分析推断', unknown: '待确认', pending: '待执行', passed: '研究者记录通过', failed: '研究者记录失败', blocked: '阻塞' };
  const lines = [`# ${s.title}`, '', ...(s.demo ? ['> 演示研究：使用虚构样例，不代表真实产品行为。', ''] : []), `研究问题：${s.question}`, '', `目标：${s.target || '未指定'}`, `研究 ID：${s.id}`, `更新时间：${s.updated_at}`, '', '> 本报告由证据与研究者记录汇编。静态分析不证明运行行为；引用存在不证明判断正确。', '', '## 判断与待确认事项', ''];
  if (!s.claims.length) lines.push('尚未形成判断。');
  for (const c of s.claims) lines.push(`### ${c.id} · ${labels[c.type]}`, '', c.text, '', `依据：${c.evidence_ids.join('、') || '尚无证据'}`, ...(c.limitation ? [`局限：${c.limitation}`] : []), '');
  lines.push('## 验证记录', '');
  if (!s.verifications.length) lines.push('尚未建立验证项。');
  for (const v of s.verifications) {
    lines.push(`### ${v.id} · ${v.question}`, '', `状态：${labels[v.status]}`, `步骤：${v.steps}`, `预期：${v.expected}`, `关联判断：${v.claim_ids.join('、') || '无'}`, '');
    for (const a of v.attempts) lines.push(`- ${a.recorded_at} · ${labels[a.status]}：${a.observed}（依据：${a.evidence_ids.join('、') || '无'}）`);
    lines.push('');
  }
  lines.push('## 证据目录', '');
  for (const e of s.evidence) lines.push(`### ${e.id} · ${e.title}`, '', `类型：${e.kind}；来源方式：${e.provenance}`, `来源：${e.source}`, `内容摘要哈希：${e.digest}`, ...(e.parent_evidence_id ? [`分析 Evidence：${e.parent_evidence_id}`] : []), '', ...e.content.split('\n').map(l => `> ${l}`), '', `局限：${e.limitation || '研究者未填写，需自行评估'}`, '');
  lines.push('## 分析范围与局限', '');
  for (const a of s.analyses) lines.push(`- ${a.id}：${a.origin}，${a.node_count} 个静态节点；原始 Evidence：${a.evidence_id}；JSON SHA-256：${a.sha256}`, `  局限：${JSON.stringify(a.limitations)}`);
  if (!s.analyses.length) lines.push('未执行或导入工具分析。');
  return lines.join('\n') + '\n';
}
