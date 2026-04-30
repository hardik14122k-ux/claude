"""Payslip generation, persistence, and payroll-run lifecycle.

A payroll_run groups payslips for one (tenant, month, year). The run goes
through draft → processing → processed → approved → paid → locked. Locked
runs are immutable.
"""
from __future__ import annotations

import json
from typing import Any

from .. import db as recruitment_db
from .. import payroll as engine
from ..hrms import attendance, employee as employee_master
from ..shared import audit
from ..shared.utils import new_id, now_iso
from . import structures


# ---------- Payroll runs ----------

def list_runs(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM payroll_runs WHERE tenant_id = ? ORDER BY year DESC, month DESC",
            (tenant_id,),
        ).fetchall()]


def get_run(tenant_id: str, run_id: str) -> dict | None:
    with recruitment_db.connect() as c:
        r = c.execute(
            "SELECT * FROM payroll_runs WHERE tenant_id = ? AND id = ?",
            (tenant_id, run_id),
        ).fetchone()
    return dict(r) if r else None


def get_or_create_run(
    tenant_id: str, *, month: int, year: int, working_days: int,
    actor_id: str | None = None,
) -> dict:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM payroll_runs WHERE tenant_id = ? AND month = ? AND year = ?",
            (tenant_id, month, year),
        ).fetchone()
        if row:
            return dict(row)
        rid = new_id("prun")
        c.execute(
            """INSERT INTO payroll_runs
                (id, tenant_id, month, year, status, working_days, created_at)
               VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
            (rid, tenant_id, month, year, working_days, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="payroll_run", entity_id=rid,
                  message=f"Run created for {month:02d}/{year}")
    return get_run(tenant_id, rid)


def process_run(
    tenant_id: str, run_id: str, *, actor_id: str | None = None,
    only_employee_ids: list[str] | None = None,
) -> int:
    """Generate payslips for every active employee with a current salary structure.
    Returns count of payslips created/updated."""
    run = get_run(tenant_id, run_id)
    if not run or run["status"] in ("approved", "locked"):
        return 0
    employees = employee_master.list_employees(tenant_id, status="active")
    if only_employee_ids:
        employees = [e for e in employees if e["id"] in only_employee_ids]

    count = 0
    with recruitment_db.connect() as c:
        c.execute("UPDATE payroll_runs SET status = 'processing' WHERE id = ?", (run_id,))

    for emp in employees:
        struct_row = structures.current(tenant_id, emp["id"])
        if not struct_row:
            continue
        location = structures._location_to_engine(tenant_id, struct_row.get("location_id"))
        structure = structures.to_engine_structure(struct_row)

        att_summary = attendance.monthly_summary(tenant_id, emp["id"], run["year"], run["month"])
        paid_days = att_summary["paid_days"] or run["working_days"]

        payslip = engine.generate_payslip(
            employee={"tax_regime": "new"},
            structure=structure,
            location=location,
            month=run["month"],
            year=run["year"],
            working_days=run["working_days"],
            paid_days=paid_days,
        )
        _persist_payslip(tenant_id, run_id, emp["id"], payslip)
        count += 1

    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE payroll_runs SET status = 'processed', processed_by = ?, processed_at = ? WHERE id = ?",
            (actor_id, now_iso(), run_id),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="process",
                  entity_type="payroll_run", entity_id=run_id,
                  message=f"Processed {count} payslip(s)")
    return count


def _persist_payslip(tenant_id: str, run_id: str, employee_id: str, payslip: dict) -> str:
    pid = new_id("pslp")
    with recruitment_db.connect() as c:
        existing = c.execute(
            "SELECT id FROM payslips WHERE tenant_id = ? AND payroll_run_id = ? AND employee_id = ?",
            (tenant_id, run_id, employee_id),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE payslips
                   SET working_days = ?, paid_days = ?, earnings = ?, deductions = ?,
                       employer_contributions = ?, gross_earnings = ?, total_deductions = ?,
                       net_pay = ?, ctc_total = ?
                   WHERE id = ?""",
                (payslip["working_days"], payslip["paid_days"],
                 json.dumps(payslip["earnings"]), json.dumps(payslip["deductions"]),
                 json.dumps(payslip["employer_contributions"]),
                 payslip["gross_earnings"], payslip["total_deductions"],
                 payslip["net_pay"], payslip["ctc_total"], existing["id"]),
            )
            return existing["id"]
        c.execute(
            """INSERT INTO payslips
                (id, tenant_id, payroll_run_id, employee_id, month, year, working_days, paid_days,
                 earnings, deductions, employer_contributions,
                 gross_earnings, total_deductions, net_pay, ctc_total, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, tenant_id, run_id, employee_id, payslip["month"], payslip["year"],
             payslip["working_days"], payslip["paid_days"],
             json.dumps(payslip["earnings"]), json.dumps(payslip["deductions"]),
             json.dumps(payslip["employer_contributions"]),
             payslip["gross_earnings"], payslip["total_deductions"],
             payslip["net_pay"], payslip["ctc_total"], now_iso()),
        )
    return pid


def approve_run(tenant_id: str, run_id: str, *, approver_id: str) -> bool:
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE payroll_runs SET status = 'approved', approved_by = ?, approved_at = ? "
            "WHERE id = ? AND tenant_id = ? AND status = 'processed'",
            (approver_id, now_iso(), run_id, tenant_id),
        )
        audit.log(c, actor_id=approver_id, tenant_id=tenant_id, action="approve",
                  entity_type="payroll_run", entity_id=run_id, message="Run approved")
    return True


def lock_run(tenant_id: str, run_id: str, *, actor_id: str | None = None) -> bool:
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE payroll_runs SET status = 'locked', locked_at = ? "
            "WHERE id = ? AND tenant_id = ? AND status IN ('approved','paid')",
            (now_iso(), run_id, tenant_id),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="lock",
                  entity_type="payroll_run", entity_id=run_id, message="Run locked")
    return True


# ---------- Payslip queries ----------

def list_for_run(tenant_id: str, run_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        rows = c.execute(
            """SELECT p.*, e.first_name, e.last_name, e.employee_code
               FROM payslips p JOIN employees e ON e.id = p.employee_id
               WHERE p.tenant_id = ? AND p.payroll_run_id = ?
               ORDER BY e.employee_code""",
            (tenant_id, run_id),
        ).fetchall()
    return [_decode(r) for r in rows]


def list_for_employee(tenant_id: str, employee_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        rows = c.execute(
            "SELECT * FROM payslips WHERE tenant_id = ? AND employee_id = ? "
            "ORDER BY year DESC, month DESC",
            (tenant_id, employee_id),
        ).fetchall()
    return [_decode(r) for r in rows]


def get(tenant_id: str, payslip_id: str) -> dict | None:
    with recruitment_db.connect() as c:
        r = c.execute("SELECT * FROM payslips WHERE tenant_id = ? AND id = ?",
                      (tenant_id, payslip_id)).fetchone()
    return _decode(r) if r else None


def _decode(row: Any) -> dict:
    d = dict(row)
    for k in ("earnings", "deductions", "employer_contributions"):
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                d[k] = {}
    return d
