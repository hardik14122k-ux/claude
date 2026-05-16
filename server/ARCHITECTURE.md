# TalentTrack → HRMS Architecture Inventory

## 1. Current Module Map

### Server (primary codebase — Flask + SQLite + Jinja2)

| File | Role | Reusable As-Is |
|------|------|----------------|
| `app.py` | Flask routes: vacancies, candidates, upload, pipeline, interviews, reports, settings | Route handlers; keep as recruitment blueprint |
| `db.py` | SQLite connection manager, schema, CRUD for vacancies/candidates/interviews/activity | Connection helpers; `now_iso`, `new_id` → extract to shared |
| `cv_parser.py` | PDF/DOCX text extraction + heuristic field parsing | Fully reusable; expose as `server.shared.cv_parser` |
| `matcher.py` | JD ↔ CV weighted scoring | Fully reusable; no changes needed |
| `analytics.py` | Dashboard aggregations, TAT, funnel, aging | Reusable; `days_between`, `_parse_iso` → extract to shared |
| `payroll.py` | Indian payroll engine: EPF/ESI/PT/LWF/TDS, payslip generation | Fully reusable pure-functions module; needs DB layer on top |
| `seed.py` | Demo data generator | Keep; extend for HRMS entities |
| `run.py` | Entry point | Keep |

### Client (vanilla JS SPA — legacy parallel track)

| File | Role |
|------|------|
| `index.html`, `js/` | Browser-only recruitment tracker; **not the primary codebase** |
| `styles.css` | Standalone SPA styles |

---

## 2. Existing Data Model

```
vacancies          candidates          candidate_history
---------          ----------          -----------------
id (PK)            id (PK)             id (PK, auto)
title              name                candidate_id → candidates
department         email               stage
location           phone               from_stage
hiring_manager     location            at
openings           headline
priority           skills (JSON)
status             experience_years
target_close       education (JSON)
description        experience (JSON)
skills (JSON)      source
created_at         vacancy_id → vacancies
                   stage
                   rating
                   raw_cv
                   file_name
                   created_at / updated_at

interviews         activity
----------         --------
id (PK)            id (PK, auto)
candidate_id       type
interviewer        message
type               meta (JSON)
date               ts
status
feedback
rating
created_at
```

---

## 3. What Can Be Reused Without Modification

| Component | Reuse Target |
|-----------|-------------|
| `db.connect()` context manager | All new modules use same SQLite file |
| `db.now_iso()` | Extracted to `shared.utils` |
| `db.new_id(prefix)` | Extracted to `shared.utils` |
| `analytics._parse_iso()` | Extracted to `shared.utils` |
| `analytics.days_between()` | Extracted to `shared.utils` |
| `cv_parser.extract_text()` | Reused for employee document parsing |
| `cv_parser.parse_cv()` | Reused directly in recruitment + onboarding |
| `matcher.score()` | Unchanged |
| `payroll.compute_epf_employee()` etc. | All pure functions reused directly by payroll routes |
| `payroll.generate_payslip()` | Core of payslip service |
| `payroll.build_structure()` | Core of salary structure service |

---

## 4. What Needs Extracting Into Shared Modules

| Concern | Current Location | Target |
|---------|-----------------|--------|
| `now_iso`, `new_id` | `db.py` (lines 27-31) | `shared/utils.py` |
| `_parse_iso`, `days_between` | `analytics.py` (lines 10-28) | `shared/utils.py` |
| Activity logging | `db.log_activity()` | `shared/audit.py` (generalize) |
| File parsing | `cv_parser.py` | `shared/storage.py` wraps it |
| Row → dict deserialization | `db._row_to_dict()` | Keep in `db.py`, also used in hrms |

---

## 5. Tightly Coupled / Risky Areas

