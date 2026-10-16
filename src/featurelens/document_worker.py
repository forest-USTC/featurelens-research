"""Bounded subprocess entry point; input is a snapshot, never an executable."""

import json
from pathlib import Path
import sys
from .documents import extract

try:
    chunks, warnings = extract(Path(sys.argv[1]).read_bytes(), sys.argv[2])
    print(json.dumps(dict(chunks=chunks, warnings=warnings), ensure_ascii=False))
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
