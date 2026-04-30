"""HRMS blueprint: employees, departments, attendance, leave, ESS."""
from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for

from .. import db as recruitment_db
from ..shared.auth import (
    current_tenant, current_user, login_required, role_required,
)
from ..shared.utils import fiscal_year, now_iso
from . import attendance, documents, employee as employee_master, leave, schema as hrms_db


hrms_bp = Blueprint("hrms", __name__, url_prefix="/hr")


# ============ Employees ============

@hrms_bp.route("/employees")
@login_required
def employees_list():
    tenant = current_tenant()
    q = (request.args.get("q") or "").strip() or None
    status = request.args.get("status", "active")
    dept = request.args.get("department", "all")
    employees = employee_master.list_employees(tenant, q=q, status=status, department_id=dept)
    departments = hrms_db.list_departments(tenant)
    return render_template(
        "hrms/employees.html",
        employees=employees, departments=departments,
        q=q or "", status=status, dept=dept,
    )


@hrms_bp.route("/employees/new", methods=["GET", "POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def employee_new():
    tenant = current_tenant()
    if request.method == "POST":
        emp = employee_master.create_employee(tenant, _form_to_employee_data(request.form),
                                               actor_id=(current_user() or {}).get("id"))
        flash(f"Employee {emp['employee_code']} created", "ok")
        return redirect(url_for("hrms.employee_detail", eid=emp["id"]))
    return render_template(
        "hrms/employee_form.html", employee=None,
        departments=hrms_db.list_departments(tenant),
        positions=hrms_db.list_positions(tenant),
        managers=employee_master.list_employees(tenant, status="active"),
    )


@hrms_bp.route("/employees/<eid>")
@login_required
def employee_detail(eid: str):
    tenant = current_tenant()
    emp = employee_master.get_employee(tenant, eid)
    if not emp:
        abort(404)
    docs = documents.list_for_owner(tenant, "employee", eid)
    balances = leave.list_balances(tenant, eid)
    return render_template(
        "hrms/employee_detail.html",
        employee=emp, documents=docs, balances=balances,
        audit=hrms_db.list_audit(tenant, entity_type="employee", entity_id=eid, limit=20),
    )


@hrms_bp.route("/employees/<eid>/edit", methods=["GET", "POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def employee_edit(eid: str):
    tenant = current_tenant()
    emp = employee_master.get_employee(tenant, eid)
    if not emp:
        abort(404)
    if request.method == "POST":
        employee_master.update_employee(tenant, eid, _form_to_employee_data(request.form),
                                         actor_id=(current_user() or {}).get("id"))
        flash("Employee updated", "ok")
        return redirect(url_for("hrms.employee_detail", eid=eid))
    return render_template(
        "hrms/employee_form.html", employee=emp,
        departments=hrms_db.list_departments(tenant),
        positions=hrms_db.list_positions(tenant),
        managers=employee_master.list_employees(tenant, status="active"),
    )


def _form_to_employee_data(form) -> dict:
    return {
        "employee_code": form.get("employee_code"),
        "first_name": form.get("first_name"),
        "last_name": form.get("last_name"),
        "email": form.get("email"),
        "personal_email": form.get("personal_email"),
        "phone": form.get("phone"),
        "dob": form.get("dob"),
        "gender": form.get("gender"),
        "marital_status": form.get("marital_status"),
        "pan": form.get("pan"),
        "aadhaar_last4": form.get("aadhaar_last4"),
        "uan": form.get("uan"),
        "pf_number": form.get("pf_number"),
        "bank_account_no": form.get("bank_account_no"),
        "bank_ifsc": form.get("bank_ifsc"),
        "bank_name": form.get("bank_name"),
        "address_line": form.get("address_line"),
        "city": form.get("city"),
        "state": form.get("state"),
        "pincode": form.get("pincode"),
        "country": form.get("country") or "India",
        "department_id": form.get("department_id") or None,
        "position_id": form.get("position_id") or None,
        "manager_id": form.get("manager_id") or None,
        "work_location": form.get("work_location"),
        "employment_type": form.get("employment_type") or "permanent",
        "status": form.get("status") or "active",
        "date_joined": form.get("date_joined"),
        "probation_months": int(form.get("probation_months") or 6),
        "notice_period_days": int(form.get("notice_period_days") or 60),
    }


# ============ Departments / Positions ============

@hrms_bp.route("/org", methods=["GET", "POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def org():
    tenant = current_tenant()
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "department":
            hrms_db.create_department(tenant, {
                "name": request.form.get("name", ""),
                "code": request.form.get("code", ""),
            })
            flash("Department added", "ok")
        elif kind == "position":
            hrms_db.create_position(tenant, {
                "title": request.form.get("title", ""),
                "grade": request.form.get("grade", ""),
                "department_id": request.form.get("department_id"),
            })
            flash("Position added", "ok")
        return redirect(url_for("hrms.org"))
    return render_template(
        "hrms/org.html",
        departments=hrms_db.list_departments(tenant),
        positions=hrms_db.list_positions(tenant),
        org_tree=employee_master.org_tree(tenant),
    )


# ============ Attendance ============

@hrms_bp.route("/attendance")
@login_required
def attendance_view():
    tenant = current_tenant()
    today = date.today()
    year = int(request.args.get("year") or today.year)
    month = int(request.args.get("month") or today.month)
    employees = employee_master.list_employees(tenant, status="active")
    summaries = {e["id"]: attendance.monthly_summary(tenant, e["id"], year, month) for e in employees}
    return render_template(
        "hrms/attendance.html",
        employees=employees, summaries=summaries, year=year, month=month,
    )


@hrms_bp.route("/attendance/check-in", methods=["POST"])
@login_required
def attendance_check_in():
    user = current_user() or {}
    if not user.get("employee_id"):
        flash("No employee record linked to this user", "bad")
        return redirect(url_for("hrms.attendance_view"))
    attendance.check_in(current_tenant(), user["employee_id"])
    flash("Checked in", "ok")
    return redirect(url_for("hrms.attendance_view"))


@hrms_bp.route("/attendance/check-out", methods=["POST"])
@login_required
def attendance_check_out():
    user = current_user() or {}
    if not user.get("employee_id"):
        flash("No employee record linked to this user", "bad")
        return redirect(url_for("hrms.attendance_view"))
    attendance.check_out(current_tenant(), user["employee_id"])
    flash("Checked out", "ok")
    return redirect(url_for("hrms.attendance_view"))


@hrms_bp.route("/attendance/mark", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def attendance_mark():
    tenant = current_tenant()
    attendance.upsert(
        tenant,
        request.form["employee_id"],
        request.form["date"],
        status=request.form.get("status", "present"),
        notes=request.form.get("notes", ""),
        actor_id=(current_user() or {}).get("id"),
    )
    flash("Attendance recorded", "ok")
    return redirect(url_for("hrms.attendance_view"))


# ============ Leave ============

@hrms_bp.route("/leave")
@login_required
def leave_view():
    tenant = current_tenant()
    user = current_user() or {}
    role = user.get("role")
    is_admin = role in ("hr_admin", "hr_manager", "super_admin")
    employee_id = user.get("employee_id") if not is_admin else (request.args.get("employee_id"))
    requests = leave.list_requests(
        tenant, employee_id=employee_id,
        status=request.args.get("status", "all"),
    )
    leave_types = hrms_db.list_leave_types(tenant)
    balances = []
    if user.get("employee_id"):
        balances = leave.list_balances(tenant, user["employee_id"])
    return render_template(
        "hrms/leave.html",
        requests=requests, leave_types=leave_types, balances=balances,
        is_admin=is_admin,
    )


@hrms_bp.route("/leave/request", methods=["POST"])
@login_required
def leave_request():
    user = current_user() or {}
    if not user.get("employee_id"):
        flash("No employee record linked", "bad")
        return redirect(url_for("hrms.leave_view"))
    try:
        leave.request_leave(
            current_tenant(), user["employee_id"], request.form["leave_type_id"],
            request.form["start"], request.form["end"], request.form.get("reason", ""),
            actor_id=user["id"],
        )
        flash("Leave request submitted", "ok")
    except ValueError as exc:
        flash(str(exc), "bad")
    return redirect(url_for("hrms.leave_view"))


@hrms_bp.route("/leave/<rid>/decide", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def leave_decide(rid: str):
    user = current_user() or {}
    approve = request.form.get("decision") == "approve"
    leave.decide_request(
        current_tenant(), rid, approve=approve, approver_id=user["id"],
        note=request.form.get("note", ""),
    )
    flash(f"Leave {'approved' if approve else 'rejected'}", "ok")
    return redirect(url_for("hrms.leave_view"))


@hrms_bp.route("/leave-types/seed", methods=["POST"])
@login_required
@role_required("hr_admin")
def seed_leave_types():
    tenant = current_tenant()
    defaults = [
        {"code": "CL", "name": "Casual Leave", "annual_quota": 12, "accrual": "monthly", "is_paid": True},
        {"code": "SL", "name": "Sick Leave", "annual_quota": 12, "accrual": "monthly", "is_paid": True, "requires_proof": True},
        {"code": "PL", "name": "Privilege Leave", "annual_quota": 18, "accrual": "monthly", "is_paid": True, "carry_forward": 30, "encashable": True},
        {"code": "ML", "name": "Maternity Leave", "annual_quota": 182, "accrual": "none", "is_paid": True, "requires_proof": True},
        {"code": "PT", "name": "Paternity Leave", "annual_quota": 15, "accrual": "none", "is_paid": True},
        {"code": "LWP", "name": "Leave Without Pay", "annual_quota": 0, "accrual": "none", "is_paid": False},
    ]
    for d in defaults:
        hrms_db.upsert_leave_type(tenant, d)
    flash(f"{len(defaults)} leave types seeded", "ok")
    return redirect(url_for("hrms.leave_view"))


# ============ Documents ============

@hrms_bp.route("/employees/<eid>/documents/upload", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def upload_document(eid: str):
    tenant = current_tenant()
    up = request.files.get("file")
    if not up or not up.filename:
        flash("Pick a file", "bad")
        return redirect(url_for("hrms.employee_detail", eid=eid))
    documents.upload(
        tenant, owner_type="employee", owner_id=eid,
        stream=up.stream, file_name=up.filename,
        category=request.form.get("category", ""),
        title=request.form.get("title", ""),
        is_confidential=request.form.get("confidential") == "on",
        uploaded_by=(current_user() or {}).get("id"),
    )
    flash("Document uploaded", "ok")
    return redirect(url_for("hrms.employee_detail", eid=eid))


@hrms_bp.route("/documents/<doc_id>/download")
@login_required
def download_document(doc_id: str):
    tenant = current_tenant()
    doc = documents.get(tenant, doc_id)
    if not doc:
        abort(404)
    return send_file(doc["storage_path"], as_attachment=True,
                     download_name=doc["file_name"], mimetype=doc.get("content_type"))


# ============ ESS (employee self service) ============

@hrms_bp.route("/me")
@login_required
def me():
    user = current_user() or {}
    tenant = current_tenant()
    if not user.get("employee_id"):
        return render_template("hrms/me.html", employee=None)
    emp = employee_master.get_employee(tenant, user["employee_id"])
    balances = leave.list_balances(tenant, user["employee_id"])
    from ..payroll_ext import payslips as payslip_store
    slips = payslip_store.list_for_employee(tenant, user["employee_id"])
    return render_template(
        "hrms/me.html",
        employee=emp, balances=balances, payslips=slips,
        recent_attendance=attendance.list_for_employee(
            tenant, user["employee_id"], date.today().year, date.today().month,
        ),
    )


# ============ Audit log ============

@hrms_bp.route("/audit")
@login_required
@role_required("hr_admin", "super_admin")
def audit_log():
    tenant = current_tenant()
    rows = hrms_db.list_audit(tenant, limit=200)
    return render_template("hrms/audit.html", rows=rows)
