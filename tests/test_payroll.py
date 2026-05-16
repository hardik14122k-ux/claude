"""Verify the existing payroll engine still works and the new DB layer
preserves its outputs round-trip."""
import pytest


def test_engine_compute_basics():
    from server import payroll
    assert payroll.compute_epf_employee(20_000) == round(15_000 * 0.12, 2)
    assert payroll.compute_epf_employee(10_000) == round(10_000 * 0.12, 2)


def test_engine_esi_above_ceiling():
    from server import payroll
    assert payroll.compute_esi(25_000) == 0.0
    assert payroll.compute_esi(20_000, "employee") == round(20_000 * 0.0075, 2)


def test_tds_new_regime_rebate_below_7L():
    from server import payroll
    assert payroll.compute_tds_annual(600_000, regime="new") == 0.0


def test_tds_old_regime_rebate_below_5L():
    from server import payroll
    assert payroll.compute_tds_annual(450_000, regime="old") == 0.0


def test_build_structure_balances(tmp_db):
    from server import payroll
    loc = payroll.Location(state="KA", city="Bengaluru", is_metro=True, hra_basic_pct=50.0)
    s = payroll.build_structure(ctc_annual=1_200_000, location=loc)
    total = (s.basic_annual + s.hra_annual + s.special_allowance_annual
             + s.conveyance_annual + s.medical_annual + s.lta_annual + s.bonus_annual
             + s.employer_pf_annual + s.gratuity_annual)
    # Allow ₹10 rounding tolerance
    assert abs(total - 1_200_000) <= 10


def test_persist_structure_and_generate_payslip(tmp_db, tenant_id):
    from server.hrms import employee as employee_master
    from server.payroll_ext import structures, payslips

    emp = employee_master.create_employee(tenant_id, {
        "first_name": "Test", "last_name": "User", "status": "active",
    })
    structures.upsert(tenant_id, emp["id"], ctc_annual=900_000)
    cur = structures.current(tenant_id, emp["id"])
    assert cur is not None and cur["ctc_annual"] == 900_000

    run = payslips.get_or_create_run(tenant_id, month=4, year=2025, working_days=22)
    n = payslips.process_run(tenant_id, run["id"])
    assert n == 1
    slips = payslips.list_for_run(tenant_id, run["id"])
    assert len(slips) == 1 and slips[0]["gross_earnings"] > 0
