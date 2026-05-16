"""Employee expense reimbursements with approval workflow."""
from __future__ import annotations

from typing import Any

from .. import db as recruitment_db
from ..shared import audit
from ..shared.utils import new_id, now_iso


def submit(
    tenant_id: str, employee_id: str, *,
    category: str, amount: float, expense_date: str = "", description: str = "",
    receipt_doc_id: str | None = None, actor_id: str | None = None,
) -> dict:
    rid = new_id("rmb")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO reimbursements
                (id, tenant_id, employee_id, category, amount, expense_date, description,
                 receipt_doc_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (rid, tenant_id, employee_id, category, amount, expense_date,
             description, receipt_doc_id, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="reimbursement", entity_id=rid,
                  message=f"Reimbursement ₹{amount:,.0f} ({category})")
    return {"id": rid, "status": "pending"}


def list_requests(
    tenant_id: str, *, status: str | None = None, employee_id: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM reimbursements WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if status and status != "all":
        sql += " AND status = ?"; params.append(status)
    if employee_id:
        sql += " AND employee_id = ?"; params.append(employee_id)
    sql += " ORDER BY created_at DESC"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def decide(
    tenant_id: str, rid: str, *, approve: bool, approver_id: str,
) -> bool:
    new_status = "approved" if approve else "rejected"
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE reimbursements SET status = ?, approver_id = ?, decided_at = ? "
            "WHERE tenant_id = ? AND id = ?",
            (new_status, approver_id, now_iso(), tenant_id, rid),
        )
        audit.log(c, actor_id=approver_id, tenant_id=tenant_id, action=new_status,
                  entity_type="reimbursement", entity_id=rid,
                  message=f"Reimbursement {new_status}")
    return True
