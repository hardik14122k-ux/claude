"""Leave management — types, balances, requests, approvals.

Balances are tracked per (employee, leave_type, fiscal year). Requests
deduct from `used` only on approval; rejection / cancellation is a no-op.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .. import db as recruitment_db
from ..shared.utils import fiscal_year, new_id, now_iso, parse_iso
from ..shared import audit, notifications


def working_days(start: str, end: str) -> float:
    """Inclusive count of days between two YYYY-MM-DD strings, Sundays excluded."""
    s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if e < s:
        return 0
    total = 0
    cur = s
    while cur <= e:
        if cur.weekday() != 6:
            total += 1
        cur += timedelta(days=1)
    return float(total)


def get_or_create_balance(tenant_id: str, employee_id: str, leave_type_id: str,
                          fy: int | None = None) -> dict:
    fy = fy or fiscal_year()
    with recruitment_db.connect() as c:
        row = c.execute(
            """SELECT * FROM leave_balances
               WHERE tenant_id = ? AND employee_id = ? AND leave_type_id = ? AND fy_year = ?""",
            (tenant_id, employee_id, leave_type_id, fy),
        ).fetchone()
        if row:
            return dict(row)
        # Initialise with the leave type's annual quota.
        lt = c.execute("SELECT * FROM leave_types WHERE id = ?", (leave_type_id,)).fetchone()
        opening = float(lt["annual_quota"]) if lt else 0
        bid = new_id("bal")
        c.execute(
            """INSERT INTO leave_balances
                (id, tenant_id, employee_id, leave_type_id, fy_year, opening, accrued, used, encashed)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0)""",
            (bid, tenant_id, employee_id, leave_type_id, fy, opening),
        )
        return dict(c.execute("SELECT * FROM leave_balances WHERE id = ?", (bid,)).fetchone())


def list_balances(tenant_id: str, employee_id: str, fy: int | None = None) -> list[dict]:
    fy = fy or fiscal_year()
    with recruitment_db.connect() as c:
        rows = c.execute(
            """SELECT lb.*, lt.code AS leave_code, lt.name AS leave_name
               FROM leave_balances lb
               JOIN leave_types lt ON lt.id = lb.leave_type_id
               WHERE lb.tenant_id = ? AND lb.employee_id = ? AND lb.fy_year = ?
               ORDER BY lt.code""",
            (tenant_id, employee_id, fy),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["available"] = (d.get("opening") or 0) + (d.get("accrued") or 0) - (d.get("used") or 0) - (d.get("encashed") or 0)
        out.append(d)
    return out


def request_leave(
    tenant_id: str, employee_id: str, leave_type_id: str,
    start: str, end: str, reason: str = "",
    *, actor_id: str | None = None,
) -> dict:
    days = working_days(start, end)
    if days <= 0:
        raise ValueError("End date must be on or after start date")
    rid = new_id("lvr")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO leave_requests
                (id, tenant_id, employee_id, leave_type_id, start_date, end_date, days,
                 reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (rid, tenant_id, employee_id, leave_type_id, start, end, days, reason, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="leave_request", entity_id=rid,
                  message=f"Leave requested {start}→{end} ({days}d)")
    return {"id": rid, "days": days, "status": "pending"}


def list_requests(
    tenant_id: str, *, employee_id: str | None = None, status: str | None = None,
) -> list[dict]:
    sql = """SELECT lr.*, lt.code AS leave_code, lt.name AS leave_name,
                    e.first_name, e.last_name, e.employee_code
             FROM leave_requests lr
             JOIN leave_types lt ON lt.id = lr.leave_type_id
             JOIN employees e ON e.id = lr.employee_id
             WHERE lr.tenant_id = ?"""
    params: list[Any] = [tenant_id]
    if employee_id:
        sql += " AND lr.employee_id = ?"; params.append(employee_id)
    if status and status != "all":
        sql += " AND lr.status = ?"; params.append(status)
    sql += " ORDER BY lr.created_at DESC"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def decide_request(
    tenant_id: str, rid: str, *, approve: bool, approver_id: str, note: str = "",
) -> bool:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM leave_requests WHERE tenant_id = ? AND id = ?",
            (tenant_id, rid),
        ).fetchone()
        if not row or row["status"] != "pending":
            return False
        new_status = "approved" if approve else "rejected"
        c.execute(
            """UPDATE leave_requests SET status = ?, approver_id = ?, decided_at = ?, decision_note = ?
               WHERE id = ?""",
            (new_status, approver_id, now_iso(), note, rid),
        )
        audit.log(c, actor_id=approver_id, tenant_id=tenant_id, action=new_status,
                  entity_type="leave_request", entity_id=rid,
                  message=f"Leave {new_status}: {row['days']}d")
        if approve:
            # Apply to balance, ensuring it exists first.
            bal = c.execute(
                """SELECT * FROM leave_balances WHERE tenant_id = ? AND employee_id = ?
                   AND leave_type_id = ? AND fy_year = ?""",
                (tenant_id, row["employee_id"], row["leave_type_id"],
                 fiscal_year(parse_iso(row["start_date"] + "T00:00:00"))),
            ).fetchone()
            if not bal:
                # Inline create-balance to stay in same transaction.
                lt = c.execute("SELECT * FROM leave_types WHERE id = ?", (row["leave_type_id"],)).fetchone()
                opening = float(lt["annual_quota"]) if lt else 0
                bid = new_id("bal")
                c.execute(
                    """INSERT INTO leave_balances
                        (id, tenant_id, employee_id, leave_type_id, fy_year, opening, accrued, used, encashed)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0)""",
                    (bid, tenant_id, row["employee_id"], row["leave_type_id"],
                     fiscal_year(parse_iso(row["start_date"] + "T00:00:00")),
                     opening, row["days"]),
                )
            else:
                c.execute(
                    "UPDATE leave_balances SET used = used + ? WHERE id = ?",
                    (row["days"], bal["id"]),
                )
    # Best-effort notify employee.
    with recruitment_db.connect() as c:
        emp = c.execute("SELECT email, phone, first_name FROM employees WHERE id = ?",
                        (row["employee_id"],)).fetchone()
    if emp:
        notifications.notify(
            email=emp["email"], phone=emp["phone"],
            subject=f"Leave request {new_status}",
            body=f"Hi {emp['first_name']}, your leave request from {row['start_date']} to {row['end_date']} was {new_status}.",
        )
    return True


def cancel_request(tenant_id: str, rid: str, *, actor_id: str | None = None) -> bool:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM leave_requests WHERE tenant_id = ? AND id = ?",
            (tenant_id, rid),
        ).fetchone()
        if not row:
            return False
        if row["status"] == "approved":
            # Roll back balance.
            c.execute(
                """UPDATE leave_balances SET used = used - ?
                   WHERE tenant_id = ? AND employee_id = ? AND leave_type_id = ?""",
                (row["days"], tenant_id, row["employee_id"], row["leave_type_id"]),
            )
        c.execute(
            "UPDATE leave_requests SET status = 'cancelled', decided_at = ? WHERE id = ?",
            (now_iso(), rid),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="cancel",
                  entity_type="leave_request", entity_id=rid, message="Leave cancelled")
    return True


def accrue_monthly(tenant_id: str, fy: int | None = None) -> int:
    """Add monthly accruals for all leave_types whose accrual='monthly'.
    Returns number of balance rows updated. Run once per month from a cron.
    """
    fy = fy or fiscal_year()
    updated = 0
    with recruitment_db.connect() as c:
        types = c.execute(
            "SELECT * FROM leave_types WHERE tenant_id = ? AND accrual = 'monthly'",
            (tenant_id,),
        ).fetchall()
        for lt in types:
            monthly_accrual = (lt["annual_quota"] or 0) / 12.0
            employees = c.execute(
                "SELECT id FROM employees WHERE tenant_id = ? AND status = 'active'",
                (tenant_id,),
            ).fetchall()
            for e in employees:
                bal = c.execute(
                    """SELECT id FROM leave_balances WHERE tenant_id = ? AND employee_id = ?
                       AND leave_type_id = ? AND fy_year = ?""",
                    (tenant_id, e["id"], lt["id"], fy),
                ).fetchone()
                if bal:
                    c.execute(
                        "UPDATE leave_balances SET accrued = accrued + ? WHERE id = ?",
                        (monthly_accrual, bal["id"]),
                    )
                else:
                    c.execute(
                        """INSERT INTO leave_balances (id, tenant_id, employee_id, leave_type_id,
                                                        fy_year, opening, accrued, used, encashed)
                           VALUES (?, ?, ?, ?, ?, 0, ?, 0, 0)""",
                        (new_id("bal"), tenant_id, e["id"], lt["id"], fy, monthly_accrual),
                    )
                updated += 1
    return updated