| Risk | Location | Mitigation |
|------|----------|------------|
| `db.init_db()` called in `before_request` | `app.py:29` | Idempotent; safe; move to `run.py` startup |
| `PARSED_CACHE` dict in `app.py` | `app.py:24` | Process-local; fine for dev; document limit |
| Hard-coded `secret_key` | `app.py:19` | Move to `config.py` / env var |
| `DB_PATH` hard-coded | `db.py:12` | Move to `config.py` for tenant paths |
| Recruitment routes in monolithic `app.py` | `app.py` | Refactor to `recruitment/` blueprint, keep old routes |
| No auth on any route | All routes | Add auth blueprint; protect with decorator |

---

## 6. HRMS Extension Architecture

```
server/
  config.py              ← app config, env vars, DB path
  shared/
    __init__.py
    utils.py             ← now_iso, new_id, _parse_iso, days_between
    auth.py              ← login/logout, current_user, login_required, role_required
    audit.py             ← structured audit logging (who, what, when, tenant)
    notifications.py     ← email/SMS/Slack/WhatsApp stubs
    storage.py           ← file upload abstraction
  recruitment/
    __init__.py          ← Blueprint
    routes.py            ← existing app.py routes moved here
    requisitions.py      ← requisition lifecycle + approvals
    offers.py            ← offer letter generation
    onboarding.py        ← onboarding handoff to employee master
  hrms/
    __init__.py          ← Blueprint
    schema.py            ← DB schema: tenants, orgs, employees, docs, attendance, leave
    employee.py          ← employee master CRUD
    org.py               ← org structure (departments, positions, reporting)
    attendance.py        ← daily attendance, regularization
    leave.py             ← leave policies, requests, approvals
    documents.py         ← employee document store
    ess.py               ← employee self-service (profile, leave, payslips)
    routes.py            ← all HRMS Flask routes
  payroll_ext/
    __init__.py          ← Blueprint
    schema.py            ← payroll_runs, payslips, salary_structures, reimbursements
    structures.py        ← salary structure management (wraps payroll.build_structure)
    payslips.py          ← payslip DB layer (wraps payroll.generate_payslip)
    arrears.py           ← arrears calculation
    reimbursements.py    ← reimbursement claims
    yearend.py           ← Form 16, annual IT computations
    routes.py            ← payroll Flask routes
  compliance/
    __init__.py          ← Blueprint
    engine.py            ← pluggable rules: PF, ESI, PT, TDS, gratuity, leave
    reminders.py         ← statutory deadline reminders
    routes.py            ← compliance dashboard routes
  templates/
    (existing templates unchanged)
    hrms/
    payroll/
    compliance/
```

---

## 7. Multi-Tenancy Strategy

- All new tables include `tenant_id TEXT NOT NULL DEFAULT 'default'`
- Existing tables left unchanged (single-tenant for now)
- `g.tenant_id` set by auth middleware from JWT/session
- All CRUD helpers accept and filter by `tenant_id`
- Future: per-tenant DB files via configurable `DB_PATH`

---

## 8. Indian Compliance Coverage

Already implemented in `payroll.py`:
- EPF (employee + employer 12%, EPS 8.33%)
- ESI (0.75% employee, 3.25% employer, ₹21k ceiling)
- PT (slab-based, configurable per state)
- LWF (configurable per state)
- TDS (old/new regime FY 2024-25, Section 87A rebate)
- Gratuity accrual (4.81% of basic)

Needs adding:
- Arrears computation
- Form 16 Part A + Part B generation
- Annual IT computation worksheet
- Compliance calendar (ECR filing deadlines, PT remittance dates)
- State-specific minimum wage enforcement

---

## 9. Reuse / Refactor / Add Summary

| Category | Items |
|----------|-------|
| **Reuse as-is** | `cv_parser`, `matcher`, all `payroll.*` pure functions, `seed.py` |
| **Extract to shared** | `now_iso`, `new_id`, `_parse_iso`, `days_between`, `log_activity` |
| **Refactor** | `app.py` → `recruitment/routes.py` blueprint (keep old URL routes) |
| **Add new** | auth, RBAC, multi-tenancy, employee master, attendance, leave, payroll routes, compliance, notifications, ESS |
