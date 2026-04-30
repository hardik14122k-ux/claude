"""Authentication and RBAC for HRMS.

Uses Flask session (server-side). Passwords hashed with werkzeug pbkdf2
(no extra dependency). RBAC roles: super_admin, hr_admin, hr_manager,
recruiter, employee, read_only.

Usage:
    from server.shared.auth import login_required, role_required, current_user

    @app.route("/hr/employees")
    @login_required
    @role_required("hr_admin", "hr_manager")
    def employee_list(): ...
"""
from __future__ import annotations

import functools
import json
from typing import Callable

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import DEFAULT_TENANT

# Role hierarchy: higher index = more privileged
ROLES = ["read_only", "employee", "recruiter", "hr_manager", "hr_admin", "super_admin"]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "read_only":   {"dashboard.view", "report.view"},
    "employee":    {"dashboard.view", "report.view", "leave.request", "payslip.view", "ess.view"},
    "recruiter":   {"dashboard.view", "vacancy.all", "candidate.all", "interview.all",
                    "report.view", "pipeline.view"},
    "hr_manager":  {"dashboard.view", "vacancy.all", "candidate.all", "interview.all",
                    "report.view", "pipeline.view", "leave.approve", "attendance.edit",
                    "employee.view", "payslip.view"},
    "hr_admin":    {"*"},  # all permissions except super_admin ops
    "super_admin": {"*"},
}


def hash_password(plain: str) -> str:
    return generate_password_hash(plain, method="pbkdf2:sha256", salt_length=16)


def verify_password(plain: str, hashed: str) -> bool:
    return check_password_hash(hashed, plain)


def current_user() -> dict | None:
    return g.get("current_user")


def current_tenant() -> str:
    return g.get("tenant_id", DEFAULT_TENANT)


def has_permission(permission: str) -> bool:
    user = current_user()
    if not user:
        return False
    role = user.get("role", "read_only")
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


def load_user_from_session() -> None:
    """Call in before_request to populate g.current_user and g.tenant_id."""
    uid = session.get("user_id")
    if uid:
        from ..hrms import schema as hrms_db
        user = hrms_db.get_user_by_id(uid)
        g.current_user = user
        g.tenant_id = user["tenant_id"] if user else DEFAULT_TENANT
    else:
        g.current_user = None
        g.tenant_id = DEFAULT_TENANT


def login_required(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.path))
            if user.get("role") not in roles and user.get("role") != "super_admin":
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def permission_required(perm: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_permission(perm):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
