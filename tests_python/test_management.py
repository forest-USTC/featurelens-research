import json
import subprocess
import sys
from pathlib import Path
import zipfile
import pytest
from featurelens.core import Service, encode, digest
from featurelens.tools import invoke


def call(service, name, **args):
    return invoke(service, "research_" + name, args)


def test_lifecycle_keeps_evidence_and_revision_history(tmp_path):
    service = Service(tmp_path / "data")
    s = service.create("研究", "原问题")
    sid = s["id"]
    e = service.addEvidence(sid, "证据", "document", "原文", "fixture")
    call(service, "update", study_id=sid, title="新标题", question="新问题")
    updated = service.get(sid)
    assert updated["revisions"][0]["before"]["question"] == "原问题"
    assert updated["evidence"][0] == e
    call(service, "archive", study_id=sid)
    assert not service.list()
    assert service.list("archived")[0]["id"] == sid
    call(service, "unarchive", study_id=sid)
    assert service.list()[0]["status"] == "active"
    call(service, "delete", study_id=sid)
    assert service.list("deleted")[0]["id"] == sid
    with pytest.raises(ValueError, match="找不到研究"):
        service.get(sid)
    call(service, "undelete", study_id=sid)
    assert service.get(sid)["evidence"][0] == e
    with pytest.raises(ValueError, match="title 或 question"):
        call(service, "update", study_id=sid)


def populated(tmp_path):
    service = Service(tmp_path / "original")
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.js").write_text("export function f() { return 1; }")
    s = service.create("备份测试", "问题", str(target))
    sid = s["id"]
    a = service.analyze(sid)
    source = tmp_path / "note.md"
    source.write_text("可验证的文档片段")
    d = call(service, "import_document", study_id=sid, path=str(source))
    hit = call(service, "document_chunks", study_id=sid, document_id=d["id"])["items"][
        0
    ]
    e = call(
        service,
        "capture_document_chunk",
        study_id=sid,
        document_id=d["id"],
        chunk_id=hit["chunk_id"],
        title="片段",
    )
    service.claim(sid, "材料包含该片段", "fact", [e["id"]])
    return service, s, a, d


def test_backup_restore_relocates_evidence_and_preserves_trash(tmp_path):
    service, s, a, d = populated(tmp_path)
    sid = s["id"]
    other = service.create("回收区", "问题")
    call(service, "delete", study_id=other["id"])
    path = tmp_path / "backup.zip"
    before = (service.store.directory / "research.json").read_bytes()
    call(service, "backup", output=str(path))
    assert before == (service.store.directory / "research.json").read_bytes()
    restored = tmp_path / "restored"
    call(service, "restore", path=str(path), destination=str(restored))
    other_service = Service(restored)
    assert other_service.list("deleted")[0]["id"] == other["id"]
    assert other_service.get(sid)["target"] is None
    assert other_service.get(sid)["restored_target"] == s["target"]
    assert (
        call(other_service, "document_chunks", study_id=sid, document_id=d["id"])[
            "items"
        ][0]["text"]
        == "可验证的文档片段"
    )
    assert str(restored) in other_service.get(sid)["documents"][0]["raw_file"]
    assert other_service.get(sid)["claims"] == service.get(sid)["claims"]
    node = other_service.findNodes(sid, a["id"])["items"][0]
    with pytest.raises(ValueError, match="只允许读取"):
        other_service.readSource(sid, a["id"], node["node_id"])
    with pytest.raises(ValueError, match="新目录"):
        call(service, "restore", path=str(path), destination=str(restored))
    with pytest.raises(ValueError, match="不覆盖"):
        call(service, "backup", output=str(path))


def test_backup_refuses_tampered_or_external_files(tmp_path):
    service, s, a, d = populated(tmp_path)
    Path(d["chunks_file"]).write_text("changed")
    output = tmp_path / "backup.zip"
    with pytest.raises(ValueError, match="已变化"):
        call(service, "backup", output=str(output))
    assert not output.exists()
    db = service.store.read()
    db["studies"][0]["analyses"][0]["raw_file"] = str(tmp_path / "outside.json")
    (service.store.directory / "research.json").write_bytes(encode(db))
    with pytest.raises(ValueError, match="超出"):
        call(service, "backup", output=str(output))


def test_restore_rejects_traversal_and_checksum_changes(tmp_path):
    service = Service(tmp_path / "data")
    service.create("研究", "问题")
    path = tmp_path / "backup.zip"
    call(service, "backup", output=str(path))
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr("../escaped.txt", "bad")
    target = tmp_path / "restored"
    with pytest.raises(ValueError, match="不安全路径"):
        call(service, "restore", path=str(bad), destination=str(target))
    assert not target.exists() and not (tmp_path / "escaped.txt").exists()
    with zipfile.ZipFile(bad, "w") as z:
        for name, data in files.items():
            z.writestr(name, b"{}" if name == "research.json" else data)
    with pytest.raises(ValueError, match="哈希校验失败"):
        call(service, "restore", path=str(bad), destination=str(target))
    assert not target.exists()


def test_restore_rejects_forged_file_reference(tmp_path):
    service, s, a, d = populated(tmp_path)
    path = tmp_path / "backup.zip"
    call(service, "backup", output=str(path))
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    db = json.loads(files["research.json"])
    db["studies"][0]["documents"][0]["raw_file"] = "/tmp/arbitrary"
    files["research.json"] = encode(db)
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["research.json"] = digest(files["research.json"])
    files["manifest.json"] = encode(manifest)
    bad = tmp_path / "forged.zip"
    with zipfile.ZipFile(bad, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    with pytest.raises(ValueError, match="引用或哈希无效"):
        call(service, "restore", path=str(bad), destination=str(tmp_path / "new"))
    assert not (tmp_path / "new").exists()


def test_document_demo_cli_produces_complete_report_without_node(tmp_path):
    import os

    env = {**os.environ, "PATH": str(tmp_path)}
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "featurelens",
            "demo-document",
            "--data-dir",
            str(tmp_path / "data"),
            "--json",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(run.stdout)
    text = Path(result["report"]).read_text()
    assert result["claims"] == 3 and result["pending_verifications"] == 1
    for expected in [
        "材料事实",
        "分析推断",
        "待确认",
        "待执行",
        "没有资料达到阈值",
        "SHA-256",
    ]:
        assert expected in text
    study = Service(tmp_path / "data").get(result["study_id"])
    assert study["verifications"][0]["attempts"] == []
    assert all(c["evidence_ids"] for c in study["claims"] if c["type"] != "unknown")
