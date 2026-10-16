// Syntax-only analysis. Target files are read as text, never imported or executed.
import { readdir, readFile, lstat, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute, sep, extname } from 'node:path';
import { createHash } from 'node:crypto';
import { parse } from 'acorn';
import { fileURLToPath } from 'node:url';

const hash = data => createHash('sha256').update(data).digest('hex');
const within = (root, file) => { const r = relative(root, file); return r !== '..' && !r.startsWith(`..${sep}`) && !isAbsolute(r); };
const excluded = new Set(['node_modules', '.git', 'data', 'artifacts', 'coverage']);
const extensions = new Set(['.js', '.mjs', '.cjs']);
export async function analyzeDirectory(target, selected = []) {
  const root = await realpath(target);
  if (!(await lstat(root)).isDirectory() || root.endsWith('.app')) throw new Error('内置分析器只支持已解包的 JavaScript 目录；请先自行解包 .app / ASAR');
  const files = new Set(); const skipped = []; let visited = 0;
  async function collect(file, explicit = false) {
    if (++visited > 20000) throw new Error('目录超过 20,000 个条目，请用 source_paths 缩小范围');
    if (!within(root, file)) throw new Error('source_paths 超出选定目标');
    const info = await lstat(file);
    if (info.isSymbolicLink()) { skipped.push({ source: relative(root, file), reason: 'symbolic-link' }); return; }
    if (info.isDirectory()) {
      for (const entry of (await readdir(file)).sort()) if (!excluded.has(entry)) await collect(resolve(file, entry));
    } else if (info.isFile() && extensions.has(extname(file))) {
      const actual = await realpath(file);
      if (!within(root, actual)) throw new Error('文件路径超出选定目标');
      files.add(actual);
      if (files.size > 1000) throw new Error('超过 1,000 个 JS 文件，请用 source_paths 缩小范围');
    } else if (explicit) throw new Error('指定文件不是支持的 .js / .mjs / .cjs 文件');
  }
  if (selected.length) {
    for (const p of selected) {
      if (isAbsolute(p) || p.split(/[\\/]/).includes('..')) throw new Error('source_paths 只能包含目标内的相对路径');
      const file = resolve(root, p);
      if (!within(root, await realpath(file))) throw new Error('source_paths 超出选定目标');
      await collect(file, true);
    }
  } else await collect(root);
  const nodes = [], semantic = [], contexts = [], edges = [];
  const limitations = ['仅提取语法节点；不执行目标，不解析调用目标或跨文件数据流，不证明运行行为。', '只解析标准 JavaScript；不支持 TypeScript、JSX、ASAR 或原生二进制。'];
  let totalBytes = 0, parsed = 0;
  for (const file of files) {
    const source = relative(root, file);
    const size = (await lstat(file)).size;
    if (size > 2 * 1024 * 1024) { skipped.push({ source, reason: 'file exceeds 2 MiB' }); continue; }
    totalBytes += size;
    if (totalBytes > 32 * 1024 * 1024) throw new Error('源码总量超过 32 MiB，请缩小范围');
    const bytes = await readFile(file), text = bytes.toString('utf8'), digest = hash(bytes);
    let ast;
    try { ast = parse(text, { ecmaVersion: 'latest', sourceType: 'module', locations: true, allowHashBang: true }); }
    catch {
      try { ast = parse(text, { ecmaVersion: 'latest', sourceType: 'script', locations: true, allowHashBang: true }); }
      catch (error) { skipped.push({ source, reason: `parse-error: ${error.message}` }); continue; }
    }
    parsed++;
    const context_id = `ctx_${hash(source).slice(0, 16)}`;
    contexts.push({ context_id, artifact: { sha256: digest }, limitations });
    const evidence = node => ({ context_id, artifact: { sha256: digest }, location: { value: { kind: 'source-range', source, start: node.loc.start, end: node.loc.end } }, limitations });
    const fileId = `file_${hash(source).slice(0, 16)}`;
    nodes.push({ node_id: fileId, kind: 'file', observations: [{ label: source, evidence: evidence(ast) }] });
    const queue = [{ node: ast, parent: null }];
    while (queue.length) {
      const { node, parent } = queue.pop();
      let kind, label;
      if (['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression'].includes(node.type)) {
        kind = 'function'; label = node.id?.name || parent?.id?.name || parent?.key?.name || '(anonymous)';
      } else if (node.type === 'CallExpression' || node.type === 'NewExpression') { kind = 'call'; label = text.slice(node.callee.start, node.callee.end); }
      else if (node.type === 'ImportDeclaration') { kind = 'import'; label = node.source.value; }
      else if (node.type === 'IfStatement' || node.type === 'ConditionalExpression') { kind = 'branch'; label = text.slice(node.test.start, node.test.end); }
      else if (node.type === 'ReturnStatement') { kind = 'return'; label = node.argument ? text.slice(node.argument.start, node.argument.end) : 'return'; }
      if (kind) {
        if (semantic.length >= 20000) throw new Error('超过 20,000 个语法节点，请缩小范围');
        const node_id = `syntax_${hash(`${source}:${node.start}:${node.type}`).slice(0, 20)}`;
        semantic.push({ node_id, kind, label: String(label).slice(0, 300), properties: { syntax_type: node.type, excerpt: text.slice(node.start, Math.min(node.end, node.start + 600)) }, evidence: evidence(node) });
        edges.push({ source: fileId, target: node_id, kind: 'contains' });
      }
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) { for (let i = value.length - 1; i >= 0; i--) if (value[i]?.type) queue.push({ node: value[i], parent: node }); }
        else if (value?.type) queue.push({ node: value, parent: node });
      }
    }
  }
  if (!parsed) throw new Error(`没有成功解析的 JavaScript 文件：${JSON.stringify(skipped).slice(0, 2000)}`);
  if (skipped.length) limitations.push('存在跳过或解析失败的条目；详见 statistics.skipped，结果不是完整覆盖。');
  const normalized_result = { graph: { nodes, edges, coverage: { complete: false, selected_paths: selected, scope: 'syntax-only' } }, semantic_graph: { nodes: semantic, evidence_contexts: contexts }, statistics: { parsed_javascript_files: parsed, skipped }, limitations };
  return { evidence_id: `ev_${hash(JSON.stringify(normalized_result)).slice(0, 24)}`, operation: 'analyze_javascript_application', subject: { local_path: root }, provider: 'featurelens-acorn', normalized_result, limitations };
}

if (process.argv[1] && await realpath(process.argv[1]).catch(() => '') === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(await analyzeDirectory(process.argv[2], JSON.parse(process.argv[3] || '[]')))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
