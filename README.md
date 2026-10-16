# FeatureLens Research · 知微

Evidence-driven product feature research for product managers.

把一个产品问题推进成有来源、能追问、可验证的研究记录。**只有命令行与 stdio MCP，没有前端、网页服务或内置模型 API。**

底层调用已经安装的 ChaiChai 进行 JavaScript/Electron 静态分析；新增的 15 个工具负责研究项目、证据筛选、判断分层、验证记录和报告。没有复制 ChaiChai / REA 的分析实现。

## 开始使用

先克隆仓库并安装依赖（Node.js 22+）：

```bash
git clone https://github.com/forest-USTC/featurelens-research.git
cd featurelens-research
npm ci
```

然后在此目录执行：

```bash
./zhiwei help
./zhiwei doctor
./zhiwei demo --json
```

`demo` 创建一个演示研究并真正调用分析引擎处理 `fixtures/demo-app`。这个应用是虚构测试样例，不代表任何真实产品；静态分析不会运行它。演示输出 `study_id` 与 `analysis.id`，后续命令使用实际返回值。

```bash
./zhiwei create --title '知识库引用研究' --question '找不到引用时，功能怎样处理？' --target '/绝对路径/已解包应用' --json
./zhiwei analyze --study-id r_实际ID --json
./zhiwei find-nodes --study-id r_实际ID --analysis-id a_实际ID --query knowledge --json
./zhiwei capture-node --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID --title '问答入口'
./zhiwei read-source --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID
./zhiwei report --study-id r_实际ID --output '/绝对路径/新报告.md'
```

运行静态分析前需准备独立的 ChaiChai CLI；没有分析引擎时仍可管理研究、材料、判断和验证记录。仓库的 `./zhiwei` 优先使用本机已安装的 ChaiChai Node 运行环境；找不到时使用 PATH 上的 Node，不会自动下载运行环境。

## MCP 接入

```bash
./zhiwei mcp-config
```

输出绝对路径配置，可用于支持 `mcpServers` 的客户端。Codex 的 TOML 形态如下，实际 Node 路径以 `mcp-config` 返回值为准：

```toml
[mcp_servers.zhiwei]
command = "/绝对路径/node"
args = ["/绝对路径/feature-research/bin/zhiwei.mjs", "mcp"]

[mcp_servers.zhiwei.env]
ZHIWEI_DATA_DIR = "/绝对路径/研究库"
ZHIWEI_ENGINE_BIN = "/绝对路径/chaichai"
```

配置由用户选择的客户端加载。生成配置不等于已注册；独立 MCP 客户端握手测试也不等于当前聊天已经连接。

接入后可以这样提出需求：

> 用知微研究我指定的这个应用：知识库没有匹配资料时会发生什么？先建立研究，找到相关证据，区分源码事实和运行推断，把未验证的问题列出来，最后导出报告。

服务提供 `feature-investigation` 提示模板。模型由 Codex 等客户端提供；本工具不保存模型密钥，也不发起付费模型调用。

## 工具与工作流程

| 工作 | 工具 |
| --- | --- |
| 确定问题与目标 | `research_create`、`research_list`、`research_get` |
| 分析或导入已有结果 | `research_analyze`、`research_import_analysis` |
| 找到可引用证据 | `research_find_nodes`、`research_capture_node`、`research_read_source` |
| 补充文档、访谈、实测材料 | `research_add_evidence`、`research_evidence` |
| 区分事实、推断与未知 | `research_add_claim` |
| 管理验证计划与结果 | `research_add_verification`、`research_record_verification` |
| 导出与环境诊断 | `research_report`、`research_doctor` |

每个命令都支持 `--json`。复杂参数可以存入 JSON 文件，再传 `--input /绝对路径/参数.json`；CLI 与 MCP 使用同一套参数校验和业务逻辑。

## 证据边界

- `fact` 是研究者对材料事实的判断，不是系统证明；必须引用当前研究中的证据。
- `inference` 必须有证据和局限说明；无证据的事项只能登记为 `unknown`。
- 人工材料标记为 `researcher-supplied`，分析节点标记为 `analyzer-output`。
- 验证通过或失败必须附证据；所有尝试保留历史，不能自动升级判断类型。
- 静态节点保留原始 Evidence ID、节点身份、哈希、覆盖范围与限制。工具没有新的“降低幻觉率”实测数据。
- 完整分析 JSON 单独保存，分页查询不会丢失原记录。哈希变化会拒绝沿用；导入的 JSON 不能授权工具读取其内部列出的本地文件。
- 报告含材料原文和可能的本地路径。向外分享前人工检查，不会自动匿名化。

## 范围与限制

第一版支持已解包 JS 应用目录、ASAR、带标准 `Contents/Resources/app.asar` 的 Electron `.app`。不是所有 Mac 应用都是 Electron。未接入原生反编译、浏览器自动操作或运行时采集；这些任务仍由独立工具完成，再将观察记录导入研究。

关键词搜索是字面匹配，不是语义检索。静态分析默认限制总时长 180 秒、单文件分析 60 秒、单分析 Worker 堆 512 MiB、结果 64 MiB、20,000 个语义节点；大型应用建议用 `--source-paths '["相对路径.js"]'` 明确缩小范围。失败时不会凭空生成判断。

默认数据目录为项目下 `data/`，可用 `ZHIWEI_DATA_DIR` 或 CLI `--data-dir` 指定。采用原子 JSON 写入和跨进程写锁。不要把它当成多用户数据库。写进程被强制终止可能留下 `.write-lock`；确认没有其他知微进程后方可移除该锁目录。

## 验证

```bash
npm run check
npm test
node scripts/verify-engine.mjs
```

测试覆盖引用边界、验证历史、并发持久化、证据篡改、源码路径越界、导出不覆盖、进程超时、真实 CLI 调用及真实 stdio MCP 发现/调用/提示模板。`verify-engine.mjs` 使用真实 MCP 调用分析引擎、定位源码并生成报告，另外实际测试自编写的纯函数样例；不启动 Electron 或真实产品。

在受限沙箱中，分析引擎可能因无法读取进程表而返回 `cleanup_incomplete` 或迟迟不退出。本工具会在总超时后停止自己启动的进程组。遇到这种情况，应在具备进程检查权限的终端运行或由宿主批准执行，不能把清理失败当成分析成功。本项目在宿主授权的终端环境中完成了真实分析验证。

## 依赖与来源说明

对外入口使用知微名称，分析引擎通过 `ZHIWEI_ENGINE_BIN` 指定；旧的 `CHAICHAI_BIN` 仍作为兼容配置读取。当前适配的是 ChaiChai CLI 的 JavaScript 分析接口，并不支持任意命令行程序。默认安装路径保留以确保现有环境继续可用。`doctor` 的引擎状态字段现为 `engine`。

原始分析 JSON、已有研究记录中的 provider / extractor 信息及依赖包的许可声明保持原样，它们用于说明来源和校验完整性。产品文案的清理不代表分析引擎变成知微自研。

## 项目名称与发布范围

英文名为 **FeatureLens Research**，中文名为**知微**。本地 `./featurelens` 与 `./zhiwei` 均可使用；npm 命令入口也提供这两个别名。现有环境变量继续兼容。

这是 0.1.0 初始版本，尚未发布到 npm。仓库不包含用户研究库、原始分析结果、个人 MCP 配置、模型密钥或已安装依赖。测试中的产品与数据均为自编写的虚构样例。
