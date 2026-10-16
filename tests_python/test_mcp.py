import asyncio
import sys
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


def test_real_stdio_research_document_flow(tmp_path):
    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "featurelens", "mcp", "--data-dir", str(tmp_path / "data")],
        )
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert len(tools.tools) == 25
                destructive = next(
                    t for t in tools.tools if t.name == "research_delete"
                )
                assert destructive.annotations.destructive_hint is True
                prompts = await client.list_prompts()
                assert prompts.prompts[0].name == "feature-investigation"
                prompt = await client.get_prompt(
                    "feature-investigation", arguments={"question": "无证据时？"}
                )
                assert prompt.messages

                async def call(name, args):
                    r = await client.call_tool(name, args)
                    assert not r.is_error, r
                    return r.structured_content

                target = tmp_path / "target"
                target.mkdir()
                (target / "sample.js").write_text(
                    "export function answer() { return 42; }"
                )
                s = await call(
                    "research_create",
                    {
                        "title": "MCP test",
                        "question": "文档规则？",
                        "target": str(target),
                    },
                )
                analysis = await call("research_analyze", {"study_id": s["id"]})
                nodes = await call(
                    "research_find_nodes",
                    {
                        "study_id": s["id"],
                        "analysis_id": analysis["id"],
                        "query": "answer",
                    },
                )
                fn = next(n for n in nodes["items"] if n["kind"] == "function")
                source = await call(
                    "research_read_source",
                    {
                        "study_id": s["id"],
                        "analysis_id": analysis["id"],
                        "node_id": fn["node_id"],
                    },
                )
                assert "return 42" in source["text"]
                invalid = await client.call_tool(
                    "research_add_claim",
                    {"study_id": s["id"], "text": "unsupported", "type": "fact"},
                )
                assert invalid.is_error
                path = tmp_path / "source.md"
                path.write_text("没有证据时返回未知。")
                d = await call(
                    "research_import_document", {"study_id": s["id"], "path": str(path)}
                )
                chunks = await call(
                    "research_document_chunks",
                    {"study_id": s["id"], "document_id": d["id"]},
                )
                e = await call(
                    "research_capture_document_chunk",
                    {
                        "study_id": s["id"],
                        "document_id": d["id"],
                        "chunk_id": chunks["items"][0]["chunk_id"],
                        "title": "规则",
                    },
                )
                await call(
                    "research_add_claim",
                    {
                        "study_id": s["id"],
                        "text": "文档包含无证据返回未知的规则",
                        "type": "fact",
                        "evidence_ids": [e["id"]],
                    },
                )
                report = await call("research_report", {"study_id": s["id"]})
                assert "没有证据时返回未知" in report["text"]
                await call(
                    "research_update", {"study_id": s["id"], "title": "更新后的研究"}
                )
                await call("research_archive", {"study_id": s["id"]})
                rows = await call("research_list", {"status": "archived"})
                assert rows["items"][0]["title"] == "更新后的研究"
                await call("research_delete", {"study_id": s["id"]})
                await call("research_undelete", {"study_id": s["id"]})
                await call("research_unarchive", {"study_id": s["id"]})
                backup = tmp_path / "mcp-backup.zip"
                await call("research_backup", {"output": str(backup)})
                restored = await call(
                    "research_restore",
                    {"path": str(backup), "destination": str(tmp_path / "restored")},
                )
                assert restored["studies"] == 1

    asyncio.run(run())
