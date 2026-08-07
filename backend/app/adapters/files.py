"""File-store adapter (Pass 0 seam): local directory now, GCS behind the same
two calls in a GCP deployment.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..config import settings


def _root() -> Path:
    root = Path(settings.file_store_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_bytes(data: bytes, filename: str) -> str:
    """Store and return an opaque storage key (never a caller-chosen path)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[-80:]
    key = f"{uuid.uuid4().hex}_{safe}"
    (_root() / key).write_bytes(data)
    return key


def read_bytes(key: str) -> bytes:
    path = (_root() / key).resolve()
    if _root().resolve() not in path.parents:  # traversal guard
        raise ValueError("invalid storage key")
    return path.read_bytes()
