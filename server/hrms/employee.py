"""Employee master CRUD.

Multi-tenant. Always filters by tenant_id. Stores employee_code uniquely
within a tenant. Links back to recruitment.candidates via candidate_id when
an employee was onboarded from a candidate.
"""
from __future__ import annotations

from typing import Any

from .. import db as recruitment_db
from ..shared.utils import new_id, now_iso
from ..shared import audit


def list_employees(
    tenant_id: str,
    *,
    status: str | None = None,
    department_id: str | None = None,
    q: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM employees WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if status and status != "all":
        sql += " AND status = ?"; params.append(status)
    if department_id and department_id != "all":
        sql += " AND department_id = ?"; params.append(department_id)
    if q:
        sql += (" AND (LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? "
                "OR LOWER(email) LIKE ? OR LOWER(employee_code) LIKE ?)")
        like = f"%{q.lower()}%"
        params.extend([like, like, like, like])
    sql += " ORDER BY first_name"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def get_employee(tenant_id: str, eid: str) -> dict | None:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM employees WHERE tenant_id = ? AND id = ?",
            (tenant_id, eid),
        ).fetchone()
    return dict(row) if row else None


def get_by_code(tenant_id: str, code: str) -> dict | None:
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM employees WHERE tenant_id = ? AND employee_code = ?",
            (tenant_id, code),
        ).fetchone()
    return dict(row) if row else None


def next_employee_code(tenant_id: str, prefix: str = "EMP") -> str:
    """Generate the next sequential employee code within a tenant."""
    with recruitment_db.connect() as c:
        rows = c.execute(
            "SELECT employee_code FROM employees WHERE tenant_id = ? AND employee_code LIKE ?",
            (tenant_id, f"{prefix}%"),
        ).fetchall()
    nums = []
    for r in rows:
        suffix = r["employee_code"][len(prefix):]
        if suffix.isdigit():
            nums.append(int(suffix))
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}{nxt:04d}"


_FIELDS = [
    "employee_code", "first_name", "last_name", "email", "personal_email", "phone",
    "dob", "gender", "blood_group", "marital_status", "pan", "aadhaar_last4",
    "uan", "pf_number", "esi_number", "bank_account_no", "bank_ifsc", "bank_name",
    "address_line", "city", "state", "pincode", "country",
    "emergency_contact", "emergency_phone",
    "department_id", "position_id", "manager_id", "work_location",
    "employment_type", "status", "date_joined", "date_confirmed", "date_exit",
    "probation_months", "notice_period_days", "candidate_id",
]


def create_employee(tenant_id: str, data: dict, *, actor_id: str | None = None) -> dict:
    eid = new_id("emp")
    code = (data.get("employee_code") or "").strip() or next_employee_code(tenant_id)
    ts = now_iso()
    payload = {
        "id": eid,
        "tenant_id": tenant_id,
        "employee_code": code,
        "first_name": (data.get("first_name") or "").strip() or "Unnamed",
        "last_name": data.get("last_name") or "",
        "email": data.get("email") or "",
        "personal_email": data.get("personal_email") or "",
        "phone": data.get("phone") or "",
        "dob": data.get("dob") or "",
        "gender": data.get("gender") or "",
        "blood_group": data.get("blood_group") or "",
        "marital_status": data.get("marital_status") or "",
        "pan": data.get("pan") or "",
        "aadhaar_last4": (data.get("aadhaar_last4") or "")[-4:],
        "uan": data.get("uan") or "",
        "pf_number": data.get("pf_number") or "",
        "esi_number": data.get("esi_number") or "",
        "bank_account_no": data.get("bank_account_no") or "",
        "bank_ifsc": data.get("bank_ifsc") or "",
        "bank_name": data.get("bank_name") or "",
        "address_line": data.get("address_line") or "",
        "city": data.get("city") or "",
        "state": data.get("state") or "",
        "pincode": data.get("pincode") or "",
        "country": data.get("country") or "India",
        "emergency_contact": data.get("emergency_contact") or "",
        "emergency_phone": data.get("emergency_phone") or "",
        "department_id": data.get("department_id") or None,
        "position_id": data.get("position_id") or None,
        "manager_id": data.get("manager_id") or None,
        "work_location": data.get("work_location") or "",
        "employment_type": data.get("employment_type") or "permanent",
        "status": data.get("status") or "active",
        "date_joined": data.get("date_joined") or "",
        "date_confirmed": data.get("date_confirmed") or "",
        "date_exit": data.get("date_exit") or "",
        "probation_months": int(data.get("probation_months") or 6),
        "notice_period_days": int(data.get("notice_period_days") or 60),
        "candidate_id": data.get("candidate_id") or None,
        "created_at": ts,
        "updated_at": ts,
    }
    cols = ", ".join(payload.keys())
    placeholders = ", ".join("?" for _ in payload)
    with recruitment_db.connect() as c:
        c.execute(f"INSERT INTO employees ({cols}) VALUES ({placeholders})", list(payload.values()))
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="employee", entity_id=eid,
                  message=f'Employee {payload["first_name"]} {payload["last_name"]} created')
    return get_employee(tenant_id, eid)


