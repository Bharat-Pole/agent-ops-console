"""Emit the generated file map to a directory or a byte-stable zip.

Determinism: a dict {relpath: content} is written in sorted order; the zip uses a
fixed timestamp + fixed permissions + sorted names, so identical input → identical
zip bytes (golden-diffable).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)  # earliest zip epoch → no wall-clock leakage


def write_dir(files: dict[str, str], out_dir: str | Path) -> Path:
    out = Path(out_dir)
    for rel in sorted(files):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(files[rel], encoding="utf-8", newline="\n")
    return out


def write_zip(files: dict[str, str], root: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(files):
            name = f"{root.rstrip('/')}/{rel}" if root else rel
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[rel].encode("utf-8"))
    return buf.getvalue()


def file_tree(files: dict[str, str]) -> list[str]:
    return sorted(files)
