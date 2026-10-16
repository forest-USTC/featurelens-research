from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import pytest
from featurelens.core import Service, encode
from featurelens.tools import invoke


@pytest.fixture
def setup(tmp_path):
    svc = Service(tmp_path / "data")
    s = svc.create("测试", "缺少证据时如何处理？")
    return svc, s, tmp_path


def test_claim_boundaries(setup):
    svc, s, _ = setup
    with pytest.raises(ValueError, match="必须引用"):
        invoke(
            svc,
            "research_add_claim",
            dict(study_id=s["id"], text="无证据", type="fact"),
        )
    other = svc.create("另一个", "问题")
    e = svc.addEvidence(other["id"], "文档", "document", "x", "fixture")
    with pytest.raises(ValueError, match="不属于"):
        svc.claim(s["id"], "跨研究", "fact", [e["id"]])
    with pytest.raises(ValueError, match="局限"):
        svc.claim(other["id"], "推断", "inference", [e["id"]])
    c = svc.claim(s["id"], "未知", "unknown")
    assert c["type"] == "unknown"


def test_validation_history_and_report(setup):
    svc, s, p = setup
    c = svc.claim(s["id"], "未知", "unknown")
    v = svc.verification(s["id"], "输出？", "输入", "拒答", [c["id"]])
    with pytest.raises(ValueError, match="附实际证据"):
        svc.recordVerification(s["id"], v["id"], "passed", "ok")
    svc.recordVerification(s["id"], v["id"], "blocked", "未执行")
    e = svc.addEvidence(s["id"], "结果", "runtime", "拒答", "synthetic test")
    svc.recordVerification(s["id"], v["id"], "passed", "拒答", [e["id"]])
    updated = svc.get(s["id"])
    assert len(updated["verifications"][0]["attempts"]) == 2
    assert updated["claims"][0]["type"] == "unknown"
    output = p / "report.md"
    svc.report(s["id"], output=str(output))
    with pytest.raises(FileExistsError):
        svc.report(s["id"], output=str(output))
    assert "拒答" in output.read_text()


def test_concurrent_store_instances(setup):
    svc, s, p = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda i: Service(p / "data").claim(s["id"], f"未知{i}", "unknown"),
                range(12),
            )
        )
    assert len(svc.get(s["id"])["claims"]) == 12


def test_existing_json_and_strict_schema(setup):
    svc, s, p = setup
    # A v0.1 record has no documents field; opening it must preserve all data.
    before = (p / "data/research.json").read_bytes()
    assert Service(p / "data").get(s["id"]) == s
    assert (p / "data/research.json").read_bytes() == before
    with pytest.raises(Exception):
        invoke(svc, "research_evidence", dict(study_id=s["id"], limit=-1))
    with pytest.raises(Exception):
        invoke(svc, "research_create", dict(title="x", question="x", arbitrary=1))
    with pytest.raises(Exception):
        invoke(svc, "research_create", dict(title="  ", question="x"))


def test_static_source_and_import_boundaries(setup):
    svc, _, p = setup
    target = p / "target"
    target.mkdir()
    f = target / "sample.js"
    f.write_text(
        'throw new Error("must never run");\nexport function answer(q) { if (!q) return null; return q; }'
    )
    s = svc.create("静态", "分支？", str(target))
    a = svc.analyze(s["id"])
    rows = svc.findNodes(s["id"], a["id"], query="answer")["items"]
    n = next(n for n in rows if n["kind"] == "function")
    assert "if (!q)" in svc.readSource(s["id"], a["id"], n["node_id"])["text"]
    e = svc.captureNode(s["id"], a["id"], n["node_id"], "函数")
    assert svc.captureNode(s["id"], a["id"], n["node_id"], "重复")["id"] == e["id"]
    other = svc.create("导入", "来源？", str(target))
    b = svc.importAnalysis(other["id"], a["raw_file"])
    assert b["sha256"] == a["sha256"]
    assert svc.importAnalysis(other["id"], a["raw_file"])["reused"]
    with pytest.raises(ValueError, match="只允许读取"):
        svc.readSource(other["id"], b["id"], n["node_id"])
    f.write_text("changed")
    with pytest.raises(ValueError, match="改变"):
        svc.readSource(s["id"], a["id"], n["node_id"])
    Path(a["raw_file"]).write_text("{}")
    with pytest.raises(ValueError, match="已变化"):
        svc.findNodes(s["id"], a["id"])


def test_cli(setup):
    _, _, p = setup
    cmd = [
        sys.executable,
        "-m",
        "featurelens",
        "create",
        "--title",
        "CLI",
        "--question",
        "question",
        "--data-dir",
        str(p / "cli"),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["id"].startswith("r_")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "featurelens",
            "evidence",
            "--study-id",
            "r_12345678",
            "--limit",
            "-1",
            "--data-dir",
            str(p / "cli"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_process_timeout_and_cancellation():
    from threading import Event
    from featurelens.core import run_process, CANCEL

    with pytest.raises(ValueError, match="超时"):
        run_process([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)
    event = Event()
    event.set()
    token = CANCEL.set(event)
    try:
        with pytest.raises(ValueError, match="取消"):
            run_process([sys.executable, "-c", "import time; time.sleep(5)"])
    finally:
        CANCEL.reset(token)


def test_parser_failures_and_source_traversal(setup):
    svc, _, p = setup
    root = p / "target"
    root.mkdir()
    file = root / "bad.js"
    file.write_text("export ???")
    s = svc.create("解析", "失败？", str(root))
    with pytest.raises(ValueError, match="没有成功解析"):
        svc.analyze(s["id"])
    file.write_text("export function answer() { return 42; }")
    outside = p / "outside.js"
    outside.write_text(file.read_text())
    (root / "escape.js").symlink_to(outside)
    with pytest.raises(ValueError, match="超出选定"):
        svc.analyze(s["id"], ["escape.js"])
    a = svc.analyze(s["id"], ["bad.js"])
    raw = json.loads(Path(a["raw_file"]).read_bytes())
    node = next(
        n
        for n in raw["normalized_result"]["semantic_graph"]["nodes"]
        if n["kind"] == "function"
    )
    node["evidence"]["location"]["value"]["source"] = "../outside.js"
    forged = svc.retain(s["id"], raw, encode(raw), "local-run")
    with pytest.raises(ValueError, match="超出选定"):
        svc.readSource(s["id"], forged["id"], node["node_id"])
