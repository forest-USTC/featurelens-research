# 命令指南

源码安装时，为下列命令加上 `uv run`；wheel 安装激活环境后可直接执行。参数中的 ID 应替换为实际返回值。

## 文档研究

```bash
featurelens create --title '知识库规则研究' --question '无匹配资料时如何响应？' --json
featurelens import-document --study-id r_实际ID --path '/绝对路径/说明.md' --json
featurelens document-chunks --study-id r_实际ID --document-id d_实际ID --query '资料不足' --json
featurelens capture-document-chunk --study-id r_实际ID --document-id d_实际ID --chunk-id chunk_实际编号 --title '资料不足规则' --json
featurelens add-claim --study-id r_实际ID --type fact --text '文档要求资料不足时提示用户' --evidence-ids '["e_实际ID"]'
```

`document-chunks` 返回原始行号、段落号、表格行或页码，以及片段 ID。按实际找到的片段进行引用。

三类判断：

- `fact`：对材料内容的判断，必须引用证据。
- `inference`：基于材料的推断，必须引用证据并通过 `--limitation` 写明局限。
- `unknown`：尚不能确认的问题，可以没有证据。

```bash
featurelens add-claim --study-id r_实际ID --type unknown --text '实际产品是否遵守该规则？'
featurelens add-verification --study-id r_实际ID --question '无资料时如何回答？' --steps '在授权测试环境输入未覆盖的问题并保存回答' --expected '显示资料不足提示' --claim-ids '["c_实际ID"]'
```

验证计划不执行测试。完成实际观察后，用 `add-evidence --kind runtime` 登记记录，再用 `record-verification` 填写 `passed`、`failed` 或 `blocked`。通过与失败必须引用证据；阻塞需说明原因。状态不会自动改变原判断的类型。

```bash
featurelens report --study-id r_实际ID --output '/绝对路径/研究报告.md'
featurelens report --study-id r_实际ID --format json --output '/绝对路径/研究记录.json'
```

Markdown 适合阅读；JSON 保留完整记录。导出不覆盖已有文件。

## 静态分析

先完成[可选解析模块安装](installation.md#可选解析模块)。

```bash
featurelens create --title '问答实现研究' --question '无引用时有哪些处理分支？' --target '/绝对路径/已解包目录' --json
featurelens analyze --study-id r_实际ID --source-paths '["retrieval.js"]' --json
featurelens find-nodes --study-id r_实际ID --analysis-id a_实际ID --query answerQuestion --json
featurelens capture-node --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID --title '问答函数'
featurelens read-source --study-id r_实际ID --analysis-id a_实际ID --node-id 实际节点ID
```

只分析明确指定的目录，不自动搜索其他应用。`source_paths` 为目标内相对路径。节点代表语法线索，不证明实际执行；读取源码时会检查哈希与路径范围。

## 研究管理与备份

```bash
featurelens list --json
featurelens update --study-id r_实际ID --title '新的标题' --question '调整后的研究问题'
featurelens archive --study-id r_实际ID
featurelens list --status archived --json
featurelens unarchive --study-id r_实际ID
featurelens delete --study-id r_实际ID
featurelens list --status deleted --json
featurelens undelete --study-id r_实际ID
```

`update` 保留标题与问题的修订历史；已有证据和判断不随之改写。研究问题改变后，应人工复核先前结论是否仍然适用。

默认列表仅显示活动研究；`--status all` 包括归档和回收区。删除是可恢复的移入回收区，原始文件仍占用磁盘空间，当前没有永久清理命令。恢复已归档的研究后，其归档状态也会保留。

```bash
featurelens backup --output '/绝对路径/研究备份.zip'
featurelens restore --path '/绝对路径/研究备份.zip' --destination '/绝对路径/新的研究目录'
featurelens list --data-dir '/绝对路径/新的研究目录' --status all --json
```

备份包含整个研究库：活动、归档、回收区记录，以及记录引用的分析结果、原始文档和提取片段。不包含外部应用源码、先前导出的报告或未被记录引用的临时文件；报告可再次导出。

恢复只接受尚不存在的新目录，不覆盖现有库，也不切换当前默认配置。文档片段的保存路径会重建，来源路径仍作为历史信息保留。原应用目标不会被自动重新授权；若需重新分析，请新建研究并指定当前目录。备份哈希用于发现损坏，不证明备份来源可信。

## MCP 工具对应关系

除 `demo`、`demo-document`、`mcp`、`mcp-config`、`tools`、`help` 外，CLI 业务命令对应同名 MCP 工具：前缀 `research_`，连字符换为下划线。例如 `import-document` 对应 `research_import_document`。

25 个工具按用途划分：

| 类别 | 工具后缀（均有 `research_` 前缀） |
| --- | --- |
| 研究 | `create`、`list`、`get`、`update`、`archive`、`unarchive`、`delete`、`undelete` |
| 文档 | `import_document`、`document_chunks`、`capture_document_chunk` |
| 静态分析 | `analyze`、`import_analysis`、`find_nodes`、`capture_node`、`read_source` |
| 材料与判断 | `add_evidence`、`evidence`、`add_claim` |
| 验证 | `add_verification`、`record_verification` |
| 输出与维护 | `report`、`doctor`、`backup`、`restore` |

`featurelens tools` 输出所有工具的参数 Schema。复杂输入可保存为 JSON，使用 `--input /绝对路径/参数.json`。分页工具支持 `--offset` 与 `--limit`。
