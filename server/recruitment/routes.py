"""Recruitment extensions blueprint: requisitions, offers, onboarding handoff.

Lives alongside the existing recruitment routes in app.py — does not
replace them. Original /vacancies, /candidates, /pipeline routes work
exactly as before.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db as recruitment_db
from ..hrms import schema as hrms_db
from ..shared.auth import current_tenant, current_user, login_required, role_required
from . import offers, onboarding, requisitions


recruitment_ext_bp = Blueprint("recruitment_ext", __name__, url_prefix="/recruit")


# ============ Requisitions ============

@recruitment_ext_bp.route("/requisitions")
@login_required
def requisitions_list():
    tenant = current_tenant()
    return render_template(
        "recruit/requisitions.html",
        rows=requisitions.list_requisitions(tenant, request.args.get("status", "all")),
    )


@recruitment_ext_bp.route("/requisitions/new", methods=["GET", "POST"])
@login_required
def requisition_new():
    tenant = current_tenant()
    if request.method == "POST":
        requisitions.create(tenant, {
            "title": request.form["title"],
            "department_id": request.form.get("department_id"),
            "openings": request.form.get("openings", 1),
            "employment_type": request.form.get("employment_type", "permanent"),
            "target_ctc_min": request.form.get("target_ctc_min"),
            "target_ctc_max": request.form.get("target_ctc_max"),
            "justification": request.form.get("justification", ""),
        }, actor_id=(current_user() or {}).get("id"))
        flash("Requisition submitted", "ok")
        return redirect(url_for("recruitment_ext.requisitions_list"))
    return render_template(
        "recruit/requisition_form.html",
        departments=hrms_db.list_departments(tenant),
    )


@recruitment_ext_bp.route("/requisitions/<rid>/decide", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def requisition_decide(rid: str):
    user = current_user() or {}
    approve = request.form.get("decision") == "approve"
    requisitions.decide(current_tenant(), rid, approve=approve, approver_id=user["id"])
    flash(f"Requisition {'approved' if approve else 'rejected'}", "ok")
    return redirect(url_for("recruitment_ext.requisitions_list"))


# ============ Offers ============

@recruitment_ext_bp.route("/offers")
@login_required
def offers_list():
    tenant = current_tenant()
    rows = offers.list_offers(tenant, request.args.get("status", "all"))
    candidates = {c["id"]: c for c in recruitment_db.list_candidates()}
    return render_template("recruit/offers.html", rows=rows, candidates=candidates)


@recruitment_ext_bp.route("/offers/new", methods=["GET", "POST"])
@login_required
@role_required("hr_admin", "hr_manager", "recruiter")
def offer_new():
    tenant = current_tenant()
    if request.method == "POST":
        offers.create(tenant, {
            "candidate_id": request.form["candidate_id"],
            "vacancy_id": request.form.get("vacancy_id"),
            "offered_ctc": float(request.form["offered_ctc"]),
            "offered_position": request.form.get("offered_position", ""),
            "join_date": request.form.get("join_date", ""),
            "expiry_date": request.form.get("expiry_date", ""),
            "notes": request.form.get("notes", ""),
        }, actor_id=(current_user() or {}).get("id"))
        flash("Offer drafted", "ok")
        return redirect(url_for("recruitment_ext.offers_list"))
    return render_template(
        "recruit/offer_form.html",
        candidates=recruitment_db.list_candidates(),
        vacancies=recruitment_db.list_vacancies(),
    )


@recruitment_ext_bp.route("/offers/<oid>/send", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager", "recruiter")
def offer_send(oid: str):
    if offers.send(current_tenant(), oid, actor_id=(current_user() or {}).get("id")):
        flash("Offer sent", "ok")
    else:
        flash("Offer cannot be sent in its current state", "bad")
    return redirect(url_for("recruitment_ext.offers_list"))


@recruitment_ext_bp.route("/offers/<oid>/decide", methods=["POST"])
@login_required
def offer_decide(oid: str):
    accept = request.form.get("decision") == "accept"
    offers.decide(current_tenant(), oid, accept=accept,
                  actor_id=(current_user() or {}).get("id"))
    flash(f"Offer {'accepted' if accept else 'declined'}", "ok")
    return redirect(url_for("recruitment_ext.offers_list"))


# ============ Onboarding ============

@recruitment_ext_bp.route("/onboard/<candidate_id>", methods=["POST"])
@login_required
@role_required("hr_admin", "hr_manager")
def onboard(candidate_id: str):
    emp = onboarding.handoff_to_employee(
        current_tenant(), candidate_id,
        actor_id=(current_user() or {}).get("id"),
    )
    if not emp:
        abort(404)
    flash(f"Candidate onboarded as employee {emp['employee_code']}", "ok")
    return redirect(url_for("hrms.employee_detail", eid=emp["id"]))
