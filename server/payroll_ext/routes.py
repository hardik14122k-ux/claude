"""Payroll blueprint: structures, runs, payslips, reimbursements, year-end."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..hrms import attendance, employee as employee_master
from ..shared.auth import current_tenant, current_user, login_required, role_required
from . import arrears, payslips as payslip_store, reimbursements, structures, yearend


payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")


# ============ Salary structures ============

@payroll_bp.route("/structures")
@login_required
@role_required("hr_admin", "hr_manager")
def structures_list():
    tenant = current_tenant()
    employees = employee_master.list_employees(tenant, status="active")
    rows = []
    for e in employees:
        cur = structures.current(tenant, e["id"])
        rows.append({"employee": e, "structure": cur})
    return render_template("payroll/structures.html", rows=rows,
                            locations=structures.list_locations(tenant))


@payroll_bp.route("/structures/<eid>", methods=["GET", "POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def structure_edit(eid: str):
    tenant = current_tenant()
    emp = employee_master.get_employee(tenant, eid)
    if not emp:
        abort(404)
    if request.method == "POST":
        structures.upsert(
            tenant, eid,
            ctc_annual=float(request.form["ctc_annual"]),
            location_id=request.form.get("location_id") or None,
            effective_from=request.form.get("effective_from") or None,
            basic_pct=float(request.form.get("basic_pct") or 40.0),
            conveyance_monthly=float(request.form.get("conveyance_monthly") or 0),
            medical_monthly=float(request.form.get("medical_monthly") or 0),
            lta_annual=float(request.form.get("lta_annual") or 0),
            bonus_annual=float(request.form.get("bonus_annual") or 0),
            actor_id=(current_user() or {}).get("id"),
        )
        flash("Salary structure saved", "ok")
        return redirect(url_for("payroll.structure_edit", eid=eid))
    return render_template(
        "payroll/structure_edit.html",
        employee=emp,
        history=structures.list_for_employee(tenant, eid),
        current=structures.current(tenant, eid),
        locations=structures.list_locations(tenant),
    )


# ============ Payroll runs ============

@payroll_bp.route("/runs")
@login_required
@role_required("hr_admin", "hr_manager")
def runs_list():
    tenant = current_tenant()
    return render_template("payroll/runs.html", runs=payslip_store.list_runs(tenant))


@payroll_bp.route("/runs/new", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def run_new():
    tenant = current_tenant()
    month = int(request.form["month"])
    year = int(request.form["year"])
    working_days = int(request.form.get("working_days") or 22)
    run = payslip_store.get_or_create_run(
        tenant, month=month, year=year, working_days=working_days,
        actor_id=(current_user() or {}).get("id"),
    )
    flash(f"Run created for {month:02d}/{year}", "ok")
    return redirect(url_for("payroll.run_detail", run_id=run["id"]))


@payroll_bp.route("/runs/<run_id>")
@login_required
@role_required("hr_admin", "hr_manager")
def run_detail(run_id: str):
    tenant = current_tenant()
    run = payslip_store.get_run(tenant, run_id)
    if not run:
        abort(404)
    slips = payslip_store.list_for_run(tenant, run_id)
    return render_template("payroll/run_detail.html", run=run, slips=slips)


@payroll_bp.route("/runs/<run_id>/process", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def run_process(run_id: str):
    n = payslip_store.process_run(
        current_tenant(), run_id, actor_id=(current_user() or {}).get("id"),
    )
    flash(f"Generated {n} payslip(s)", "ok")
    return redirect(url_for("payroll.run_detail", run_id=run_id))


@payroll_bp.route("/runs/<run_id>/approve", methods=["POST"])
@login_required
@role_required("hr_admin")
def run_approve(run_id: str):
    payslip_store.approve_run(current_tenant(), run_id, approver_id=(current_user() or {}).get("id"))
    flash("Run approved", "ok")
    return redirect(url_for("payroll.run_detail", run_id=run_id))


@payroll_bp.route("/runs/<run_id>/lock", methods=["POST"])
@login_required
@role_required("hr_admin")
def run_lock(run_id: str):
    payslip_store.lock_run(current_tenant(), run_id, actor_id=(current_user() or {}).get("id"))
    flash("Run locked", "ok")
    return redirect(url_for("payroll.run_detail", run_id=run_id))


# ============ Payslips ============

@payroll_bp.route("/payslips/<pid>")
@login_required
def payslip_detail(pid: str):
    tenant = current_tenant()
    slip = payslip_store.get(tenant, pid)
    if not slip:
        abort(404)
    user = current_user() or {}
    # Permit only the owning employee or hr roles to view
    if user.get("role") not in ("hr_admin", "hr_manager", "super_admin"):
        if user.get("employee_id") != slip["employee_id"]:
            abort(403)
    emp = employee_master.get_employee(tenant, slip["employee_id"])
    return render_template("payroll/payslip.html", slip=slip, employee=emp)


# ============ Reimbursements ============

@payroll_bp.route("/reimbursements", methods=["GET", "POST"])
@login_required
def reimbursements_view():
    tenant = current_tenant()
    user = current_user() or {}
    if request.method == "POST":
        if not user.get("employee_id"):
            flash("No employee record linked", "bad")
            return redirect(url_for("payroll.reimbursements_view"))
        reimbursements.submit(
            tenant, user["employee_id"],
            category=request.form["category"],
            amount=float(request.form["amount"]),
            expense_date=request.form.get("expense_date", ""),
            description=request.form.get("description", ""),
            actor_id=user["id"],
        )
        flash("Reimbursement submitted", "ok")
        return redirect(url_for("payroll.reimbursements_view"))
    role = user.get("role")
    is_admin = role in ("hr_admin", "hr_manager", "super_admin")
    rows = reimbursements.list_requests(
        tenant, status=request.args.get("status", "all"),
        employee_id=None if is_admin else user.get("employee_id"),
    )
    return render_template("payroll/reimbursements.html", rows=rows, is_admin=is_admin)


@payroll_bp.route("/reimbursements/<rid>/decide", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def reimbursement_decide(rid: str):
    user = current_user() or {}
    approve = request.form.get("decision") == "approve"
    reimbursements.decide(current_tenant(), rid, approve=approve, approver_id=user["id"])
    flash(f"Reimbursement {'approved' if approve else 'rejected'}", "ok")
    return redirect(url_for("payroll.reimbursements_view"))


# ============ Year-end ============

@payroll_bp.route("/yearend/<eid>")
@login_required
def yearend_view(eid: str):
    tenant = current_tenant()
    user = current_user() or {}
    if user.get("role") not in ("hr_admin", "hr_manager", "super_admin"):
        if user.get("employee_id") != eid:
            abort(403)
    emp = employee_master.get_employee(tenant, eid)
    if not emp:
        abort(404)
    fy = int(request.args.get("fy", date.today().year - (0 if date.today().month >= 4 else 1)))
    agg = yearend.aggregate_fy(tenant, eid, fy)
    compare = yearend.compute_regime_comparison(agg["gross_salary"])
    return render_template(
        "payroll/yearend.html", employee=emp, fy=fy, agg=agg, compare=compare,
    )


@payroll_bp.route("/yearend/<eid>/generate", methods=["POST"])
@login_required
@role_required("hr_admin")
def yearend_generate(eid: str):
    tenant = current_tenant()
    fy = int(request.form["fy"])
    chapter_via = float(request.form.get("chapter_via") or 0)
    regime = request.form.get("regime", "new")
    yearend.generate_form16(
        tenant, eid, fy, chapter_via=chapter_via, regime=regime,
        actor_id=(current_user() or {}).get("id"),
    )
    flash("Form 16 record generated", "ok")
    return redirect(url_for("payroll.yearend_view", eid=eid, fy=fy))


# ============ Locations ============

@payroll_bp.route("/locations", methods=["GET", "POST"])
@login_required
@role_required("hr_admin")
def locations_view():
    tenant = current_tenant()
    if request.method == "POST":
        import json
        pt_raw = request.form.get("pt_slabs", "[]")
        try:
            slabs = json.loads(pt_raw)
        except json.JSONDecodeError:
            slabs = []
        structures.upsert_location(tenant, {
            "state": request.form["state"],
            "city": request.form["city"],
            "is_metro": request.form.get("is_metro") == "on",
            "hra_basic_pct": float(request.form.get("hra_basic_pct") or 40.0),
            "pt_slabs": slabs,
            "lwf_employee_monthly": float(request.form.get("lwf_employee_monthly") or 0),
            "lwf_employer_monthly": float(request.form.get("lwf_employer_monthly") or 0),
        })
        flash("Location saved", "ok")
        return redirect(url_for("payroll.locations_view"))
    return render_template("payroll/locations.html",
                           locations=structures.list_locations(tenant))
