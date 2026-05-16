"""HRMS database schema and CRUD helpers.

All tables include `tenant_id` for multi-tenant isolation. The schema is
applied additively to the existing recruitment DB (server/data.db) so the
recruitment module keeps working unchanged.

Convention: every table here is prefixed conceptually for HRMS use.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .. import db as recruitment_db
from ..config import DEFAULT_TENANT
from ..shared.auth import hash_password
from ..shared.utils import new_id, now_iso

SCHEMA = """
-- ===== Tenants & Users =====
CREATE TABLE IF NOT EXISTS tenants (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    domain       TEXT,
    plan         TEXT DEFAULT 'starter',
    status       TEXT DEFAULT 'active',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    email           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'employee',
    employee_id     TEXT,
    status          TEXT DEFAULT 'active',
    last_login_at   TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(tenant_id, email),
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- ===== Organization Structure =====
CREATE TABLE IF NOT EXISTS departments (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    name         TEXT NOT NULL,
    code         TEXT,
    parent_id    TEXT,
    head_id      TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    title        TEXT NOT NULL,
    department_id TEXT,
    grade        TEXT,
    description  TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- ===== Employee Master =====
CREATE TABLE IF NOT EXISTS employees (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    employee_code       TEXT NOT NULL,
    first_name          TEXT NOT NULL,
    last_name           TEXT,
    email               TEXT,
    personal_email      TEXT,
    phone               TEXT,
    dob                 TEXT,
    gender              TEXT,
    blood_group         TEXT,
    marital_status      TEXT,
    pan                 TEXT,
    aadhaar_last4       TEXT,         -- store only last 4 digits for safety
    uan                 TEXT,         -- EPF UAN
    pf_number           TEXT,
    esi_number          TEXT,
    bank_account_no     TEXT,
    bank_ifsc           TEXT,
    bank_name           TEXT,
    address_line        TEXT,
    city                TEXT,
    state               TEXT,
    pincode             TEXT,
    country             TEXT DEFAULT 'India',
    emergency_contact   TEXT,
    emergency_phone     TEXT,
    department_id       TEXT,
    position_id         TEXT,
    manager_id          TEXT,
    work_location       TEXT,
    employment_type     TEXT DEFAULT 'permanent',  -- permanent, contract, intern
    status              TEXT DEFAULT 'active',     -- active, on_leave, resigned, terminated
    date_joined         TEXT,
    date_confirmed      TEXT,
    date_exit           TEXT,
    probation_months    INTEGER DEFAULT 6,
    notice_period_days  INTEGER DEFAULT 60,
    candidate_id        TEXT,         -- link back to recruitment candidate row, if onboarded
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(tenant_id, employee_code),
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY(department_id) REFERENCES departments(id) ON DELETE SET NULL,
    FOREIGN KEY(position_id)   REFERENCES positions(id)   ON DELETE SET NULL,
    FOREIGN KEY(manager_id)    REFERENCES employees(id)   ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_employees_tenant ON employees(tenant_id);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);

-- ===== Documents =====
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    owner_type    TEXT NOT NULL,    -- employee, candidate, vacancy, payroll
    owner_id      TEXT NOT NULL,
    category      TEXT,             -- pan, aadhaar, offer_letter, payslip, contract, certificate
    title         TEXT,
    file_name     TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    size_bytes    INTEGER,
    sha256        TEXT,
    content_type  TEXT,
    uploaded_by   TEXT,
    is_confidential INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(tenant_id, owner_type, owner_id);

-- ===== Attendance =====
CREATE TABLE IF NOT EXISTS attendance (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    date          TEXT NOT NULL,        -- YYYY-MM-DD
    check_in      TEXT,                 -- ISO datetime
    check_out     TEXT,
    work_minutes  INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'present',  -- present, absent, half_day, leave, holiday, weekoff
    source        TEXT DEFAULT 'manual',   -- manual, biometric, mobile, web
    notes         TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(tenant_id, employee_id, date),
    FOREIGN KEY(tenant_id)   REFERENCES tenants(id)   ON DELETE CASCADE,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attendance_emp_date ON attendance(employee_id, date);

CREATE TABLE IF NOT EXISTS attendance_regularizations (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    date          TEXT NOT NULL,
    requested_check_in  TEXT,
    requested_check_out TEXT,
    reason        TEXT,
    status        TEXT DEFAULT 'pending',  -- pending, approved, rejected
    approver_id   TEXT,
    decided_at    TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- ===== Leave =====
CREATE TABLE IF NOT EXISTS leave_types (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    code          TEXT NOT NULL,        -- CL, SL, PL, LWP, ML, PT
    name          TEXT NOT NULL,
    annual_quota  REAL DEFAULT 0,       -- days/year
    accrual       TEXT DEFAULT 'yearly',-- yearly, monthly, none
    carry_forward INTEGER DEFAULT 0,    -- max days that carry forward
    encashable    INTEGER DEFAULT 0,
    is_paid       INTEGER DEFAULT 1,
    requires_proof INTEGER DEFAULT 0,
    UNIQUE(tenant_id, code)
);

CREATE TABLE IF NOT EXISTS leave_balances (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    leave_type_id TEXT NOT NULL,
    fy_year       INTEGER NOT NULL,
    opening       REAL DEFAULT 0,
    accrued       REAL DEFAULT 0,
    used          REAL DEFAULT 0,
    encashed      REAL DEFAULT 0,
    UNIQUE(tenant_id, employee_id, leave_type_id, fy_year)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    leave_type_id TEXT NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    days          REAL NOT NULL,
    reason        TEXT,
    status        TEXT DEFAULT 'pending',  -- pending, approved, rejected, cancelled
    approver_id   TEXT,
    decided_at    TEXT,
    decision_note TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leave_requests_emp ON leave_requests(employee_id, status);

CREATE TABLE IF NOT EXISTS holidays (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    date        TEXT NOT NULL,
    name        TEXT NOT NULL,
    type        TEXT DEFAULT 'gazetted',
    location    TEXT,
    UNIQUE(tenant_id, date, location)
);

-- ===== Audit Log =====
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     TEXT NOT NULL,
    actor_id      TEXT,
    action        TEXT NOT NULL,       -- create, update, delete, approve, login, etc.
    entity_type   TEXT NOT NULL,
    entity_id     TEXT,
    message       TEXT,
    diff          TEXT DEFAULT '{}',
    ip            TEXT,
    ts            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON audit_log(tenant_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);

-- ===== Recruitment Extensions =====
CREATE TABLE IF NOT EXISTS requisitions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    department_id   TEXT,
    position_id     TEXT,
    requested_by    TEXT,
    openings        INTEGER DEFAULT 1,
    employment_type TEXT DEFAULT 'permanent',
    target_ctc_min  REAL,
    target_ctc_max  REAL,
    justification   TEXT,
    status          TEXT DEFAULT 'pending',  -- pending, approved, rejected, fulfilled, cancelled
    approver_id     TEXT,
    decided_at      TEXT,
    vacancy_id      TEXT,                    -- created vacancy after approval
    created_at      TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS offers (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    vacancy_id      TEXT,
    offered_ctc     REAL NOT NULL,
    offered_position TEXT,
    join_date       TEXT,
    expiry_date     TEXT,
    status          TEXT DEFAULT 'draft',    -- draft, sent, accepted, declined, expired, revoked
    letter_doc_id   TEXT,
    notes           TEXT,
    sent_at         TEXT,
    decided_at      TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- ===== Payroll Extensions =====
CREATE TABLE IF NOT EXISTS payroll_locations (
    id                       TEXT PRIMARY KEY,
    tenant_id                TEXT NOT NULL,
    state                    TEXT NOT NULL,
    city                     TEXT NOT NULL,
    is_metro                 INTEGER DEFAULT 0,
    hra_basic_pct            REAL DEFAULT 40.0,
    pt_slabs                 TEXT DEFAULT '[]',
    lwf_employee_monthly     REAL DEFAULT 0,
    lwf_employer_monthly     REAL DEFAULT 0,
    min_wage_unskilled       REAL DEFAULT 0,
    min_wage_semi_skilled    REAL DEFAULT 0,
    min_wage_skilled         REAL DEFAULT 0,
    UNIQUE(tenant_id, state, city)
);

CREATE TABLE IF NOT EXISTS salary_structures (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    employee_id         TEXT NOT NULL,
    effective_from      TEXT NOT NULL,
    effective_to        TEXT,
    ctc_annual          REAL NOT NULL,
    basic_annual        REAL NOT NULL,
    hra_annual          REAL NOT NULL,
    special_allowance_annual REAL NOT NULL,
    conveyance_annual   REAL DEFAULT 0,
    medical_annual      REAL DEFAULT 0,
    lta_annual          REAL DEFAULT 0,
    bonus_annual        REAL DEFAULT 0,
    employer_pf_annual  REAL DEFAULT 0,
    employer_eps_annual REAL DEFAULT 0,
    employer_esi_annual REAL DEFAULT 0,
    gratuity_annual     REAL DEFAULT 0,
    location_id         TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_struct_emp ON salary_structures(employee_id, effective_from);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    month         INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    status        TEXT DEFAULT 'draft',    -- draft, processing, processed, approved, paid, locked
    working_days  INTEGER NOT NULL,
    notes         TEXT,
    processed_by  TEXT,
    processed_at  TEXT,
    approved_by   TEXT,
    approved_at   TEXT,
    locked_at     TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(tenant_id, month, year)
);

CREATE TABLE IF NOT EXISTS payslips (
    id                   TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    payroll_run_id       TEXT NOT NULL,
    employee_id          TEXT NOT NULL,
    month                INTEGER NOT NULL,
    year                 INTEGER NOT NULL,
    working_days         INTEGER NOT NULL,
    paid_days            REAL NOT NULL,
    earnings             TEXT NOT NULL,        -- JSON
    deductions           TEXT NOT NULL,        -- JSON
    employer_contributions TEXT NOT NULL,      -- JSON
    gross_earnings       REAL NOT NULL,
    total_deductions     REAL NOT NULL,
    net_pay              REAL NOT NULL,
    ctc_total            REAL NOT NULL,
    pdf_doc_id           TEXT,
    created_at           TEXT NOT NULL,
    UNIQUE(tenant_id, payroll_run_id, employee_id),
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY(payroll_run_id) REFERENCES payroll_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_payslips_emp ON payslips(employee_id, year, month);

CREATE TABLE IF NOT EXISTS reimbursements (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    category      TEXT NOT NULL,    -- travel, food, internet, fuel, mobile
    amount        REAL NOT NULL,
    expense_date  TEXT,
    description   TEXT,
    receipt_doc_id TEXT,
    status        TEXT DEFAULT 'pending',
    approver_id   TEXT,
    decided_at    TEXT,
    paid_in_run_id TEXT,            -- payroll_run_id once paid
    created_at    TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS arrears (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    month         INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    component     TEXT NOT NULL,    -- basic, hra, special, etc.
    amount        REAL NOT NULL,
    reason        TEXT,
    paid_in_run_id TEXT,
    created_at    TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS form16_records (
    id                TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL,
    employee_id       TEXT NOT NULL,
    fy_year           INTEGER NOT NULL,
    gross_salary      REAL NOT NULL,
    exemptions        REAL DEFAULT 0,
    standard_deduction REAL DEFAULT 0,
    chapter_via       REAL DEFAULT 0,    -- 80C, 80D, etc. total
    taxable_income    REAL NOT NULL,
    tax_before_rebate REAL DEFAULT 0,
    rebate_87a        REAL DEFAULT 0,
    cess              REAL DEFAULT 0,
    total_tax         REAL NOT NULL,
    tds_deducted      REAL DEFAULT 0,
    regime            TEXT DEFAULT 'new',
    pdf_doc_id        TEXT,
    generated_at      TEXT,
    created_at        TEXT NOT NULL,
    UNIQUE(tenant_id, employee_id, fy_year)
);

-- ===== Compliance Reminders =====
CREATE TABLE IF NOT EXISTS compliance_reminders (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,    -- pf, esi, pt, tds, gratuity, lwf
    due_date      TEXT NOT NULL,
    recurrence    TEXT DEFAULT 'monthly',
    description   TEXT,
    status        TEXT DEFAULT 'open',
    completed_at  TEXT,
    created_at    TEXT NOT NULL
);
"""


def init_hrms_db() -> None:
    with recruitment_db.connect() as c:
        c.executescript(SCHEMA)
        # Ensure default tenant exists for single-tenant deployments.
        existing = c.execute("SELECT 1 FROM tenants WHERE id = ?", (DEFAULT_TENANT,)).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO tenants (id, name, plan, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (DEFAULT_TENANT, "Default Organization", "starter", "active", now_iso()),
            )


# ---------- Generic helpers ----------

def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ---------- Tenants ----------

def list_tenants() -> list[dict]:
    with recruitment_db.connect() as c:
        return _rows(c.execute("SELECT * FROM tenants ORDER BY created_at DESC").fetchall())


def create_tenant(name: str, domain: str = "", plan: str = "starter") -> dict:
    tid = new_id("tnt")
    with recruitment_db.connect() as c:
        c.execute(
            "INSERT INTO tenants (id, name, domain, plan, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tid, name, domain, plan, "active", now_iso()),
        )
    return {"id": tid, "name": name, "domain": domain, "plan": plan, "status": "active"}


# ---------- Users ----------

def get_user_by_id(uid: str) -> dict | None:
    with recruitment_db.connect() as c:
        return _row(c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())


def get_user_by_email(tenant_id: str, email: str) -> dict | None:
    with recruitment_db.connect() as c:
        return _row(c.execute(
            "SELECT * FROM users WHERE tenant_id = ? AND LOWER(email) = LOWER(?)",
            (tenant_id, email),
        ).fetchone())


def create_user(
    *,
    tenant_id: str,
    email: str,
    password: str,
    name: str,
    role: str = "employee",
    employee_id: str | None = None,
) -> dict:
    uid = new_id("usr")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO users (id, tenant_id, email, password_hash, name, role, employee_id,
                                  status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (uid, tenant_id, email, hash_password(password), name, role, employee_id, now_iso()),
        )
    return get_user_by_id(uid)


def list_users(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return _rows(c.execute(
            "SELECT id, tenant_id, email, name, role, employee_id, status, last_login_at, created_at "
            "FROM users WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall())


def touch_login(uid: str) -> None:
    with recruitment_db.connect() as c:
        c.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), uid))


# ---------- Departments / Positions ----------

def list_departments(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return _rows(c.execute(
            "SELECT * FROM departments WHERE tenant_id = ? ORDER BY name",
            (tenant_id,),
        ).fetchall())


def create_department(tenant_id: str, data: dict) -> dict:
    did = new_id("dept")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO departments (id, tenant_id, name, code, parent_id, head_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (did, tenant_id, data["name"], data.get("code", ""), data.get("parent_id"),
             data.get("head_id"), now_iso()),
        )
    return {"id": did, **data}


def list_positions(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return _rows(c.execute(
            "SELECT * FROM positions WHERE tenant_id = ? ORDER BY title",
            (tenant_id,),
        ).fetchall())


def create_position(tenant_id: str, data: dict) -> dict:
    pid = new_id("pos")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO positions (id, tenant_id, title, department_id, grade, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, tenant_id, data["title"], data.get("department_id"), data.get("grade", ""),
             data.get("description", ""), now_iso()),
        )
    return {"id": pid, **data}


# ---------- Holidays / Leave Types ----------

def list_holidays(tenant_id: str, year: int | None = None) -> list[dict]:
    sql = "SELECT * FROM holidays WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if year:
        sql += " AND date LIKE ?"
        params.append(f"{year}-%")
    sql += " ORDER BY date"
    with recruitment_db.connect() as c:
        return _rows(c.execute(sql, params).fetchall())


def add_holiday(tenant_id: str, date: str, name: str, type_: str = "gazetted",
                location: str = "") -> dict:
    hid = new_id("hol")
    with recruitment_db.connect() as c:
        c.execute(
            "INSERT OR IGNORE INTO holidays (id, tenant_id, date, name, type, location) VALUES (?, ?, ?, ?, ?, ?)",
            (hid, tenant_id, date, name, type_, location),
        )
    return {"id": hid, "date": date, "name": name, "type": type_, "location": location}


def list_leave_types(tenant_id: str) -> list[dict]:
    with recruitment_db.connect() as c:
        return _rows(c.execute(
            "SELECT * FROM leave_types WHERE tenant_id = ? ORDER BY code",
            (tenant_id,),
        ).fetchall())


def get_leave_type(tenant_id: str, code: str) -> dict | None:
    with recruitment_db.connect() as c:
        return _row(c.execute(
            "SELECT * FROM leave_types WHERE tenant_id = ? AND code = ?",
            (tenant_id, code),
        ).fetchone())


def upsert_leave_type(tenant_id: str, data: dict) -> dict:
    """Create or update a leave type. Idempotent on (tenant, code)."""
    existing = get_leave_type(tenant_id, data["code"])
    with recruitment_db.connect() as c:
        if existing:
            c.execute(
                """UPDATE leave_types SET name = ?, annual_quota = ?, accrual = ?,
                       carry_forward = ?, encashable = ?, is_paid = ?, requires_proof = ?
                   WHERE id = ?""",
                (data["name"], data.get("annual_quota", 0), data.get("accrual", "yearly"),
                 data.get("carry_forward", 0), 1 if data.get("encashable") else 0,
                 1 if data.get("is_paid", True) else 0,
                 1 if data.get("requires_proof") else 0, existing["id"]),
            )
            return get_leave_type(tenant_id, data["code"])
        lid = new_id("lvt")
        c.execute(
            """INSERT INTO leave_types (id, tenant_id, code, name, annual_quota, accrual,
                                         carry_forward, encashable, is_paid, requires_proof)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lid, tenant_id, data["code"], data["name"], data.get("annual_quota", 0),
             data.get("accrual", "yearly"), data.get("carry_forward", 0),
             1 if data.get("encashable") else 0,
             1 if data.get("is_paid", True) else 0,
             1 if data.get("requires_proof") else 0),
        )
    return get_leave_type(tenant_id, data["code"])


# ---------- Audit Log ----------

def list_audit(tenant_id: str, limit: int = 50, entity_type: str | None = None,
               entity_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM audit_log WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with recruitment_db.connect() as c:
        rows = _rows(c.execute(sql, params).fetchall())
    for r in rows:
        try:
            r["diff"] = json.loads(r.get("diff") or "{}")
        except json.JSONDecodeError:
            r["diff"] = {}
    return rows
