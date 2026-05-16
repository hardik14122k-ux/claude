"""Arrears: salary differences owed for prior months (e.g. retroactive hike)."""
from __future__ import annotations

from .. import db as recruitment_db
from ..shared import audit
from ..shared.utils import new_id, now_iso


def add(
    tenant_id: str, employee_id: str, *,
    month: int, year: int, component: str, amount: float, reason: str = "",
    actor_id: str | None = None,
) -> dict:
    aid = new_id("arr")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO arrears
                (id, tenant_id, employee_id, month, year, component, amount, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, tenant_id, employee_id, month, year, component, amount, reason, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="arrear", entity_id=aid,
                  message=f"Arrear ₹{amount:,.0f} ({component}) for {month:02d}/{year}")
    return {"id": aid, "amount": amount, "component": component}


def list_unpaid(tenant_id: str, employee_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM arrears WHERE tenant_id = ? AND paid_in_run_id IS NULL"
    params = [tenant_id]
    if employee_id:
        sql += " AND employee_id = ?"; params.append(employee_id)
    sql += " ORDER BY year, month"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def mark_paid(tenant_id: str, arrear_ids: list[str], run_id: str) -> int:
    if not arrear_ids:
        return 0
    placeholders = ",".join("?" for _ in arrear_ids)
    with recruitment_db.connect() as c:
        cur = c.execute(
            f"UPDATE arrears SET paid_in_run_id = ? WHERE tenant_id = ? AND id IN ({placeholders})",
            [run_id, tenant_id] + arrear_ids,
        )
        return cur.rowcount or 0
