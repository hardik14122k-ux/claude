# Changelog

## [Unreleased]

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
