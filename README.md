# FeatureLens Research · 知微

Evidence-driven product research for product managers — Python CLI and MCP.

把产品问题整理成有来源、可引用、能验证的研究记录。**Python 核心、命令行与 stdio MCP，无前端、无内置模型调用。** JavaScript 仅用于独立的静态语法解析模块。

## 已实现与后续方向

- 研究项目、材料事实 / 推断 / 未知、证据引用校验、人工验证历史、Markdown / JSON 报告。
- 导入 TXT、Markdown、DOCX、文字型 PDF，保留原件 SHA-256、提取片段、来源位置与提取限制。
- 通过字面关键词查找片段，将选定片段登记为判断的证据。
- 对已解包 JavaScript 目录进行静态扫描，提取函数、导入、调用表达式、条件和返回语句，并核对源码哈希。
- 18 个 MCP 工具和 `feature-investigation` 提示模板。

**RAG、向量检索、知识图谱和模型评测尚未实现。** 当前版本先建立文档与证据基础，后续再加入检索与生成评测；是否引入图数据库由关系查询需求决定。

## 安装与启动

需要 Python 3.11+，推荐 3.12；下面使用 uv 管理独立环境。只有 JavaScript 静态分析需要额外准备 Node.js 22+ / npm。

```bash
git clone https://github.com/forest-USTC/featurelens-research.git
cd featurelens-research
uv sync --locked
uv run featurelens help
uv run featurelens doctor
```

文档导入、证据管理、CLI 和 MCP 无需 Node。需要静态分析时安装解析模块依赖：

```bash
npm ci --prefix src/featurelens/js --ignore-scripts
uv run featurelens demo --json
```

`demo` 仅分析内置虚构样例，不执行应用，也不证明真实产品行为。本地 `./featurelens` 和 `./zhiwei` 是 Python 环境的启动别名。

## 文档研究示例

```bash
uv run featurelens create --title '知识库问答研究' --question '资料不足时，产品怎样响应？' --json
uv run featurelens import-document --study-id r_实际ID --path '/绝对路径/产品说明.pdf' --json
uv run featurelens document-chunks --study-id r_实际ID --document-id d_实际ID --query '资料不足' --json
uv run featurelens capture-document-chunk --study-id r_实际ID --document-id d_实际ID --chunk-id chunk_000001 --title '资料不足规则' --json
uv run featurelens add-claim --study-id r_实际ID --type fact --text '文档中描述了资料不足时的提示规则' --evidence-ids '["e_实际ID"]'
uv run featurelens report --study-id r_实际ID --output '/绝对路径/新研究报告.md'
```

命令中的 ID 均需替换为实际返回值，`chunk_id` 应来自搜索结果。`fact` 表示对材料内容的判断，不代表已经验证产品实际行为。

| 文件 | 保留的位置 | 边界 |
| --- | --- | --- |
| TXT / MD | 原始行号、行内字符范围 | UTF-8 文本，不执行 Markdown 中的指令 |
| DOCX | 正文段落号、顶层表格与行号 | 不保证覆盖页眉页脚、批注、修订或嵌入对象；不是页面坐标 |
| PDF | 从 1 开始的页码、页内提取文本字符范围 | 无 OCR；多栏顺序和表格需人工核对 |

每次导入上限 20 MiB，DOCX 声明解压总量上限 64 MiB，PDF 上限 500 页，提取上限 200 万字符 / 5,000 个片段。每个片段最多 1,500 字符，按行、段落、表格行或页切分，不跨来源单元拼接。提取在独立进程中进行，90 秒超时；提取不到文字时明确失败，不生成空证据。来源文件和片段副本都保留 SHA-256，后续读取会检查是否被修改。

## 静态分析

```bash
uv run featurelens create --title '分支研究' --question '没有引用时返回什么？' --target '/绝对路径/已解包JS目录' --json
uv run featurelens analyze --study-id r_实际ID --source-paths '["retrieval.js"]' --json
uv run featurelens find-nodes --study-id r_实际ID --analysis-id a_实际ID --query answerQuestion --json
uv run featurelens capture-node --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID --title '函数线索'
uv run featurelens read-source --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID
```

