"""Requisition workflow — formal hiring request that, on approval, creates a vacancy.

Flow: requisition (pending) → approve → create vacancy → recruitment proceeds.
Existing recruitment routes work unchanged; this is an upstream entry point.
"""
from __future__ import annotations

from typing import Any

from .. import db as recruitment_db
from ..shared import audit
from ..shared.utils import new_id, now_iso


def list_requisitions(tenant_id: str, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM requisitions WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if status and status != "all":
        sql += " AND status = ?"; params.append(status)
    sql += " ORDER BY created_at DESC"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def get(tenant_id: str, rid: str) -> dict | None:
    with recruitment_db.connect() as c:
        r = c.execute(
            "SELECT * FROM requisitions WHERE tenant_id = ? AND id = ?",
            (tenant_id, rid),
        ).fetchone()
    return dict(r) if r else None


def create(tenant_id: str, data: dict, *, actor_id: str | None = None) -> dict:
    rid = new_id("req")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO requisitions
                (id, tenant_id, title, department_id, position_id, requested_by, openings,
                 employment_type, target_ctc_min, target_ctc_max, justification, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (rid, tenant_id, data["title"], data.get("department_id"), data.get("position_id"),
             actor_id or data.get("requested_by"), int(data.get("openings") or 1),
             data.get("employment_type") or "permanent",
             float(data.get("target_ctc_min") or 0) or None,
             float(data.get("target_ctc_max") or 0) or None,
             data.get("justification", ""), now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="requisition", entity_id=rid,
                  message=f'Requisition for {data["title"]} (×{data.get("openings", 1)})')
    return get(tenant_id, rid)


def decide(
    tenant_id: str, rid: str, *, approve: bool, approver_id: str,
) -> dict | None:
    """Approve creates a downstream vacancy and links it back to the requisition."""
    req = get(tenant_id, rid)
    if not req or req["status"] != "pending":
        return None
    new_status = "approved" if approve else "rejected"
    vacancy_id: str | None = None
    if approve:
        vacancy = recruitment_db.create_vacancy({
            "title": req["title"],
            "openings": req["openings"],
            "status": "Open",
            "priority": "Medium",
        })
        vacancy_id = vacancy["id"]
    with recruitment_db.connect() as c:
        c.execute(
            """UPDATE requisitions SET status = ?, approver_id = ?, decided_at = ?, vacancy_id = ?
               WHERE id = ?""",
            (new_status, approver_id, now_iso(), vacancy_id, rid),
        )
        audit.log(c, actor_id=approver_id, tenant_id=tenant_id, action=new_status,
                  entity_type="requisition", entity_id=rid,
                  message=f"Requisition {new_status}" + (f", vacancy {vacancy_id}" if vacancy_id else ""))
    return get(tenant_id, rid)
