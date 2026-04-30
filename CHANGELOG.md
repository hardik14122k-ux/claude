# Changelog

## [Unreleased]

### Added — HRMS extension (Indian HR/Payroll/Compliance)
- **Architecture inventory** at `server/ARCHITECTURE.md` mapping every existing
  module, what to reuse vs. extract vs. add.
- **Shared modules** (`server/shared/`):
  - `utils.py` — extracted `now_iso`, `new_id`, `parse_iso`, `days_between`,
    `same_month`, `fiscal_year` from `db.py` and `analytics.py`.
  - `auth.py` — session-based login, password hashing, RBAC roles
    (`super_admin`, `hr_admin`, `hr_manager`, `recruiter`, `employee`,
    `read_only`), `login_required` and `role_required` decorators.
  - `audit.py` — structured audit log writer with tenant_id and diff capture.
  - `notifications.py` — email/SMS/WhatsApp/Slack channel stubs (env-driven).
  - `storage.py` — local-filesystem document storage with content-type detection.
- **HRMS foundation** (`server/hrms/`):
  - `schema.py` — multi-tenant DB schema: `tenants`, `users`, `departments`,
    `positions`, `employees`, `documents`, `attendance`,
    `attendance_regularizations`, `leave_types`, `leave_balances`,
    `leave_requests`, `holidays`, `audit_log`, plus recruitment and payroll
    extension tables.
  - `employee.py` — full employee master CRUD with auto-numbering and
    `from_candidate()` onboarding helper.
  - `attendance.py` — daily attendance, check-in/out, monthly summaries,
    regularization workflow.
  - `leave.py` — leave types, balances, requests, approvals, monthly accruals.
  - `documents.py` — document upload, listing, download tied to any owner type.
  - `routes.py` — Flask blueprint for employees / org / attendance / leave / ESS / audit.
- **Recruitment extensions** (`server/recruitment/`):
  - `requisitions.py` — formal requisition with approval workflow that creates
    a vacancy on approval (existing `app.py` routes unchanged).
  - `offers.py` — offer letter lifecycle (draft → sent → accepted/declined),
    with notification dispatch.
  - `onboarding.py` — single-call candidate→employee handoff.
  - `routes.py` — Flask blueprint for requisitions / offers / onboarding.
- **Payroll extensions** (`server/payroll_ext/`):
  - `structures.py` — DB-persistent salary structures wrapping
    `payroll.build_structure`, with effective-from/to dating.
  - `payslips.py` — payroll-run lifecycle (draft → processed → approved →
    locked) and DB-persisted payslip generation that reuses
    `payroll.generate_payslip` and pulls paid days from attendance.
  - `arrears.py`, `reimbursements.py` — workflow + persistence.
  - `yearend.py` — FY aggregation, regime comparison, Form 16 record
    generation.
  - `routes.py` — Flask blueprint for structures, runs, payslips, locations,
    reimbursements, year-end.
- **Compliance** (`server/compliance/`):
  - `engine.py` — pluggable rule engine with built-in rules: PF eligibility,
    ESI ceiling, PT state coverage, gratuity eligibility, TDS regime
    comparison, minimum wage check, leave encashment cap.
  - `reminders.py` — auto-seeded statutory deadline calendar (PF/ESI/PT/TDS).
  - `routes.py` — compliance dashboard blueprint.
- **Auth blueprint** (`server/auth_routes.py`) at `/auth/login` and
  `/auth/logout`; default `admin@example.com` / `admin` is bootstrapped on
  first run.
- **Templates** for every new page under `templates/hrms/`, `templates/payroll/`,
  `templates/recruit/`, `templates/compliance/`, plus `auth_login.html`.
- **Sidebar nav** updated in `base.html` with HRMS, Payroll, Recruit-ext,
  Compliance, Audit log, and sign-in/out links.
- **Tests** under `tests/` covering payroll engine math, salary-structure
  persistence, payslip generation, employee CRUD, attendance, leave,
  audit log, compliance rules, and verification that all legacy
  recruitment routes still return HTTP 200.

### Reuse / Refactor
- `server/payroll.py` (Indian payroll engine), `cv_parser.py`, `matcher.py`,
  `analytics.py`, `seed.py`, and all of `db.py` are reused without
  modification — `app.py` recruitment routes work exactly as before.
- `db.py` helpers `now_iso` and `new_id` retained for backward compat;
  new modules import from `shared.utils` instead.

### Added
- **JavaScript SPA** (`index.html`, `js/`) — zero-backend recruitment tracker
  - CV auto-parsing via PDF.js (name, email, phone, skills, experience, education)
  - Vacancy management with priority, SLA targets, and skills tagging
  - Kanban pipeline with drag-and-drop stage transitions
  - Interview scheduling with feedback and auto-stage advancement
  - Live dashboard: KPIs, hiring funnel, TAT aging buckets, avg. days in stage vs. SLA
  - Reports: source breakdown, stage distribution, per-role snapshot
  - LocalStorage persistence, JSON export/import, demo seed data

- **Python/Flask edition** (`server/`) — server-rendered with SQLite
  - Parallel feature parity with the JS SPA
  - **JD matching module** (`server/matcher.py`): scores CV against every vacancy's
    Job Description automatically on upload
    - Skill match (60%), keyword overlap (30%), experience fit (10%)
    - Matched/missing skill breakdown, required years auto-parsed from JD text
  - CV upload flow shows ranked JD matches and pre-selects the best role
  - Candidate detail shows match score vs. linked vacancy
  - `/candidates/<id>/match` — ranked vacancy list for one candidate
  - `/vacancies/<id>/match` — ranked candidate list for one vacancy
  - Kanban drag-and-drop via lightweight fetch JS
  - JSON export/import, reset, demo seed data