def update_employee(
    tenant_id: str, eid: str, data: dict, *, actor_id: str | None = None,
) -> dict | None:
    existing = get_employee(tenant_id, eid)
    if not existing:
        return None
    diff: dict[str, Any] = {}
    sets, params = [], []
    for f in _FIELDS:
        if f in data and data[f] != existing.get(f):
            sets.append(f"{f} = ?")
            val = data[f]
            if f == "aadhaar_last4" and isinstance(val, str):
                val = val[-4:]
            params.append(val)
            diff[f] = {"from": existing.get(f), "to": val}
    if not sets:
        return existing
    sets.append("updated_at = ?")
    params.extend([now_iso(), tenant_id, eid])
    with recruitment_db.connect() as c:
        c.execute(
            f"UPDATE employees SET {', '.join(sets)} WHERE tenant_id = ? AND id = ?",
            params,
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="update",
                  entity_type="employee", entity_id=eid, diff=diff,
                  message=f'Updated {len(diff)} field(s)')
    return get_employee(tenant_id, eid)


def deactivate_employee(
    tenant_id: str, eid: str, *, exit_date: str = "", actor_id: str | None = None,
) -> bool:
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE employees SET status = 'resigned', date_exit = ?, updated_at = ? "
            "WHERE tenant_id = ? AND id = ?",
            (exit_date, now_iso(), tenant_id, eid),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="deactivate",
                  entity_type="employee", entity_id=eid, message="Employee resigned")
    return True


def from_candidate(tenant_id: str, candidate: dict, *, actor_id: str | None = None,
                   extra: dict | None = None) -> dict:
    """Onboarding handoff: create an employee record from a recruitment candidate."""
    name = (candidate.get("name") or "").strip().split(" ", 1)
    first = name[0] if name else "Unnamed"
    last = name[1] if len(name) > 1 else ""
    payload = {
        "first_name": first,
        "last_name": last,
        "email": candidate.get("email") or "",
        "phone": candidate.get("phone") or "",
        "candidate_id": candidate.get("id"),
        "status": "active",
        "date_joined": now_iso()[:10],
    }
    if extra:
        payload.update(extra)
    return create_employee(tenant_id, payload, actor_id=actor_id)


def org_tree(tenant_id: str) -> list[dict]:
    """Return reports-to tree rooted at employees with no manager."""
    employees = list_employees(tenant_id)
    by_manager: dict[str | None, list[dict]] = {}
    for e in employees:
        by_manager.setdefault(e.get("manager_id"), []).append(e)

    def build(emp: dict) -> dict:
        return {
            "id": emp["id"],
            "name": f"{emp['first_name']} {emp.get('last_name','')}".strip(),
            "title": emp.get("work_location", ""),
            "reports": [build(c) for c in by_manager.get(emp["id"], [])],
        }

    roots = by_manager.get(None, [])
    return [build(r) for r in roots]
