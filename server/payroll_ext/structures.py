"""Salary structure persistence.

Wraps server.payroll.build_structure (pure Indian-payroll math) and stores
the resulting annualised components against an employee with effective dates.
"""
from __future__ import annotations

from typing import Any

from .. import db as recruitment_db
from .. import payroll as engine
from ..shared import audit
from ..shared.utils import new_id, now_iso


def list_for_employee(tenant_id: str, employee_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(
            """SELECT * FROM salary_structures WHERE tenant_id = ? AND employee_id = ?
               ORDER BY effective_from DESC""",
            (tenant_id, employee_id),
        ).fetchall()]


def current(tenant_id: str, employee_id: str, on_date: str | None = None) -> dict | None:
    on_date = on_date or now_iso()[:10]
    with recruitment_db.connect() as c:
        row = c.execute(
            """SELECT * FROM salary_structures
               WHERE tenant_id = ? AND employee_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to = '' OR effective_to >= ?)
               ORDER BY effective_from DESC LIMIT 1""",
            (tenant_id, employee_id, on_date, on_date),
        ).fetchone()
    return dict(row) if row else None


def upsert(
    tenant_id: str,
    employee_id: str,
    *,
    ctc_annual: float,
    location_id: str | None = None,
    effective_from: str | None = None,
    basic_pct: float = 40.0,
    conveyance_monthly: float = 0.0,
    medical_monthly: float = 0.0,
    lta_annual: float = 0.0,
    bonus_annual: float = 0.0,
    actor_id: str | None = None,
) -> dict:
    """Compute the full structure via the payroll engine, close any open prior
    structure, and insert the new one."""
    location = _location_to_engine(tenant_id, location_id)
    structure = engine.build_structure(
        ctc_annual=ctc_annual,
        location=location,
        basic_pct=basic_pct,
        conveyance_monthly=conveyance_monthly,
        medical_monthly=medical_monthly,
        lta_annual=lta_annual,
        bonus_annual=bonus_annual,
    )
    sid = new_id("sal")
    eff_from = effective_from or now_iso()[:10]
    with recruitment_db.connect() as c:
        # Close out any existing open structure with effective_to = day before.
        c.execute(
            """UPDATE salary_structures
               SET effective_to = date(?, '-1 day')
               WHERE tenant_id = ? AND employee_id = ?
                 AND (effective_to IS NULL OR effective_to = '')""",
            (eff_from, tenant_id, employee_id),
        )
        c.execute(
            """INSERT INTO salary_structures
                (id, tenant_id, employee_id, effective_from, effective_to, ctc_annual,
                 basic_annual, hra_annual, special_allowance_annual, conveyance_annual,
                 medical_annual, lta_annual, bonus_annual, employer_pf_annual,
                 employer_eps_annual, employer_esi_annual, gratuity_annual, location_id, created_at)
               VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, tenant_id, employee_id, eff_from, structure.ctc_annual,
             structure.basic_annual, structure.hra_annual, structure.special_allowance_annual,
             structure.conveyance_annual, structure.medical_annual, structure.lta_annual,
             structure.bonus_annual, structure.employer_pf_annual, structure.employer_eps_annual,
             structure.employer_esi_annual, structure.gratuity_annual, location_id, now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="salary_structure", entity_id=sid,
                  message=f"CTC ₹{ctc_annual:,.0f} effective {eff_from}")
    with recruitment_db.connect() as c:
        return dict(c.execute("SELECT * FROM salary_structures WHERE id = ?", (sid,)).fetchone())


def to_engine_structure(row: dict) -> engine.Structure:
    """Hydrate a DB row back into the payroll-engine Structure dataclass."""
    return engine.Structure(
        ctc_annual=row["ctc_annual"],
        basic_annual=row["basic_annual"],
        hra_annual=row["hra_annual"],
        special_allowance_annual=row["special_allowance_annual"],
        conveyance_annual=row["conveyance_annual"],
        medical_annual=row["medical_annual"],
        lta_annual=row["lta_annual"],
        bonus_annual=row["bonus_annual"],
        employer_pf_annual=row["employer_pf_annual"],
        employer_eps_annual=row["employer_eps_annual"],
        employer_esi_annual=row["employer_esi_annual"],
        gratuity_annual=row["gratuity_annual"],
    )


def _location_to_engine(tenant_id: str, location_id: str | None) -> engine.Location:
    if not location_id:
        return engine.Location(state="-", city="-", is_metro=False)
    with recruitment_db.connect() as c:
        row = c.execute(
            "SELECT * FROM payroll_locations WHERE tenant_id = ? AND id = ?",
            (tenant_id, location_id),
        ).fetchone()
    if not row:
        return engine.Location(state="-", city="-", is_metro=False)
    import json
    return engine.Location(
        state=row["state"],
        city=row["city"],
        is_metro=bool(row["is_metro"]),
        hra_basic_pct=row["hra_basic_pct"],
        pt_slabs=json.loads(row["pt_slabs"] or "[]"),
        lwf_employee_monthly=row["lwf_employee_monthly"],
        lwf_employer_monthly=row["lwf_employer_monthly"],
        min_wage_unskilled=row["min_wage_unskilled"],
        min_wage_semi_skilled=row["min_wage_semi_skilled"],
        min_wage_skilled=row["min_wage_skilled"],
    )


# ---------- Locations ----------

def list_locations(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM payroll_locations WHERE tenant_id = ? ORDER BY state, city",
            (tenant_id,),
        ).fetchall()]


def upsert_location(tenant_id: str, data: dict) -> dict:
    import json
    with recruitment_db.connect() as c:
        existing = c.execute(
            "SELECT * FROM payroll_locations WHERE tenant_id = ? AND state = ? AND city = ?",
            (tenant_id, data["state"], data["city"]),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE payroll_locations SET is_metro = ?, hra_basic_pct = ?, pt_slabs = ?,
                       lwf_employee_monthly = ?, lwf_employer_monthly = ?,
                       min_wage_unskilled = ?, min_wage_semi_skilled = ?, min_wage_skilled = ?
                   WHERE id = ?""",
                (1 if data.get("is_metro") else 0, data.get("hra_basic_pct", 40.0),
                 json.dumps(data.get("pt_slabs") or []),
                 data.get("lwf_employee_monthly", 0), data.get("lwf_employer_monthly", 0),
                 data.get("min_wage_unskilled", 0), data.get("min_wage_semi_skilled", 0),
                 data.get("min_wage_skilled", 0), existing["id"]),
            )
            return dict(c.execute("SELECT * FROM payroll_locations WHERE id = ?", (existing["id"],)).fetchone())
        lid = new_id("loc")
        c.execute(
            """INSERT INTO payroll_locations
                (id, tenant_id, state, city, is_metro, hra_basic_pct, pt_slabs,
                 lwf_employee_monthly, lwf_employer_monthly,
                 min_wage_unskilled, min_wage_semi_skilled, min_wage_skilled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lid, tenant_id, data["state"], data["city"], 1 if data.get("is_metro") else 0,
             data.get("hra_basic_pct", 40.0), json.dumps(data.get("pt_slabs") or []),
             data.get("lwf_employee_monthly", 0), data.get("lwf_employer_monthly", 0),
             data.get("min_wage_unskilled", 0), data.get("min_wage_semi_skilled", 0),
             data.get("min_wage_skilled", 0)),
        )
        return dict(c.execute("SELECT * FROM payroll_locations WHERE id = ?", (lid,)).fetchone())
