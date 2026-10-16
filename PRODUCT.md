# FeatureLens Research（知微）

面向产品经理的本地功能研究 CLI / MCP，Python 核心。

研究流程：问题 → 文档 / 静态代码线索 → 引用证据 → 材料事实 / 推断 / 未知 → 验证记录 → 报告。

支持文档提取与来源定位、JavaScript 静态语法扫描、研究修订与归档、可恢复删除、备份恢复。MCP 提供 25 个工具；CLI 的 demo-document 可直接生成完整示例报告。

不执行研究目标，不内置模型调用。文档处理无 OCR，尚未实现 RAG、知识图谱和模型评测。模型由所连接的 MCP 客户端提供。

项目使用 MIT 许可证。使用说明见 README，命令细节见 docs/usage.md。
