"""Year-end forms: Form 16 Part B computation + storage.

Aggregates all payslips for an employee in a fiscal year and computes the
annual IT picture under both regimes for comparison.
"""
from __future__ import annotations

from .. import db as recruitment_db
from .. import payroll as engine
from ..shared.utils import new_id, now_iso
from . import payslips as payslip_store


def aggregate_fy(tenant_id: str, employee_id: str, fy_year: int) -> dict:
    """Sum monthly payslip data across the Indian fiscal year (Apr–Mar)."""
    months = [(fy_year, m) for m in range(4, 13)] + [(fy_year + 1, m) for m in range(1, 4)]
    all_slips = payslip_store.list_for_employee(tenant_id, employee_id)
    in_fy = [s for s in all_slips if (s["year"], s["month"]) in months]
    gross = sum(s["gross_earnings"] for s in in_fy)
    pf = sum((s.get("deductions") or {}).get("epf", 0) for s in in_fy)
    pt = sum((s.get("deductions") or {}).get("professional_tax", 0) for s in in_fy)
    tds = sum((s.get("deductions") or {}).get("tds", 0) for s in in_fy)
    return {
        "fy_year": fy_year,
        "months_paid": len(in_fy),
        "gross_salary": round(gross, 2),
        "epf_employee": round(pf, 2),
        "professional_tax": round(pt, 2),
        "tds_deducted": round(tds, 2),
    }


def compute_regime_comparison(
    annual_gross: float,
    annual_exemptions_old: float = 0,
) -> dict:
    """Return tax under both regimes so an employee can choose."""
    new_tax = engine.compute_tds_annual(
        max(0, annual_gross - engine.STD_DEDUCTION_NEW), regime="new",
    )
    old_tax = engine.compute_tds_annual(
        max(0, annual_gross - engine.STD_DEDUCTION_OLD - annual_exemptions_old), regime="old",
    )
    return {
        "new_regime": {
            "taxable_income": max(0, annual_gross - engine.STD_DEDUCTION_NEW),
            "tax_with_cess": new_tax,
        },
        "old_regime": {
            "taxable_income": max(0, annual_gross - engine.STD_DEDUCTION_OLD - annual_exemptions_old),
            "tax_with_cess": old_tax,
        },
        "recommended": "new" if new_tax <= old_tax else "old",
        "savings": round(abs(new_tax - old_tax), 2),
    }


def generate_form16(
    tenant_id: str, employee_id: str, fy_year: int, *,
    chapter_via: float = 0, regime: str = "new",
    actor_id: str | None = None,
) -> dict:
    agg = aggregate_fy(tenant_id, employee_id, fy_year)
    std_ded = engine.STD_DEDUCTION_NEW if regime == "new" else engine.STD_DEDUCTION_OLD
    taxable = max(0, agg["gross_salary"] - std_ded - chapter_via)
    tax = engine.compute_tds_annual(taxable, regime=regime)

    fid = new_id("f16")
    with recruitment_db.connect() as c:
        existing = c.execute(
            "SELECT id FROM form16_records WHERE tenant_id = ? AND employee_id = ? AND fy_year = ?",
            (tenant_id, employee_id, fy_year),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE form16_records SET gross_salary = ?, exemptions = ?, standard_deduction = ?,
                       chapter_via = ?, taxable_income = ?, total_tax = ?, tds_deducted = ?,
                       regime = ?, generated_at = ?
                   WHERE id = ?""",
                (agg["gross_salary"], 0, std_ded, chapter_via, taxable, tax,
                 agg["tds_deducted"], regime, now_iso(), existing["id"]),
            )
            fid = existing["id"]
        else:
            c.execute(
                """INSERT INTO form16_records
                    (id, tenant_id, employee_id, fy_year, gross_salary, exemptions,
                     standard_deduction, chapter_via, taxable_income, total_tax,
                     tds_deducted, regime, generated_at, created_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, tenant_id, employee_id, fy_year, agg["gross_salary"],
                 std_ded, chapter_via, taxable, tax, agg["tds_deducted"], regime,
                 now_iso(), now_iso()),
            )
    with recruitment_db.connect() as c:
        return dict(c.execute("SELECT * FROM form16_records WHERE id = ?", (fid,)).fetchone())