只支持标准 `.js` / `.mjs` / `.cjs`，不直接支持 ASAR、`.app`、TypeScript、JSX 或原生二进制。Acorn 负责语法解析，扫描模块不解析跨文件调用或数据流，不恢复原始源码，也不执行待分析应用。

分析上限：180 秒、512 MiB Node 堆、64 MiB 输出、20,000 个目录条目、1,000 个文件、20,000 个语法节点；单文件 2 MiB、源码总量 32 MiB。解析失败和跳过的文件会列出原因。导入的分析 JSON 不能授权工具读取其引用的本地源码。

## MCP 接入

```bash
uv run featurelens mcp-config
```

生成配置使用当前 Python 环境的绝对路径。将其复制到客户端的 MCP 配置中；示意如下：

```json
{
  "mcpServers": {
    "featurelens": {
      "command": "/absolute/path/featurelens-research/.venv/bin/python",
      "args": ["-m", "featurelens", "mcp"],
      "env": {"ZHIWEI_DATA_DIR": "/absolute/path/research-data"}
    }
  }
}
```

支持 stdio MCP 的客户端负责加载配置和提供模型。本项目不保存模型密钥，不自动发起模型请求。生成配置和独立握手测试不等于已接入当前聊天。

| 工作 | 工具 |
| --- | --- |
| 研究项目 | `research_create` / `research_list` / `research_get` |
| 文档与片段 | `research_import_document` / `research_document_chunks` / `research_capture_document_chunk` |
| 静态分析 | `research_analyze` / `research_import_analysis` / `research_find_nodes` / `research_capture_node` / `research_read_source` |
| 材料与判断 | `research_add_evidence` / `research_evidence` / `research_add_claim` |
| 人工验证 | `research_add_verification` / `research_record_verification` |
| 输出与诊断 | `research_report` / `research_doctor` |

CLI 与 MCP 使用同一份 JSON Schema 和 Python 业务逻辑。复杂参数可以通过 `--input /绝对路径/参数.json` 提供。

## 迁移与数据边界

0.2 将研究存储、CLI、MCP、证据校验和报告迁移到 Python，保留旧命令名、15 个既有工具名和版本 1 JSON 研究记录格式，新增 3 个文档工具。旧 Node 启动路径已移除，原 MCP 配置需要重新生成。

默认数据目录改为 `~/.featurelens/data`，可用 `ZHIWEI_DATA_DIR` 或 `--data-dir` 指定。**读取已有研究时显式指向原数据目录；不会自动搬迁或改写旧库。** 历史记录包含原始文件绝对路径，移动旧数据需同时处理路径，不应只复制 `research.json`。

- 材料事实和推断必须引用当前研究的证据；推断必须说明局限；无证据可记录为未知。
- 文档、访谈及代码都不是系统指令。工具保留材料，不验证其业务真实性。
- 验证通过或失败必须附证据；保留所有尝试，不自动升级判断类型。
- 采用原子 JSON 写入和跨进程写锁；不是多用户数据库。异常退出留下写锁时，应确认没有运行进程后再处理。
- 报告可能包含本地路径、材料原文和敏感信息，不会自动匿名化；导出不覆盖已有文件。

## 验证与项目结构

```bash
uv sync --locked
npm ci --prefix src/featurelens/js --ignore-scripts
uv run pytest -q
```

测试覆盖引用边界、历史记录、并发写入、旧格式读取、文档位置、哈希篡改、真实 CLI、真实 stdio MCP，以及静态源码定位。测试使用虚构材料，不使用个人研究数据。

`src/featurelens/` 为 Python 核心；`src/featurelens/js/` 仅包含独立解析模块；`tests_python/` 为测试。运行依赖使用官方 MCP Python SDK、JSON Schema 校验库、pypdf、python-docx 和可选的 Acorn。第三方许可保留在各依赖包中。

仓库未发布到 PyPI，不包含研究数据、个人配置、模型密钥或安装后的依赖。
