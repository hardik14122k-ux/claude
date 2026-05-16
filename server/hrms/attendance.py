"""Attendance tracking + regularization workflow.

Single attendance row per (tenant, employee, date). Status drives the
payroll paid-days calculation in payroll_ext.payslips.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db as recruitment_db
from ..shared.utils import new_id, now_iso, parse_iso
from ..shared import audit


VALID_STATUSES = {"present", "absent", "half_day", "leave", "holiday", "weekoff"}


def upsert(
    tenant_id: str,
    employee_id: str,
    date: str,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
    status: str = "present",
    source: str = "manual",
    notes: str = "",
    actor_id: str | None = None,
) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status}")
    work_minutes = 0
    if check_in and check_out:
        ci, co = parse_iso(check_in), parse_iso(check_out)
        if ci and co and co > ci:
            work_minutes = int((co - ci).total_seconds() // 60)
    aid = new_id("att")
    with recruitment_db.connect() as c:
        existing = c.execute(
            "SELECT * FROM attendance WHERE tenant_id = ? AND employee_id = ? AND date = ?",
            (tenant_id, employee_id, date),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE attendance SET check_in = ?, check_out = ?, work_minutes = ?,
                       status = ?, source = ?, notes = ?
                   WHERE id = ?""",
                (check_in, check_out, work_minutes, status, source, notes, existing["id"]),
            )
            audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="update",
                      entity_type="attendance", entity_id=existing["id"],
                      message=f"Attendance {date} → {status}")
            aid = existing["id"]
        else:
            c.execute(
                """INSERT INTO attendance (id, tenant_id, employee_id, date, check_in, check_out,
                                            work_minutes, status, source, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (aid, tenant_id, employee_id, date, check_in, check_out, work_minutes,
                 status, source, notes, now_iso()),
            )
            audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                      entity_type="attendance", entity_id=aid,
                      message=f"Attendance {date} → {status}")
    with recruitment_db.connect() as c:
        return dict(c.execute("SELECT * FROM attendance WHERE id = ?", (aid,)).fetchone())


def check_in(tenant_id: str, employee_id: str, ts: str | None = None) -> dict:
    ts = ts or now_iso()
    date = ts[:10]
    return upsert(tenant_id, employee_id, date, check_in=ts, status="present")


def check_out(tenant_id: str, employee_id: str, ts: str | None = None) -> dict:
    ts = ts or now_iso()
    date = ts[:10]
    with recruitment_db.connect() as c:
        existing = c.execute(
            "SELECT * FROM attendance WHERE tenant_id = ? AND employee_id = ? AND date = ?",
            (tenant_id, employee_id, date),
        ).fetchone()
    ci = existing["check_in"] if existing else None
    return upsert(tenant_id, employee_id, date, check_in=ci, check_out=ts, status="present")


def list_for_employee(tenant_id: str, employee_id: str, year: int, month: int) -> list[dict]:
    pad = f"{year}-{month:02d}-"
    with recruitment_db.connect() as c:
        rows = c.execute(
            "SELECT * FROM attendance WHERE tenant_id = ? AND employee_id = ? "
            "AND date LIKE ? ORDER BY date",
            (tenant_id, employee_id, f"{pad}%"),
        ).fetchall()
    return [dict(r) for r in rows]


def monthly_summary(tenant_id: str, employee_id: str, year: int, month: int) -> dict:
    rows = list_for_employee(tenant_id, employee_id, year, month)
    counts = {s: 0 for s in VALID_STATUSES}
    minutes = 0
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        minutes += r.get("work_minutes") or 0
    paid_days = counts["present"] + counts["half_day"] * 0.5 + counts["leave"] + counts["holiday"] + counts["weekoff"]
    working_days = _working_days_in_month(tenant_id, year, month)
    return {
        "year": year,
        "month": month,
        "counts": counts,
        "total_work_hours": round(minutes / 60, 1),
        "paid_days": paid_days,
        "working_days": working_days,
    }


def _working_days_in_month(tenant_id: str, year: int, month: int) -> int:
    """Calendar days minus Sundays minus holidays in that month."""
    from .schema import list_holidays
    holidays = {h["date"] for h in list_holidays(tenant_id, year)
                if h["date"].startswith(f"{year}-{month:02d}-")}
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    days = 0
    while d.month == month:
        if d.weekday() != 6 and d.strftime("%Y-%m-%d") not in holidays:
            days += 1
        d += timedelta(days=1)
    return days


# ---------- Regularization ----------

def request_regularization(
    tenant_id: str, employee_id: str, date: str, *,
    requested_check_in: str | None = None,
    requested_check_out: str | None = None,
    reason: str = "",
    actor_id: str | None = None,
) -> dict:
    rid = new_id("reg")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO attendance_regularizations
                (id, tenant_id, employee_id, date, requested_check_in, requested_check_out,
                 reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (rid, tenant_id, employee_id, date, requested_check_in, requested_check_out,
             reason, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="attendance_reg", entity_id=rid,
                  message=f"Regularization requested for {date}")
    return {"id": rid, "status": "pending"}


def decide_regularization(
    tenant_id: str, rid: str, *, approve: bool, approver_id: str,
) -> bool:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM attendance_regularizations WHERE tenant_id = ? AND id = ?",
            (tenant_id, rid),
        ).fetchone()
        if not row or row["status"] != "pending":
            return False
        new_status = "approved" if approve else "rejected"
        c.execute(
            "UPDATE attendance_regularizations SET status = ?, approver_id = ?, decided_at = ? WHERE id = ?",
            (new_status, approver_id, now_iso(), rid),
        )
        audit.log(c, actor_id=approver_id, tenant_id=tenant_id, action=new_status,
                  entity_type="attendance_reg", entity_id=rid,
                  message=f"Regularization {new_status}")
    if approve:
        upsert(tenant_id, row["employee_id"], row["date"],
               check_in=row["requested_check_in"], check_out=row["requested_check_out"],
               status="present", source="regularization", actor_id=approver_id)
    return True


def list_pending_regularizations(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        rows = c.execute(
            "SELECT * FROM attendance_regularizations WHERE tenant_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
    return [dict(r) for r in rows]
