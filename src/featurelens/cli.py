import asyncio
import json
import sys
from pathlib import Path
from .core import Service
from .tools import DEFINITIONS, invoke


def main():
    try:
        run()
    except Exception as exc:
        print(f"知微：{exc}", file=sys.stderr)
        sys.exit(1)


def run():
    argv = sys.argv[1:]
    command = argv.pop(0) if argv else "help"
    if command in ("help", "--help", "-h"):
        print(
            "FeatureLens Research 0.2 · Python CLI / MCP\n用法：featurelens <命令> [--参数 值] [--json]\n"
            + "\n".join(
                d["name"].removeprefix("research_").replace("_", "-")
                + "  "
                + d["description"]
                for d in DEFINITIONS
            )
            + "\n其他：mcp、mcp-config、tools、demo\n通用：--data-dir /绝对路径/研究库；--input /参数.json\n旧 JSON 数据可通过 --data-dir 指定；默认 ~/.featurelens/data。"
        )
        return
    if command in ("version", "--version"):
        print("0.2.0")
        return
    options = {}
    while argv:
        key = argv.pop(0)
        if not key.startswith("--"):
            raise ValueError("参数需要以 -- 开头")
        key = key[2:].replace("-", "_")
        if key in ("json", "demo"):
            options[key] = True
            continue
        if not argv:
            raise ValueError(f"{key} 缺少值")
        value = argv.pop(0)
        if key in ("offset", "limit", "context", "observation_index"):
            value = int(value)
        if key in ("evidence_ids", "claim_ids", "source_paths"):
            value = json.loads(value)
        options[key] = value
    as_json = options.pop("json", False)
    service = Service(options.pop("data_dir", None))
    if command == "mcp":
        from .server import serve

        asyncio.run(serve(service))
        return
    if command == "mcp-config":
        result = {
            "mcpServers": {
                "featurelens": {
                    "command": sys.executable,
                    "args": ["-m", "featurelens", "mcp"],
                    "env": {"ZHIWEI_DATA_DIR": str(service.store.directory)},
                }
            }
        }
    elif command == "tools":
        result = DEFINITIONS
    elif command == "demo":
        target = Path(__file__).parent / "demo"
        s = service.create(
            title="演示：无引用问答",
            question="无匹配资料时返回什么？",
            target=str(target),
            demo=True,
        )
        result = {
            "study_id": s["id"],
            "analysis": service.analyze(s["id"]),
            "boundary": "虚构样例；未执行目标。",
        }
    else:
        data = (
            json.loads(Path(options.pop("input")).read_text())
            if "input" in options
            else {}
        )
        result = invoke(
            service, "research_" + command.replace("-", "_"), {**data, **options}
        )
    print(
        result["text"]
        if command == "report" and not as_json and "text" in result
        else json.dumps(result, ensure_ascii=False, indent=None if as_json else 2)
    )
