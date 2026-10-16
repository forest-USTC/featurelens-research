#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ResearchService, ResearchStore, ROOT } from '../lib/core.mjs';
import { invoke, toolDefinitions } from '../lib/tools.mjs';

const argv = process.argv.slice(2);
const command = argv.shift() || 'help';
const help = `FeatureLens Research（知微）0.1 · 产品功能研究 CLI / MCP

用法：zhiwei <命令> [--参数 值] [--json]

  create          新建研究：--title 标题 --question 问题 [--target 绝对路径]
  list            研究列表
  get             研究详情：--study-id ID
  analyze         静态分析：--study-id ID [--source-paths '["文件.js"]']
  import-analysis 导入分析：--study-id ID --path /绝对路径/evidence.json
  find-nodes      搜索线索：--study-id ID --analysis-id ID --query 关键词
  capture-node    登记线索：--study-id ID --analysis-id ID --node-id ID --title 标题
  read-source     读取匹配的源码行：--study-id ID --analysis-id ID --node-id ID
  add-evidence    添加材料：--study-id ID --title 标题 --kind static|runtime|document|interview --content 内容 --source 来源
  evidence        查看材料：--study-id ID [--evidence-id ID] [--query 关键词]
  add-claim       记录判断：--study-id ID --type fact|inference|unknown --text 判断 --evidence-ids '["e_ID"]' [--limitation 局限]
  add-verification 创建验证：--study-id ID --question 问题 --steps 步骤 --expected 预期
  record-verification 记录验证：--study-id ID --verification-id ID --status passed|failed|blocked --observed 观察 --evidence-ids '["e_ID"]'
  report          导出研究：--study-id ID [--format markdown|json] [--output /新文件.md]
  doctor          查看 分析引擎 CLI 状态
  demo            创建并分析内置虚构样例，供体验和验证
  mcp             启动 stdio MCP 服务
  mcp-config      输出 MCP 配置示例（不修改客户端）
  tools           列出工具与参数

通用：--input /参数.json 从文件读取参数；--data-dir /目录 切换研究库。
使用 --json 输出结构化结果。没有 HTTP 服务、前端或内置模型 API。
环境变量：ZHIWEI_DATA_DIR、ZHIWEI_ENGINE_BIN（分析引擎启动器绝对路径）。`;

function parse(args) {
  const values = {}; const switches = new Set(['json', 'demo']);
  while (args.length) {
    const key = args.shift(); if (!key.startsWith('--')) throw new Error(`无法识别参数 ${key}，请运行 help`);
    const name = key.slice(2).replaceAll('-', '_');
    if (switches.has(name)) { values[name] = true; continue; }
    if (!args.length || args[0].startsWith('--')) throw new Error(`${key} 缺少值`);
    let value = args.shift();
    if (['offset', 'limit', 'context', 'observation_index'].includes(name)) value = Number(value);
    if (['source_paths', 'evidence_ids', 'claim_ids'].includes(name)) value = JSON.parse(value);
    values[name] = value;
  }
  return values;
}
try {
  if (['help', '--help', '-h'].includes(command)) { console.log(help); process.exit(0); }
  if (['--version', 'version'].includes(command)) { console.log('0.1.0'); process.exit(0); }
  const options = parse(argv); const json = options.json; delete options.json;
  const store = options.data_dir ? new ResearchStore(options.data_dir) : new ResearchStore(); delete options.data_dir;
  const service = new ResearchService({ store });
  if (command === 'mcp') { await (await import('../lib/mcp.mjs')).serve(service); }
  else {
    let result;
    if (command === 'mcp-config') result = { mcpServers: { zhiwei: { command: process.execPath, args: [join(ROOT, 'bin/zhiwei.mjs'), 'mcp'], env: { ZHIWEI_DATA_DIR: store.directory, ZHIWEI_ENGINE_BIN: service.engine } } } };
    else if (command === 'tools') result = toolDefinitions.map(d => ({ name: d.name, description: d.description, parameters: Object.keys(d.shape) }));
    else if (command === 'demo') {
      const s = await service.create({ title: '演示：知识库无引用时如何处理', question: '在这个虚构样例中，没有资料达到阈值时，问答功能返回什么？', target: join(ROOT, 'fixtures/demo-app'), demo: true });
      if (!json) console.error(`演示研究 ${s.id} 已建立，正在运行 静态分析引擎……`);
      const analysis = await service.analyze({ study_id: s.id });
      result = { study_id: s.id, analysis, next: `zhiwei find-nodes --study-id ${s.id} --analysis-id ${analysis.id} --query knowledge --json`, boundary: '虚构样例。没有生成业务结论，也没有执行目标应用。' };
    } else {
      let input = {};
      if (options.input) { input = JSON.parse(await readFile(options.input, 'utf8')); delete options.input; }
      result = await invoke(service, `research_${command.replaceAll('-', '_')}`, { ...input, ...options });
    }
    if (result?.text && command === 'report' && !json) console.log(result.text);
    else console.log(JSON.stringify(result, null, json ? undefined : 2));
  }
} catch (e) { console.error(`知微：${e.message}`); process.exitCode = 1; }
