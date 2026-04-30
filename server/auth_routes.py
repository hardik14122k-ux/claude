"""Auth blueprint: login, logout, signup-default-admin."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .config import DEFAULT_TENANT
from .hrms import schema as hrms_db
from .shared.auth import verify_password
from .shared import audit

from . import db as recruitment_db


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = hrms_db.get_user_by_email(DEFAULT_TENANT, email)
        if user and verify_password(password, user["password_hash"]):
            session.clear()
            session["user_id"] = user["id"]
            hrms_db.touch_login(user["id"])
            with recruitment_db.connect() as c:
                audit.log(c, actor_id=user["id"], tenant_id=user["tenant_id"],
                          action="login", entity_type="user", entity_id=user["id"],
                          message=f"Login {user['email']}", ip=request.remote_addr)
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        flash("Invalid credentials", "bad")
    return render_template("auth_login.html")


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("Signed out", "ok")
    return redirect(url_for("auth.login"))
