"""Research storage and evidence boundaries. Never executes a target application."""

import copy
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone

CANCEL = ContextVar("featurelens_cancel", default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def digest(data):
    return hashlib.sha256(
        data if isinstance(data, bytes) else data.encode()
    ).hexdigest()


def encode(data):
    return json.dumps(data, ensure_ascii=False, indent=2).encode()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def absolute(path):
    p = Path(path)
    require(p.is_absolute(), "需要绝对路径")
    return p


def run_process(command, timeout=180):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
        try:
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                require(not (CANCEL.get() and CANCEL.get().is_set()), "操作已取消")
                require(time.monotonic() < deadline, "操作超时")
                require(
                    os.fstat(out.fileno()).st_size <= 64 * 1024 * 1024
                    and os.fstat(err.fileno()).st_size <= 1024 * 1024,
                    "分析输出超过限制",
                )
                time.sleep(0.03)
            out.seek(0)
            err.seek(0)
            raw = out.read(64 * 1024 * 1024 + 1)
            require(len(raw) <= 64 * 1024 * 1024, "分析输出超过限制")
            require(proc.returncode == 0, err.read(4000).decode(errors="replace"))
            return json.loads(raw), raw
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def run_analysis(target, paths):
    analyzer = Path(__file__).parent / "js" / "analyzer.mjs"
    return run_process(
        [
            "node",
            "--max-old-space-size=512",
            str(analyzer),
            str(target),
            json.dumps(paths),
        ]
    )


class Store:
    def __init__(self, directory=None):
        self.directory = Path(
            directory
            or os.getenv("ZHIWEI_DATA_DIR")
            or Path.home() / ".featurelens" / "data"
        ).resolve()

    def init(self):
        (self.directory / "raw").mkdir(parents=True, exist_ok=True)

    def read(self):
        self.init()
        p = self.directory / "research.json"
        return (
            json.loads(p.read_bytes()) if p.exists() else {"version": 1, "studies": []}
        )

    def pick(self, db, sid):
        require(re.fullmatch(r"r_[a-f0-9]{8}", sid), "无效研究 ID")
        s = next((s for s in db["studies"] if s["id"] == sid), None)
        require(s is not None, "找不到研究项目")
        return s

    def get(self, sid):
        return self.pick(self.read(), sid)

    def change(self, fn):
        self.init()
        lock = self.directory / ".write-lock"
        for _ in range(80):
            try:
                lock.mkdir()
                break
            except FileExistsError:
                time.sleep(0.05)
        else:
            raise ValueError("研究库正在写入；请确认没有运行进程后检查 .write-lock")
        temp = self.directory / f"research.{uuid.uuid4().hex}.tmp"
        try:
            db = self.read()
            result = fn(db)
            with open(temp, "xb") as f:
                os.chmod(temp, 0o600)
                f.write(encode(db))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.directory / "research.json")
            return copy.deepcopy(result)
        finally:
            temp.unlink(missing_ok=True)
            lock.rmdir()

    def mutate(self, sid, fn):
        def update(db):
            s = self.pick(db, sid)
            result = fn(s)
            s["updated_at"] = now()
            return result

        return self.change(update)


