"""Employee/candidate/payslip document store. Wraps shared.storage."""
from __future__ import annotations

from typing import BinaryIO

from .. import db as recruitment_db
from ..shared import audit, storage
from ..shared.utils import now_iso


def upload(
    tenant_id: str,
    *,
    owner_type: str,
    owner_id: str,
    stream: BinaryIO,
    file_name: str,
    category: str = "",
    title: str = "",
    is_confidential: bool = False,
    uploaded_by: str | None = None,
) -> dict:
    descriptor = storage.save(stream, file_name, tenant_id)
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO documents
                (id, tenant_id, owner_type, owner_id, category, title, file_name,
                 storage_path, size_bytes, sha256, content_type, uploaded_by,
                 is_confidential, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (descriptor["doc_id"], tenant_id, owner_type, owner_id, category, title,
             file_name, descriptor["path"], descriptor["size_bytes"], descriptor["sha256"],
             descriptor["content_type"], uploaded_by, 1 if is_confidential else 0, now_iso()),
        )
        audit.log(c, actor_id=uploaded_by, tenant_id=tenant_id, action="upload",
                  entity_type="document", entity_id=descriptor["doc_id"],
                  message=f"Uploaded {file_name} for {owner_type}:{owner_id}")
    return {"id": descriptor["doc_id"], **descriptor}


def list_for_owner(tenant_id: str, owner_type: str, owner_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(
            """SELECT id, tenant_id, owner_type, owner_id, category, title, file_name,
                      size_bytes, content_type, uploaded_by, is_confidential, created_at
               FROM documents
               WHERE tenant_id = ? AND owner_type = ? AND owner_id = ?
               ORDER BY created_at DESC""",
            (tenant_id, owner_type, owner_id),
        ).fetchall()]


def get(tenant_id: str, doc_id: str) -> dict | None:
    with recruitment_db.connect() as c:
        r = c.execute(
            "SELECT * FROM documents WHERE tenant_id = ? AND id = ?",
            (tenant_id, doc_id),
        ).fetchone()
    return dict(r) if r else None


def delete(tenant_id: str, doc_id: str, *, actor_id: str | None = None) -> bool:
    doc = get(tenant_id, doc_id)
    if not doc:
        return False
    storage.delete(doc_id, doc["file_name"], tenant_id)
    with recruitment_db.connect() as c:
        c.execute("DELETE FROM documents WHERE tenant_id = ? AND id = ?", (tenant_id, doc_id))
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="delete",
                  entity_type="document", entity_id=doc_id,
                  message=f"Deleted {doc['file_name']}")
    return True
