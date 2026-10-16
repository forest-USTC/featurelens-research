import { z } from 'zod';
const text = (max = 10000) => z.string().trim().min(1).max(max);
const id = z.string().regex(/^[reacv]_[a-f0-9]{8}$/);
const study = { study_id: id.describe('研究 ID，由 research_create 返回') };
const page = { offset: z.number().int().min(0).default(0), limit: z.number().int().min(1).max(50).default(15) };
const ids = z.array(id).max(100).default([]);
const schema = (shape) => z.object(shape).strict();

export const toolDefinitions = [
  { name: 'research_create', method: 'create', description: '建立产品功能研究，保存用户的具体问题和明确选择的目标。target 为可选的本地应用目录、Electron .app 或 .asar 绝对路径；不自动寻找其他应用。', shape: { title: text(200), question: text(3000), target: text(4000).optional(), demo: z.boolean().default(false) } },
  { name: 'research_list', method: 'list', readOnly: true, description: '列出本地研究项目及材料数量。', shape: {} },
  { name: 'research_get', method: 'get', readOnly: true, description: '查看研究问题、判断、验证记录、分析范围和证据目录；完整证据使用 research_evidence 读取。', shape: study },
  { name: 'research_analyze', method: 'analyze', description: '对当前研究明确指定的 JavaScript/Electron 目标运行 静态分析引擎，保存完整原始 Evidence。最多 180 秒、64 MiB 输出，单文件 512 MiB 堆。只分析代码，不执行目标。大应用优先提供 source_paths 缩小范围。不会自动产生业务结论。', shape: { ...study, source_paths: z.array(text(4000)).max(30).default([]) } },
  { name: 'research_import_analysis', method: 'importAnalysis', description: '导入用户选择的完整 兼容的 JavaScript 分析 Evidence JSON，最多 64 MiB；导入文件不授权读取其内部引用的本地路径。', shape: { ...study, path: text(4000) } },
  { name: 'research_find_nodes', method: 'findNodes', readOnly: true, description: '按字面关键词搜索完整静态分析图并分页；query 不是语义搜索。指定 node_id 可读取完整节点及覆盖限制。节点不等于实际运行行为。', shape: { ...study, analysis_id: id, query: z.string().max(300).default(''), ...page, node_id: text(300).optional() } },
  { name: 'research_capture_node', method: 'captureNode', description: '将已选择的静态节点登记成可引用证据，保留原始 Evidence ID、节点 ID 与哈希。同一节点重复登记会复用证据。', shape: { ...study, analysis_id: id, node_id: text(300), title: text(300) } },
  { name: 'research_read_source', method: 'readSource', readOnly: true, description: '读取静态线索对应的少量源码行，先核对文件哈希。仅支持本工具实际分析过的、用户指定的已解包目录，拒绝路径越界和文件变更。', shape: { ...study, analysis_id: id, node_id: text(300), observation_index: z.number().int().min(0).default(0), context: z.number().int().min(0).max(15).default(3) } },
  { name: 'research_add_evidence', method: 'addEvidence', description: '保存研究者提供的资料、静态代码、运行观察或访谈记录。必须写明来源；工具不会把提交的文字当成已独立核验的事实。', shape: { ...study, title: text(300), kind: z.enum(['document', 'static', 'runtime', 'interview']), content: text(60000), source: text(4000), limitation: z.string().max(4000).default('') } },
  { name: 'research_evidence', method: 'evidence', readOnly: true, description: '按 ID 查看证据，或按字面关键词检索研究内已登记的证据并分页。', shape: { ...study, evidence_id: id.optional(), query: z.string().max(300).default(''), ...page } },
  { name: 'research_add_claim', method: 'claim', description: '记录研究者的材料事实 fact、分析推断 inference 或待确认事项 unknown。fact/inference 必须引用本研究证据；inference 必须说明局限。引用检查不证明结论正确。', shape: { ...study, text: text(), type: z.enum(['fact', 'inference', 'unknown']), evidence_ids: ids, limitation: z.string().max(4000).default('') } },
  { name: 'research_add_verification', method: 'verification', description: '为待确认问题创建可执行的验证项，包含步骤、预期结果和关联判断；此工具只登记计划，不执行目标。', shape: { ...study, question: text(), steps: text(), expected: text(), claim_ids: ids } },
  { name: 'research_record_verification', method: 'recordVerification', description: '记录人工验证的实际观察与通过/失败/阻塞状态。通过和失败必须引用证据；保留历次尝试，不自动升级任何判断。', shape: { ...study, verification_id: id, status: z.enum(['passed', 'failed', 'blocked']), observed: text(), evidence_ids: ids } },
  { name: 'research_report', method: 'report', description: '汇编带引用和局限的 Markdown 或 JSON 报告。默认返回内容；指定 output 绝对路径时写入新文件，不覆盖现有文件。报告是研究记录，不是模型自动核验。', shape: { ...study, format: z.enum(['markdown', 'json']).default('markdown'), output: text(4000).optional() } },
  { name: 'research_doctor', method: 'doctor', readOnly: true, description: '检查本工具版本、数据目录和 分析引擎 CLI 是否可启动，不修改配置，不检查或安装原生反编译引擎。', shape: {} },
].map(d => ({ ...d, schema: schema(d.shape) }));

export async function invoke(service, name, input, context = {}) {
  const tool = toolDefinitions.find(t => t.name === name);
  if (!tool) throw new Error(`未知工具 ${name}`);
  const args = tool.schema.parse(input);
  return service[tool.method](args, context);
}
