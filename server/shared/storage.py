"""File/document storage abstraction.

Wraps local filesystem storage (default). Replace _backend with an S3
or GCS implementation without changing call sites.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO

from .. import config
from .utils import new_id


def save(stream: BinaryIO, original_name: str, tenant_id: str = "default") -> dict:
    """Persist an uploaded file. Returns a document descriptor dict."""
    doc_id = new_id("doc")
    suffix = Path(original_name).suffix.lower()
    tenant_dir = config.UPLOAD_DIR / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    dest = tenant_dir / f"{doc_id}{suffix}"
    data = stream.read()
    dest.write_bytes(data)
    return {
        "doc_id": doc_id,
        "original_name": original_name,
        "path": str(dest),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_type": _guess_content_type(suffix),
    }


def get_path(doc_id: str, original_name: str, tenant_id: str = "default") -> Path | None:
    suffix = Path(original_name).suffix.lower()
    p = config.UPLOAD_DIR / tenant_id / f"{doc_id}{suffix}"
    return p if p.exists() else None


def delete(doc_id: str, original_name: str, tenant_id: str = "default") -> bool:
    p = get_path(doc_id, original_name, tenant_id)
    if p:
        p.unlink(missing_ok=True)
        return True
    return False


def _guess_content_type(suffix: str) -> str:
    return {
        ".pdf":  "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc":  "application/msword",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".txt":  "text/plain",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(suffix, "application/octet-stream")
