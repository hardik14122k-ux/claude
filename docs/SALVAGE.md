# Salvage map — pre-cleanup prototype code

The repo previously contained a single-tenant browser+Flask prototype called
**talenttrack**. On the cleanup commit it was removed in favour of the EDEN
multi-tenant FastAPI scaffold under `eden/`.

A small amount of code was ported into `eden/` at cleanup time. The rest was
left in git history rather than carried in the working tree as dead code. This
file records what is where, so future slices can pull from history without
having to spelunk.

## Ported into `eden/` at cleanup

| Old path | New path |
|---|---|
| `server/cv_parser.py` | `eden/src/eden/recruitment/cv_parser.py` |
| `server/matcher.py` | `eden/src/eden/recruitment/matcher.py` |
| CV-parser + matcher tests in `tests/test_recruitment_unchanged.py` | `eden/tests/recruitment/test_cv_parser.py`, `test_matcher.py` |

## Left in git history — retrieve when the relevant slice begins

Pre-cleanup commit: **`8c51c3e`** (`EDEN P0: scaffold FastAPI control plane + tenant provisioning`).

To recover any file from that snapshot:

```bash
git show 8c51c3e:<path>          # print
git show 8c51c3e:<path> > <new>  # extract
```

| When you start this slice... | ...pull these files from `8c51c3e` |
|---|---|
| Payroll (Indian statutory math: EPF, ESI, PT, TDS, gratuity, payslip generation) | `server/payroll.py`, `server/payroll_ext/structures.py`, `server/payroll_ext/payslips.py`, `server/payroll_ext/yearend.py` |
| Core HR (employee master, attendance, leave) | `server/hrms/employee.py`, `server/hrms/attendance.py`, `server/hrms/leave.py`, `server/hrms/schema.py` (schema is *design reference only* — do not port the SQLite DDL verbatim) |
| Compliance | `server/compliance/engine.py`, `server/compliance/reminders.py` |
| Recruitment schema design reference (vacancies, candidates, interviews, offers, stages) | `supabase/schema.sql`, `supabase/schema_v2.sql` — read for table shape and enum ideas; the multi-tenant DDL will be rewritten in `eden/migrations/tenant_template/` |
| Recruitment analytics (funnel, TAT, aging) | `server/analytics.py` |
| Frontend feature inventory (when a UI is built later) | `docs/HRMS_FRONTEND.md`, `js/views/*` |

All of the above is Flask/SQLite/localStorage prototype code. **Do not port
routing, auth, or DB layers** — those are replaced by FastAPI + Keycloak +
schema-per-tenant Postgres in eden. Port only pure business logic and use the
schema files as design reference.
