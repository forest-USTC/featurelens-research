# MCP 接入

先完成[安装](installation.md)，在该 Python 环境中生成配置：

```bash
featurelens mcp-config
```

源码安装用 `uv run featurelens mcp-config`。配置中的 Python 路径必须来自安装了 FeatureLens 的环境。

## JSON 配置客户端

对于使用 `mcpServers` JSON 配置的客户端，将生成的 `featurelens` 条目合并到现有配置；不要覆盖已有其他服务。例如：

```json
{
  "mcpServers": {
    "featurelens": {
      "command": "/absolute/path/.venv/bin/python",
      "args": ["-m", "featurelens", "mcp"],
      "env": {"FEATURELENS_DATA_DIR": "/absolute/path/research-data"}
    }
  }
}
```

Python 和数据目录都应使用绝对路径。配置格式以所用客户端为准；不接受 JSON 配置的客户端，请在 MCP 设置中填写相同的 command、args 和 env。

## 验证连接

保存配置后，在客户端重新加载该 MCP 服务：

1. 确认 `featurelens` 服务能够连接，且能看到 25 个 `research_` 工具。
2. 请求客户端调用 `research_doctor`，检查返回的版本和数据目录。
3. 使用下面的示例需求。文件路径应替换为你允许分析的实际文件。

> 用 FeatureLens 研究“无匹配资料时应该怎样响应”。先创建研究，导入 `/绝对路径/产品说明.md`，查找相关片段并保留出处。把材料事实、推断和未知分别记录。为未知创建验证计划；不要把计划标记为已完成。最后导出报告。

服务还提供 `feature-investigation` 提示模板，可传入 `question` 和可选的 `target`。静态分析需要先安装可选的 JavaScript 解析模块。

## 运行方式

这是 stdio 服务，由客户端启动进程；不需要端口、HTTP 地址或单独启动网页。直接在终端运行 `featurelens mcp` 后等待输入属于正常现象，结束可按 Ctrl+C。

模型与调用费用由客户端管理。FeatureLens 不保存模型密钥，也不自行请求模型。资料内容只作为研究材料；涉及删除、修改或备份时，应明确选择对应研究或目录。

连接失败请查看[常见问题](troubleshooting.md)。