class Service:
    def __init__(self, directory=None):
        self.store = Store(directory)

    def create(self, title, question, target=None, demo=False):
        if target:
            absolute(target)
        s = dict(
            id=uid("r"),
            title=title,
            question=question,
            target=target,
            demo=demo,
            created_at=now(),
            updated_at=now(),
            evidence=[],
            analyses=[],
            claims=[],
            verifications=[],
        )

        def add(db):
            db["studies"].append(s)
            return s

        return self.store.change(add)

    def list(self):
        return [
            dict(
                id=s["id"],
                title=s["title"],
                question=s["question"],
                demo=s["demo"],
                evidence_count=len(s["evidence"]),
                claim_count=len(s["claims"]),
                updated_at=s["updated_at"],
            )
            for s in self.store.read()["studies"]
        ]

    def get(self, study_id):
        return self.store.get(study_id)

    def addEvidence(self, study_id, title, kind, content, source, limitation=""):
        e = dict(
            id=uid("e"),
            title=title,
            kind=kind,
            content=content,
            source=source,
            limitation=limitation,
            provenance="researcher-supplied",
            created_at=now(),
            digest=digest(content),
        )
        return self._append(study_id, "evidence", e)

    def _append(self, sid, key, item):
        def add(s):
            s.setdefault(key, []).append(item)
            return item

        return self.store.mutate(sid, add)

    def evidence(self, study_id, evidence_id=None, query="", offset=0, limit=20):
        rows = self.store.get(study_id)["evidence"]
        if evidence_id:
            e = next((e for e in rows if e["id"] == evidence_id), None)
            require(e, "找不到证据")
            return e
        return page(
            [
                e
                for e in rows
                if query.lower() in json.dumps(e, ensure_ascii=False).lower()
            ],
            offset,
            limit,
        )

    def claim(self, study_id, text, type, evidence_ids=None, limitation=""):
        evidence_ids = evidence_ids or []
        require(
            type == "unknown" or evidence_ids,
            "材料事实和推断必须引用证据；无证据请登记 unknown",
        )
        require(type != "inference" or limitation.strip(), "推断必须说明局限")

        def add(s):
            references(s, "evidence", evidence_ids)
            c = dict(
                id=uid("c"),
                text=text,
                type=type,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                limitation=limitation,
                provenance="researcher-authored",
                created_at=now(),
            )
            s["claims"].append(c)
            return c

        return self.store.mutate(study_id, add)

    def verification(self, study_id, question, steps, expected, claim_ids=None):
        def add(s):
            references(s, "claims", claim_ids or [])
            v = dict(
                id=uid("v"),
                question=question,
                steps=steps,
                expected=expected,
                claim_ids=claim_ids or [],
                status="pending",
                attempts=[],
                created_at=now(),
            )
            s["verifications"].append(v)
            return v

        return self.store.mutate(study_id, add)

    def recordVerification(
        self, study_id, verification_id, status, observed, evidence_ids=None
    ):
        require(status == "blocked" or evidence_ids, "通过或失败必须附实际证据")

        def update(s):
            references(s, "evidence", evidence_ids or [])
            v = next(
                (v for v in s["verifications"] if v["id"] == verification_id), None
            )
            require(v, "找不到验证项")
            v["attempts"].append(
                dict(
                    status=status,
                    observed=observed,
                    evidence_ids=evidence_ids or [],
                    recorded_at=now(),
                    provenance="researcher-recorded",
                )
            )
            v["status"] = status
            return v

        return self.store.mutate(study_id, update)

    def importAnalysis(self, study_id, path):
        p = absolute(path)
        require(p.stat().st_size <= 64 * 1024 * 1024, "文件超过 64 MiB")
        raw = p.read_bytes()
        return self.retain(study_id, json.loads(raw), raw, "imported")

    def retain(self, sid, doc, raw, origin):
        e = doc if doc.get("evidence_id") else doc.get("result", {})
        require(
            e.get("operation") == "analyze_javascript_application"
            and isinstance(
                e.get("normalized_result", {}).get("graph", {}).get("nodes"), list
            ),
            "需要完整分析 Evidence JSON",
        )
        for old in self.store.get(sid)["analyses"]:
            if old["sha256"] == digest(raw):
                return dict(old, reused=True)
        aid = uid("a")
        self.store.init()
        path = self.store.directory / "raw" / f"{aid}.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        n = e["normalized_result"]
        a = dict(
            id=aid,
            origin=origin,
            evidence_id=e["evidence_id"],
            sha256=digest(raw),
            operation=e["operation"],
            subject=e.get("subject"),
            provider=e.get("provider"),
            node_count=len(n["graph"]["nodes"]),
            semantic_node_count=len(n.get("semantic_graph", {}).get("nodes", [])),
            edge_count=len(n["graph"].get("edges", [])),
            statistics=n.get("statistics"),
            limitations=list(
                dict.fromkeys(e.get("limitations", []) + n.get("limitations", []))
            ),
            coverage=n["graph"].get("coverage"),
            raw_file=str(path),
            created_at=now(),
        )
        return self._append(sid, "analyses", a)

    def analysis(self, sid, aid):
        s = self.store.get(sid)
        a = next((a for a in s["analyses"] if a["id"] == aid), None)
        require(a, "找不到分析")
        raw = Path(a["raw_file"]).read_bytes()
        require(digest(raw) == a["sha256"], "原始分析文件内容已变化")
        doc = json.loads(raw)
        e = doc if doc.get("evidence_id") else doc["result"]
        n = e["normalized_result"]
        contexts = {
            c["context_id"]: c
            for c in n.get("semantic_graph", {}).get("evidence_contexts", [])
        }
        nodes = [dict(x, graph_layer="application") for x in n["graph"]["nodes"]] + [
            dict(
                x,
                graph_layer="semantic",
                resolved_evidence_context=contexts.get(
                    x.get("evidence", {}).get("context_id"), {}
                ),
            )
            for x in n.get("semantic_graph", {}).get("nodes", [])
        ]
        return s, a, nodes

    def findNodes(
        self, study_id, analysis_id, query="", offset=0, limit=15, node_id=None
    ):
        _, a, nodes = self.analysis(study_id, analysis_id)
        if node_id:
            return dict(analysis_id=analysis_id, node=find_node(nodes, node_id))
        nodes = [
            n
            for n in nodes
            if query.lower() in json.dumps(n, ensure_ascii=False).lower()
        ]
        return dict(
            page(nodes, offset, limit),
            analysis_id=analysis_id,
            analysis_limitations=a["limitations"],
        )

    def captureNode(self, study_id, analysis_id, node_id, title):
        _, a, nodes = self.analysis(study_id, analysis_id)
        n = find_node(nodes, node_id)

        def add(s):
            for old in s["evidence"]:
                if (
                    old.get("analysis_id") == analysis_id
                    and old.get("node_id") == node_id
                ):
                    return old
            content = encode(n).decode()
            e = dict(
                id=uid("e"),
                title=title,
                kind="static",
                content=content,
                source=f"{a.get('subject')} · {node_id}",
                provenance="analyzer-output",
                analysis_id=analysis_id,
                parent_evidence_id=a["evidence_id"],
                node_id=node_id,
                created_at=now(),
                digest=digest(content),
                limitation="静态线索，不证明实际执行。",
            )
            s["evidence"].append(e)
            return e

        return self.store.mutate(study_id, add)

    def readSource(
        self, study_id, analysis_id, node_id, observation_index=0, context=3
    ):
        s, a, nodes = self.analysis(study_id, analysis_id)
        require(
            s.get("target") and a["origin"] == "local-run",
            "只允许读取本工具实际分析的明确目标；导入 JSON 不能授权读取文件",
        )
        n = find_node(nodes, node_id)
        observations = (
            [
                dict(
                    evidence={
                        **n.get("resolved_evidence_context", {}),
                        **n.get("evidence", {}),
                    }
                )
            ]
            if n["graph_layer"] == "semantic"
            else n.get("observations", [])
        )
        require(observation_index < len(observations), "没有该位置")
        ev = observations[observation_index]["evidence"]
        loc = ev.get("location", {}).get("value", {})
        require(loc.get("kind") == "source-range" and loc.get("source"), "没有源码位置")
        root = Path(s["target"]).resolve()
        file = (root / loc["source"]).resolve()
        require(root.is_dir() and file.is_relative_to(root), "证据位置超出选定目标目录")
        require(file.stat().st_size < 16 * 1024 * 1024, "源文件过大")
        raw = file.read_bytes()
        require(
            ev.get("artifact", {}).get("sha256") == digest(raw),
            "源码缺少校验身份或已在分析后改变",
        )
        lines = raw.decode().split("\n")
        start = max(1, loc["start"]["line"] - context)
        end = min(
            len(lines), loc.get("end", loc["start"])["line"] + context, start + 99
        )
        text = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start - 1, end))
        return dict(
            source=str(file),
            sha256=digest(raw),
            start_line=start,
            end_line=end,
            text=text[:30000],
            truncated=len(text) > 30000 or end < loc.get("end", loc["start"])["line"],
            boundary="源码文本不证明运行行为。",
        )

    def analyze(self, study_id, source_paths=None):
        s = self.store.get(study_id)
        require(s.get("target"), "研究尚未指定目标")
        doc, raw = run_analysis(s["target"], source_paths or [])
        return self.retain(study_id, doc, raw, "local-run")

    def report(self, study_id, format="markdown", output=None):
        s = self.store.get(study_id)
        text = encode(s).decode() if format == "json" else markdown(s)
        if output:
            p = absolute(output)
            with p.open("x", encoding="utf8") as f:
                f.write(text)
            return dict(
                path=str(p),
                format=format,
                bytes=len(text.encode()),
                note="报告可能含本地路径和材料原文。",
            )
        return dict(format=format, text=text)

    def doctor(self):
        import shutil, sys

        return dict(
            name="FeatureLens Research",
            version="0.2.0",
            python=sys.version.split()[0],
            data_directory=str(self.store.directory),
            engine=dict(
                name="featurelens-acorn",
                node=shutil.which("node"),
                dependencies_installed=(
                    Path(__file__).parent / "js/node_modules/acorn"
                ).exists(),
            ),
            interface=["cli", "mcp-stdio"],
            documents=["txt", "md", "docx", "pdf"],
            note="文档提取不验证内容真实性；PDF 不含 OCR。",
        )


