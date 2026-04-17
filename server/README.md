# TalentTrack — Python / Flask edition

A server-rendered recruitment tracker inspired by Greenhouse, Lever, Workable and Zoho Recruit. Flask + SQLite + Jinja templates — no frontend build step, no external database.

## Features

- **Vacancy management** with full **Job Description** (JD) capture
- **Candidates with CV auto-parsing** — drop a PDF/TXT/DOCX and the server extracts name, email, phone, location, headline, skills, experience, education, and years of experience (via `pypdf` + heuristics). Editable preview before save.
- **CV ↔ JD matching** — every uploaded CV is scored against every vacancy automatically; the detail page shows the score vs. the linked role, and a dedicated *Match against JDs* view ranks all roles for a candidate. Vacancy pages show ranked candidates.
- **Pipeline Kanban** — drag candidates across stages (Sourced → Screening → Interview → Offer → Hired/Rejected).
- **Interviews** — schedule, feedback, auto-advance stage.
- **Live dashboard** — KPIs (open vacancies, active candidates, pending offers, hired this month, avg. time-to-hire), hiring funnel, TAT aging buckets, avg. days in stage vs. SLA, open roles, recent activity.
- **Reports** — source breakdown, stage distribution, per-role snapshot, screen→offer conversion.
- **Data export/import** via JSON; reset wipes the DB.

## Run

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
python -m server.run
```

Open http://127.0.0.1:5000 and click **Load demo data** in the sidebar.

## JD matching

`server/matcher.py` scores CV vs. JD on three axes:

| Component       | Weight | How it's computed                                                                 |
|-----------------|-------:|-----------------------------------------------------------------------------------|
| Skill match     |    60% | Share of JD must-have skills found in the candidate's parsed skills or raw CV.     |
| Keyword match   |    30% | Token overlap of JD (title + description + skills) vs. CV (headline + skills + raw CV), minus stopwords. |
| Experience fit  |    10% | `min(1, candidate_years / required_years)`; JD-required years parsed automatically. |

`total = 60·skill + 30·keyword + 10·experience` → 0–100%.

The matcher is intentionally simple and explainable; the breakdown UI shows matched vs. missing skills, and the scoring weights are easy to tweak in one place.

## Files

- `app.py` — Flask routes
- `db.py` — SQLite + helpers
- `cv_parser.py` — PDF/DOCX text extraction + heuristic field parsing
- `matcher.py` — JD match scoring
- `analytics.py` — dashboard & report aggregations
- `seed.py` — demo data
- `templates/` — Jinja templates
- `static/` — CSS + a small drag-drop JS helper
