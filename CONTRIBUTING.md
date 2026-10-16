# 贡献指南

欢迎通过 [Issues](https://github.com/forest-USTC/featurelens-research/issues) 报告问题、提出用例或讨论改进。

## 本地开发

```bash
uv sync --locked
npm ci --prefix src/featurelens/js --ignore-scripts
uv run pytest -q
uv build
```

主要目录：

- `src/featurelens/`：CLI、MCP、研究存储、文档处理与研究管理。
- `src/featurelens/js/`：可选 JavaScript 语法扫描模块。
- `tests_python/`：单元测试与真实 CLI / MCP 集成测试。
- `docs/`：安装、使用、MCP 与排错说明。
- `examples/`：可阅读的示例研究报告。

## 提交修改

说明解决的问题、用户可见的变化，以及如何验证。功能变化应更新对应使用文档；新增工具应保持 CLI 和 MCP 参数校验一致。

测试使用虚构材料。不要提交实际研究库、个人配置、模型密钥或企业文件。与证据有关的改动需要验证来源、哈希、引用关系和错误处理；不要用测试通过代替业务真实性判断。

项目采用 [MIT License](LICENSE)，贡献的代码按项目许可证提供。第三方代码或资料需要保留适用的许可和来源。