def references(s, key, ids):
    require(all(any(x["id"] == i for x in s[key]) for i in ids), "引用不属于当前研究")


def page(rows, offset, limit):
    return dict(
        total=len(rows),
        offset=offset,
        items=rows[offset : offset + limit],
        next_offset=offset + limit if offset + limit < len(rows) else None,
    )


def find_node(nodes, nid):
    n = next((n for n in nodes if n["node_id"] == nid), None)
    require(n, "节点不存在")
    return n


def markdown(s):
    lines = [
        f"# {s['title']}",
        "",
        f"研究问题：{s['question']}",
        "",
        "材料事实和验证结果均为研究者判断；静态代码不证明实际行为。",
        "",
    ]
    if s.get("demo"):
        lines += ["这是虚构演示样例。", ""]
    for kind, title in [
        ("fact", "材料事实（研究者判断）"),
        ("inference", "分析推断"),
        ("unknown", "待确认"),
    ]:
        lines += [f"## {title}", ""]
        for c in s["claims"]:
            if c["type"] == kind:
                lines += [
                    f"- {c['id']}：{c['text']}\n  证据：{', '.join(c['evidence_ids']) or '无'}\n  局限：{c['limitation']}"
                ]
    lines += ["", "## 验证记录", ""]
    for v in s["verifications"]:
        lines += [
            f"### {v['id']} · {v['question']}",
            f"步骤：{v['steps']}\n预期：{v['expected']}\n状态：{v['status']}\n关联判断：{', '.join(v['claim_ids'])}",
            json.dumps(v["attempts"], ensure_ascii=False, indent=2),
        ]
    lines += ["", "## 证据目录", ""]
    for e in s["evidence"]:
        lines += [
            f"### {e['id']} · {e['title']}",
            f"来源：{e['source']}\n来源方式：{e['provenance']}\nSHA-256：{e['digest']}",
            "\n".join("> " + x for x in e["content"].split("\n")),
            f"局限：{e['limitation']}",
            "",
        ]
    lines += [
        "## 分析范围与局限",
        "",
        json.dumps(s["analyses"], ensure_ascii=False, indent=2),
        "",
        "## 导入文档",
        "",
        json.dumps(s.get("documents", []), ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines) + "\n"
