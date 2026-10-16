# 安装

需要 Python 3.11+，推荐 3.12。macOS 和 Linux 是当前验证环境。

## 源码安装

先按 [uv 官方说明](https://docs.astral.sh/uv/getting-started/installation/)安装 uv。

```bash
git clone https://github.com/forest-USTC/featurelens-research.git
cd featurelens-research
uv sync --locked
uv run featurelens --version
uv run featurelens demo-document --json
```

`uv sync` 创建项目独立的 `.venv`。此后可用 `uv run featurelens` 或项目内的 `./featurelens`。

## Release 安装包

在 [Releases](https://github.com/forest-USTC/featurelens-research/releases/latest) 下载 wheel。在存放 wheel 的目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./featurelens_research-0.4.0-py3-none-any.whl
featurelens --version
featurelens demo-document --json
```

文件名以下载的版本为准。无需克隆仓库，也无需 Node。退出虚拟环境用 `deactivate`；下次使用前重新激活。

如选择源码压缩包 `.tar.gz`，也可在虚拟环境内用 `python -m pip install ./featurelens_research-0.4.0.tar.gz` 安装。

## 可选解析模块

仅分析 JavaScript 代码时需要 Node.js 22+ 和 npm。

源码安装：

```bash
npm ci --prefix src/featurelens/js --ignore-scripts
```

wheel 安装：在安装 FeatureLens 的同一虚拟环境内执行：

```bash
(cd "$(python -c 'import featurelens; from pathlib import Path; print(Path(featurelens.__file__).resolve().parent / "js")')" && npm ci --ignore-scripts)
```

然后运行 `featurelens doctor --json` 检查 Node 路径和解析依赖，再运行 `featurelens demo --json` 验证实际扫描。`doctor` 检查环境信息，不替代完整功能测试。

## 升级

源码安装在工作区无未提交修改时执行 `git pull --ff-only`，然后 `uv sync --locked`。使用解析模块时重新运行相应的 `npm ci`。

wheel 安装下载新版本，激活原虚拟环境后运行 `python -m pip install --upgrade ./新版本.whl`。更新后重新生成 MCP 配置并在客户端重启该服务。研究数据与安装目录分离；升级前可用 `backup` 命令备份。
