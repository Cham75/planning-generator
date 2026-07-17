from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path


def _load_v6_source(path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    payload_dir = root / ".v6_payload"
    encoded = "".join(
        (payload_dir / f"part_{index:02d}").read_text(encoding="utf-8")
        for index in range(4)
    )
    archive = tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded)), mode="r:gz")
    member = archive.extractfile(path)
    if member is None:
        raise RuntimeError(f"Source v6 introuvable : {path}")
    return member.read().decode("utf-8")


exec(compile(_load_v6_source("./planning_tool/scheduler.py"), __file__, "exec"), globals())
