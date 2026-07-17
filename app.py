from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path


def _load_v6_app() -> str:
    root = Path(__file__).resolve().parent
    payload_dir = root / ".v6_payload"
    encoded = "".join(
        (payload_dir / f"part_{index:02d}").read_text(encoding="utf-8")
        for index in range(4)
    )
    archive = tarfile.open(fileobj=io.BytesIO(base64.b64decode(encoded)), mode="r:gz")
    member = archive.extractfile("./app.py")
    if member is None:
        raise RuntimeError("Source Streamlit v6 introuvable")
    return member.read().decode("utf-8")


exec(compile(_load_v6_app(), __file__, "exec"), globals())
