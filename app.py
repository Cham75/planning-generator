from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path


def _decode_python_source(source: bytes) -> str:
    """Decode the packaged source, including legacy Windows-encoded files."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return source.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Impossible de décoder le code de l'application Streamlit")


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
    return _decode_python_source(member.read())


exec(compile(_load_v6_app(), __file__, "exec"), globals())
