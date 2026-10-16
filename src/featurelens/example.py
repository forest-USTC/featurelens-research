"""A reproducible, explicitly synthetic document research workflow."""

from pathlib import Path
from .core import absolute, require
from .tools import invoke


def document_demo(service, output=None):
    if output:
        require(not absolute(output).exists(), "报告已存在，不覆盖")

    def call(name, **args):
        return invoke(service, "research_" + name, args)

    study = call(
        "create",
        title="示例：知识库资料不足时怎样响应？",
        question="文档如何规定资料不足时的响应，哪些行为还需要实测？",
        demo=True,
    )
    sid = study["id"]
    doc = call(
        "import_document",
        study_id=sid,
        path=str(Path(__file__).parent / "demo/product-notes.md"),
    )
    hit = call(
        "document_chunks", study_id=sid, document_id=doc["id"], query="没有资料达到阈值"
    )["items"][0]
    evidence = call(
        "capture_document_chunk",
        study_id=sid,
        document_id=doc["id"],
        chunk_id=hit["chunk_id"],
        title="资料不足处理规则",
    )
    call(
        "add_claim",
        study_id=sid,
        type="fact",
        text="示例文档要求：没有资料达到阈值时提示参考资料不足，并引导补充问题或资料。",
        evidence_ids=[evidence["id"]],
        limitation="仅确认文档表述，尚未验证产品行为。",
    )
    call(
        "add_claim",
        study_id=sid,
        type="inference",
        text="产品设计希望在资料不足时向用户说明原因，并提供继续操作的方向。",
        evidence_ids=[evidence["id"]],
        limitation="这是对规则设计意图的推断，不能证明实际界面或模型会按此执行。",
    )
    unknown = call(
        "add_claim",
        study_id=sid,
        type="unknown",
        text="实际问答是否会在无匹配资料时仍生成未经引用支持的答案？",
    )
    call(
        "add_verification",
        study_id=sid,
        question="无匹配资料时的实际输出是什么？",
        steps="在获得授权的测试环境中，输入资料库未覆盖的问题，保存回答与引用记录。",
        expected="出现资料不足提示，引用为空；是否生成额外内容另行记录。",
        claim_ids=[unknown["id"]],
    )
    if not output:
        folder = service.store.directory / "reports"
        folder.mkdir(exist_ok=True)
        output = str(folder / f"{sid}.md")
    report = call("report", study_id=sid, output=output)
    return dict(
        study_id=sid,
        document_id=doc["id"],
        evidence_id=evidence["id"],
        report=report["path"],
        claims=3,
        pending_verifications=1,
        note="虚构文档示例；没有调用模型或执行产品测试，验证项保持待执行。",
    )
