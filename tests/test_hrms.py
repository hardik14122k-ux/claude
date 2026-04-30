"""Cover employee master, attendance, leave, audit log."""


def test_employee_create_and_update(tmp_db, tenant_id):
    from server.hrms import employee as employee_master
    e = employee_master.create_employee(tenant_id, {
        "first_name": "Asha", "last_name": "Rao", "email": "asha@x.com",
    })
    assert e["employee_code"].startswith("EMP")
    e2 = employee_master.update_employee(tenant_id, e["id"], {"phone": "+91-99999"})
    assert e2["phone"] == "+91-99999"


def test_employee_code_sequencing(tmp_db, tenant_id):
    from server.hrms import employee as employee_master
    a = employee_master.create_employee(tenant_id, {"first_name": "A"})
    b = employee_master.create_employee(tenant_id, {"first_name": "B"})
    assert a["employee_code"] != b["employee_code"]


def test_attendance_upsert_and_summary(tmp_db, tenant_id):
    from server.hrms import attendance, employee as employee_master
    e = employee_master.create_employee(tenant_id, {"first_name": "Test"})
    attendance.upsert(tenant_id, e["id"], "2025-04-01", status="present")
    attendance.upsert(tenant_id, e["id"], "2025-04-02", status="leave")
    s = attendance.monthly_summary(tenant_id, e["id"], 2025, 4)
    assert s["counts"]["present"] == 1
    assert s["counts"]["leave"] == 1


def test_leave_request_and_approve(tmp_db, tenant_id):
    from server.hrms import employee as employee_master, leave, schema as hrms_db
    from server.shared.utils import fiscal_year
    lt = hrms_db.upsert_leave_type(tenant_id, {
        "code": "CL", "name": "Casual", "annual_quota": 12, "is_paid": True,
    })
    e = employee_master.create_employee(tenant_id, {"first_name": "Test"})
    fy = fiscal_year()
    start = f"{fy}-05-10"
    end = f"{fy}-05-11"
    req = leave.request_leave(tenant_id, e["id"], lt["id"], start, end)
    assert req["status"] == "pending"
    leave.decide_request(tenant_id, req["id"], approve=True, approver_id="approver-x")
    bals = leave.list_balances(tenant_id, e["id"], fy=fy)
    assert any(b["used"] >= 1 for b in bals)


def test_audit_log_appends(tmp_db, tenant_id):
    from server.hrms import employee as employee_master, schema as hrms_db
    e = employee_master.create_employee(tenant_id, {"first_name": "Audit"}, actor_id="u1")
    rows = hrms_db.list_audit(tenant_id, entity_type="employee", entity_id=e["id"])
    assert any(r["action"] == "create" for r in rows)


def test_compliance_rules_run(tmp_db):
    from server.compliance import engine
    findings = engine.evaluate({
        "basic_monthly": 25_000, "gross_monthly": 60_000,
        "annual_gross": 720_000, "state": "Maharashtra", "tenure_months": 60,
    })
    codes = {f.code for f in findings}
    assert "esi.not_applicable" in codes
    assert "gratuity.payable" in codes
