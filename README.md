# TalentTrack — Recruitment Tracker

A full-featured, zero-backend recruitment tracker inspired by Greenhouse, Lever, Workable and Zoho Recruit. Everything runs in the browser — data is stored in `localStorage`, CV parsing uses PDF.js + heuristics.

## Features

- **Vacancy management** — title, department, location, hiring manager, openings, priority, target-close date, skills.
- **Candidates with CV auto-parsing** — drop a PDF/TXT/DOCX and the app extracts name, email, phone, location, headline, skills, experience history, education, and years of experience. Edit before saving.
- **Pipeline Kanban** — drag candidates across stages (Sourced → Screening → Interview → Offer → Hired / Rejected), per vacancy or consolidated.
- **Interviews** — schedule, capture interviewer, type, status, rating, and feedback. Candidates auto-advance into the Interview stage.
- **Live dashboard** — KPIs (open vacancies, active candidates, pending offers, hired this month, avg. time-to-hire), funnel chart, TAT aging buckets, average days in stage vs. SLA, open roles, recent activity.
- **Reports** — per-source breakdown, stage distribution, per-role snapshot, screen-to-offer conversion.
- **Data export / import** — JSON round-trip; reset wipes local state.
- **Global search + quick actions** in the top bar.

## Run it

Because ES modules are used, serve the folder with any static server:

```bash
python3 -m http.server 8080
# then open http://localhost:8080/
```

Click **Load demo data** in the sidebar to populate sample vacancies, candidates, and interviews.

## Files

- `index.html` — shell
- `styles.css` — theme
- `js/app.js` — router + global wiring
- `js/store.js` — reactive localStorage store, derived helpers (TAT, aging)
- `js/cv-parser.js` — PDF.js text extraction + regex/heuristic field extraction
- `js/seed.js` — demo data
- `js/ui.js` — DOM helpers (`h`, modal, toast)
- `js/views/` — dashboard, vacancies, candidates, pipeline, interviews, reports, settings

## CV parsing notes

The parser handles the common resume layout conventions: it finds email/phone via regex, guesses the candidate's name from the first few lines with capitalisation heuristics, splits sections on known headers (Summary / Skills / Experience / Education), matches skills against a 100+ term library, parses date ranges (`Jan 2019 – Present`, `2020-2023`) to estimate years of experience, and uses a fallback explicit-match like `"5+ years of experience"`.

You always see a preview and can correct anything before  saving.
