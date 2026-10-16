"""Local extraction with stable provenance; no model calls, OCR or remote fetching."""

from io import BytesIO
from pathlib import Path
import json
import zipfile
import tempfile
import sys
from .core import absolute, require, digest, uid, encode, now, page, run_process

LIMIT = "提取结果不验证原文真实性；不执行文档指令；无 OCR、图片理解或完整排版恢复。"


def extract(raw, suffix):
    units = []
    warnings = []
    if suffix in (".txt", ".md"):
        for i, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            if line.strip():
                units.append(({"line": i}, line))
    elif suffix == ".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph

        with zipfile.ZipFile(BytesIO(raw)) as z:
            require(
                sum(x.file_size for x in z.infolist()) <= 64 * 1024 * 1024,
                "DOCX 解压内容超过 64 MiB",
            )
        doc = Document(BytesIO(raw))
        paragraph = 0
        table = 0
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                paragraph += 1
                if block.text.strip():
                    units.append(({"paragraph": paragraph}, block.text))
            else:
                table += 1
                for rownum, row in enumerate(block.rows, 1):
                    text = " | ".join(c.text for c in row.cells)
                    if text.strip():
                        units.append(({"table": table, "row": rownum}, text))
        warnings.append(
            "DOCX 仅提取正文段落与顶层表格；页眉页脚、批注、修订和嵌入对象不保证覆盖。"
        )
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw))
        require(not reader.is_encrypted, "不支持加密 PDF，请先提供可读取的副本")
        require(len(reader.pages) <= 500, "PDF 超过 500 页，请拆分")
        for num, p in enumerate(reader.pages, 1):
            text = p.extract_text() or ""
            if text.strip():
                units.append(({"page": num}, text))
            else:
                warnings.append(
                    f"第 {num} 页未提取到文字，可能为空白或扫描页；未执行 OCR。"
                )
        warnings.append("PDF 阅读顺序可能与视觉排版不同，表格和多栏内容需人工核对。")
    else:
        raise ValueError("只支持 TXT、Markdown、DOCX 和文字型 PDF")
    require(units, "未提取到文字；扫描文档需要另行 OCR")
    require(
        sum(len(t) for _, t in units) <= 2_000_000, "提取文本超过 200 万字符，请拆分"
    )
    chunks = []
    for loc, text in units:
        for start in range(0, len(text), 1500):
            chunks.append(
                dict(
                    chunk_id=f"chunk_{len(chunks) + 1:06}",
                    location=dict(
                        loc, char_start=start, char_end=min(start + 1500, len(text))
                    ),
                    text=text[start : start + 1500],
                )
            )
            require(len(chunks) <= 5000, "文档超过 5,000 个片段，请拆分")
    return chunks, warnings


def import_document(service, study_id, path, title=None):
    p = absolute(path).resolve()
    require(p.is_file(), "请选择文件")
    require(p.stat().st_size <= 20 * 1024 * 1024, "文档超过 20 MiB")
    raw = p.read_bytes()
    sha = digest(raw)
    s = service.store.get(study_id)
    for d in s.get("documents", []):
        if d["sha256"] == sha:
            return dict(d, reused=True)
    with tempfile.NamedTemporaryFile(suffix=p.suffix.lower()) as snapshot:
        snapshot.write(raw)
        snapshot.flush()
        result, _ = run_process(
            [
                sys.executable,
                "-m",
                "featurelens.document_worker",
                snapshot.name,
                p.suffix.lower(),
            ],
            timeout=90,
        )
    chunks, warnings = result["chunks"], result["warnings"]
    did = uid("d")
    service.store.init()
    source = service.store.directory / "raw" / f"{did}{p.suffix.lower()}"
    extracted = service.store.directory / "raw" / f"{did}.chunks.json"
    blob = encode(chunks)
    for file, data in [(source, raw), (extracted, blob)]:
        with file.open("xb") as f:
            f.write(data)
        file.chmod(0o600)
    doc = dict(
        id=did,
        title=title or p.name,
        source=str(p),
        sha256=sha,
        raw_file=str(source),
        chunks_file=str(extracted),
        chunks_sha256=digest(blob),
        chunk_count=len(chunks),
        warnings=warnings,
        limitation=LIMIT,
        provenance="document-extraction",
        created_at=now(),
    )
    return service._append(study_id, "documents", doc)


def load(service, sid, did):
    d = next(
        (d for d in service.store.get(sid).get("documents", []) if d["id"] == did), None
    )
    require(d, "找不到文档")
    require(digest(Path(d["raw_file"]).read_bytes()) == d["sha256"], "原始文档已变化")
    raw = Path(d["chunks_file"]).read_bytes()
    require(digest(raw) == d["chunks_sha256"], "提取片段已变化")
    return d, json.loads(raw)


def document_chunks(service, study_id, document_id, query="", offset=0, limit=15):
    d, chunks = load(service, study_id, document_id)
    return dict(
        page([c for c in chunks if query.lower() in c["text"].lower()], offset, limit),
        document_id=document_id,
        sha256=d["sha256"],
        warnings=d["warnings"],
        boundary=LIMIT,
    )


def capture_document_chunk(service, study_id, document_id, chunk_id, title):
    d, chunks = load(service, study_id, document_id)
    c = next((c for c in chunks if c["chunk_id"] == chunk_id), None)
    require(c, "找不到片段")

    def add(s):
        for e in s["evidence"]:
            if e.get("document_id") == document_id and e.get("chunk_id") == chunk_id:
                return e
        e = dict(
            id=uid("e"),
            title=title,
            kind="document",
            content=c["text"],
            source=f"{d['source']} · {json.dumps(c['location'], ensure_ascii=False)}",
            location=c["location"],
            document_id=document_id,
            chunk_id=chunk_id,
            source_sha256=d["sha256"],
            provenance="document-extraction",
            created_at=now(),
            digest=digest(c["text"]),
            limitation=LIMIT,
        )
        s["evidence"].append(e)
        return e

    return service.store.mutate(study_id, add)
