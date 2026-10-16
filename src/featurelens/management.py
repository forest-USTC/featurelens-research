"""Research lifecycle and portable backups; raw evidence remains immutable."""

import copy
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile
from .core import absolute, require, now, digest, encode

MAX_BYTES = 256 * 1024 * 1024


def update(service, study_id, title=None, question=None):
    require(title is not None or question is not None, "请提供 title 或 question")

    def change(s):
        before = {k: s[k] for k in ("title", "question")}
        if title is not None:
            s["title"] = title
        if question is not None:
            s["question"] = question
        s.setdefault("revisions", []).append(
            dict(at=now(), before=before, after={k: s[k] for k in before})
        )
        return s

    return service.store.mutate(study_id, change)


def archive(service, study_id):
    def change(s):
        s.setdefault("archived_at", now())
        return s

    return service.store.mutate(study_id, change)


def unarchive(service, study_id):
    def change(s):
        s.pop("archived_at", None)
        return s

    return service.store.mutate(study_id, change)


def delete(service, study_id):
    def change(db):
        s = service.store.pick(db, study_id)
        s["deleted_at"] = now()
        s["updated_at"] = now()
        db["studies"].remove(s)
        db.setdefault("trash", []).append(s)
        return dict(
            study_id=study_id,
            status="deleted",
            note="已移入回收区；原始证据保留，可使用 undelete 恢复。",
        )

    return service.store.change(change)


def undelete(service, study_id):
    def change(db):
        s = next((s for s in db.get("trash", []) if s["id"] == study_id), None)
        require(s, "回收区找不到研究")
        require(not any(x["id"] == study_id for x in db["studies"]), "研究 ID 冲突")
        db["trash"].remove(s)
        s.pop("deleted_at")
        s["updated_at"] = now()
        db["studies"].append(s)
        return s

    return service.store.change(change)


def file_refs(db):
    for s in db["studies"] + db.get("trash", []):
        for a in s["analyses"]:
            yield a, "raw_file", a["sha256"]
        for d in s.get("documents", []):
            yield d, "raw_file", d["sha256"]
            yield d, "chunks_file", d["chunks_sha256"]


def backup(service, output):
    destination = absolute(output)
    require(not destination.exists(), "备份文件已存在，不覆盖")
    with service.store.locked():
        db = copy.deepcopy(service.store.read())
        payloads = {}
        size = 0
        for obj, key, expected in file_refs(db):
            file = Path(obj[key]).resolve()
            require(
                file.is_relative_to(service.store.directory / "raw"),
                "备份引用超出研究库 raw 目录",
            )
            name = "raw/" + file.name
            if name not in payloads:
                size += file.stat().st_size
                require(size <= MAX_BYTES, "备份原始材料超过 256 MiB")
                data = file.read_bytes()
                require(digest(data) == expected, "原始证据已变化，拒绝备份")
                payloads[name] = data
            require(digest(payloads[name]) == expected, "备份文件身份冲突")
            obj[key] = name
        database = encode(db)
        require(size + len(database) <= MAX_BYTES, "备份超过 256 MiB")
        payloads["research.json"] = database
        manifest = dict(
            format="featurelens-backup",
            version=1,
            created_at=now(),
            files={name: digest(data) for name, data in payloads.items()},
        )
        require(len(payloads) <= 10000, "备份文件过多")
        # Build outside destination; exclusive creation prevents overwrite races.
        with tempfile.TemporaryFile() as temp:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", encode(manifest))
                for name, data in payloads.items():
                    z.writestr(name, data)
            temp.seek(0)
            with destination.open("xb") as out:
                os.chmod(destination, 0o600)
                try:
                    shutil.copyfileobj(temp, out)
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
    return dict(
        path=str(destination),
        studies=len(db["studies"]),
        deleted_studies=len(db.get("trash", [])),
        files=len(payloads),
        note="备份包含材料原文和来源路径，请按研究数据保管。",
    )


def restore(service, path, destination):
    source = absolute(path)
    target = absolute(destination)
    require(not target.exists(), "恢复目标必须是尚不存在的新目录")
    require(source.stat().st_size <= MAX_BYTES, "备份文件超过 256 MiB")
    with zipfile.ZipFile(source) as z:
        entries = z.infolist()
        names = [x.filename for x in entries]
        require(
            len(names) == len(set(names)) and len(names) <= 10001,
            "重复或过多的备份条目",
        )
        require(
            sum(x.file_size for x in entries) <= MAX_BYTES + 1024 * 1024,
            "备份解压总量超过限制",
        )
        require("manifest.json" in names and "research.json" in names, "不是完整备份")
        require(z.getinfo("manifest.json").file_size <= 1024 * 1024, "清单过大")
        for name in names:
            p = PurePosixPath(name)
            require(
                not p.is_absolute()
                and ".." not in p.parts
                and "\\" not in name
                and p.as_posix() == name,
                "备份含不安全路径",
            )
            require(
                name in ("manifest.json", "research.json")
                or (
                    len(p.parts) == 2
                    and p.parts[0] == "raw"
                    and p.name not in (".", "..")
                ),
                "备份含未知条目",
            )
        manifest = json.loads(z.read("manifest.json"))
        require(
            manifest.get("format") == "featurelens-backup"
            and manifest.get("version") == 1,
            "不支持的备份格式",
        )
        require(
            set(manifest.get("files", {})) == set(names) - {"manifest.json"},
            "备份清单不匹配",
        )
        payloads = {name: z.read(name) for name in manifest["files"]}
        require(
            all(
                digest(data) == manifest["files"][name]
                for name, data in payloads.items()
            ),
            "备份哈希校验失败",
        )
    db = json.loads(payloads["research.json"])
    require(
        db.get("version") == 1
        and isinstance(db.get("studies"), list)
        and isinstance(db.get("trash", []), list),
        "研究库格式错误",
    )
    ids = set()
    for s in db["studies"] + db.get("trash", []):
        require(
            isinstance(s, dict)
            and re.fullmatch(r"r_[a-f0-9]{8}", s.get("id", ""))
            and s["id"] not in ids,
            "研究 ID 无效或重复",
        )
        ids.add(s["id"])
        for key in ("evidence", "analyses", "claims", "verifications"):
            require(isinstance(s.get(key), list), "研究记录缺少必要列表")
        # A backup cannot authorize access to paths on the receiving computer.
        if s.get("target"):
            s["restored_target"] = s["target"]
        s["target"] = None
        for a in s["analyses"]:
            a["origin"] = "restored"
    for obj, key, expected in file_refs(db):
        name = obj[key]
        require(
            name in payloads
            and name.startswith("raw/")
            and digest(payloads[name]) == expected,
            "原始证据引用或哈希无效",
        )
        obj[key] = str((target / name).resolve())
    # Do not use extractall: only validated member names are written.
    target.mkdir(mode=0o700)
    try:
        (target / "raw").mkdir(mode=0o700)
        for name, data in payloads.items():
            if name == "research.json":
                continue
            file = target / name
            file.write_bytes(data)
            file.chmod(0o600)
        (target / "research.json").write_bytes(encode(db))
        (target / "research.json").chmod(0o600)
    except BaseException:
        shutil.rmtree(target)
        raise
    return dict(
        directory=str(target),
        studies=len(db["studies"]),
        deleted_studies=len(db.get("trash", [])),
        note="已恢复到新目录；文档与报告可继续使用。原应用路径仅作为历史记录，重新分析请新建研究并明确目标。",
    )
