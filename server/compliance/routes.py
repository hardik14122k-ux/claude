"""Compliance blueprint: rules dashboard and reminders."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..hrms import employee as employee_master
from ..payroll_ext import payslips as payslip_store, structures
from ..shared.auth import current_tenant, current_user, login_required, role_required
from . import engine, reminders


compliance_bp = Blueprint("compliance", __name__, url_prefix="/compliance")


@compliance_bp.route("/")
@login_required
@role_required("hr_admin", "hr_manager")
def dashboard():
    tenant = current_tenant()
    employees = employee_master.list_employees(tenant, status="active")
    findings_by_employee = []
    for e in employees:
        struct = structures.current(tenant, e["id"])
        if not struct:
            continue
        ctx = {
            "basic_monthly": (struct["basic_annual"] or 0) / 12,
            "gross_monthly": ((struct["basic_annual"] or 0) + (struct["hra_annual"] or 0)
                              + (struct["special_allowance_annual"] or 0)) / 12,
            "annual_gross": struct["ctc_annual"],
            "state": e.get("state", ""),
            "tenure_months": _months_since(e.get("date_joined")),
        }
        findings = engine.evaluate(ctx)
        if findings:
            findings_by_employee.append({"employee": e, "findings": findings})
    open_reminders = reminders.list_open(tenant, days_ahead=60)
    return render_template(
        "compliance/dashboard.html",
        findings_by_employee=findings_by_employee, reminders=open_reminders,
    )


@compliance_bp.route("/reminders/seed", methods=["POST"])
@login_required
@role_required("hr_admin")
def reminders_seed():
    n = reminders.seed_for_year(current_tenant(), int(request.form.get("year") or date.today().year))
    flash(f"Seeded {n} reminders", "ok")
    return redirect(url_for("compliance.dashboard"))


@compliance_bp.route("/reminders/<rid>/done", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def reminder_done(rid: str):
    reminders.mark_done(current_tenant(), rid)
    flash("Reminder marked complete", "ok")
    return redirect(url_for("compliance.dashboard"))


def _months_since(iso: str | None) -> int:
    if not iso:
        return 0
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return 0
    today = date.today()
    return (today.year - d.year) * 12 + (today.month - d.month)
