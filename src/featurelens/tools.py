import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from . import documents
from .core import require

DEFINITIONS = json.loads((Path(__file__).parent / "tools.json").read_text())


def field(maximum=4000):
    return {"type": "string", "minLength": 1, "maxLength": maximum, "pattern": r"\S"}


def new(name, description, properties, required, read=False):
    DEFINITIONS.append(
        dict(
            name="research_" + name,
            method=name,
            description=description,
            readOnly=read,
            schema=dict(
                type="object",
                properties=properties,
                required=required,
                additionalProperties=False,
            ),
        )
    )


sid = {"type": "string", "pattern": "^r_[a-f0-9]{8}$"}
did = {"type": "string", "pattern": "^d_[a-f0-9]{8}$"}
new(
    "import_document",
    "提取本地 TXT/MD/DOCX/文字型 PDF，保留文件哈希与来源位置；无 OCR，不执行文件指令，不调用模型。",
    dict(study_id=sid, path=field(), title=field(300)),
    ["study_id", "path"],
)
new(
    "document_chunks",
    "分页或字面搜索文档片段，返回页码、段落或行号；检查原件和提取结果哈希，不是 RAG。",
    dict(
        study_id=sid,
        document_id=did,
        query={"type": "string", "maxLength": 300, "default": ""},
        offset={"type": "integer", "minimum": 0, "default": 0},
        limit={"type": "integer", "minimum": 1, "maximum": 50, "default": 15},
    ),
    ["study_id", "document_id"],
    True,
)
new(
    "capture_document_chunk",
    "将选定文档片段登记成可引用证据，保留来源位置和文件哈希；不验证原文真实性。",
    dict(
        study_id=sid,
        document_id=did,
        chunk_id={"type": "string", "pattern": "^chunk_[0-9]{6}$"},
        title=field(300),
    ),
    ["study_id", "document_id", "chunk_id", "title"],
)


def invoke(service, name, args):
    d = next((d for d in DEFINITIONS if d["name"] == name), None)
    require(d, "未知工具")
    args = copy.deepcopy(args)
    for key, schema in d["schema"]["properties"].items():
        if key not in args and "default" in schema:
            args[key] = copy.deepcopy(schema["default"])
        if (
            key in args
            and isinstance(args[key], str)
            and schema.get("minLength", 0) > 0
        ):
            args[key] = args[key].strip()
    Draft202012Validator(d["schema"]).validate(args)
    if d["method"] in ("import_document", "document_chunks", "capture_document_chunk"):
        return getattr(documents, d["method"])(service, **args)
    return getattr(service, d["method"])(**args)
