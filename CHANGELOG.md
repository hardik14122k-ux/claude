# Changelog

## [0.1.0] — cleanup

Reset the repository to the EDEN multi-tenant FastAPI scaffold and removed
the single-tenant talenttrack prototype.

### Added
- `eden/src/eden/recruitment/cv_parser.py` — ported from `server/cv_parser.py`.
- `eden/src/eden/recruitment/matcher.py` — ported from `server/matcher.py`.
- `eden/tests/recruitment/test_cv_parser.py`, `test_matcher.py` — regression
  tests for the two ported modules.
- `pypdf` and `python-docx` added to `eden/pyproject.toml` dependencies.
- `docs/SALVAGE.md` — pointer to pre-cleanup commit `8c51c3e` listing which
  prototype files to retrieve from git history when future slices need them
  (Payroll, Core HR, Compliance, schema design).

### Removed
- `index.html`, `styles.css`, `js/` — vanilla JS SPA prototype (talenttrack
  frontend).
- `server/` — Flask + SQLite HRMS monolith prototype.
- `supabase/` — single-tenant Supabase DDL.
- `tests/` — Flask test suite (the two pure-function tests worth keeping were
  ported into `eden/tests/recruitment/`).
- `docs/HRMS_FRONTEND.md` — prototype frontend feature notes.

All removed code remains accessible via git history at pre-cleanup commit
`8c51c3e`. See `docs/SALVAGE.md` for retrieval guidance.
