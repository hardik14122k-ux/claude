"""Populate the DB with realistic demo data so the dashboard feels alive."""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def seed_demo_data() -> bool:
    with db.connect() as c:
        if c.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0] > 0:
            return False
        if c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] > 0:
            return False

    now = datetime.now(timezone.utc)

    vacancy_defs = [
        ("Senior Backend Engineer", "Engineering", "Bengaluru, IN", "Priya Raman", 2, "High",   14, ["Python","PostgreSQL","AWS","Kubernetes"]),
        ("Product Designer",         "Design",      "Remote",       "Alex Hughes", 1, "Medium", 21, ["Figma","UX","Prototyping"]),
        ("Data Scientist",           "Data",        "London, UK",   "Rahul Nair",  1, "High",   10, ["Python","PyTorch","SQL"]),
        ("Technical Recruiter",      "People",      "New York, US", "Sara Owens",  1, "Low",    30, ["Sourcing","ATS","Greenhouse"]),
    ]

    vacancies = []
    for title, dept, loc, mgr, openings, prio, days_out, skills in vacancy_defs:
        v = db.create_vacancy({
            "title": title,
            "department": dept,
            "location": loc,
            "hiring_manager": mgr,
            "openings": openings,
            "priority": prio,
            "status": "Open",
            "target_close": _iso(now + timedelta(days=days_out)),
            "skills": skills,
        })
        vacancies.append(v)

    candidate_defs = [
        ("Ananya Iyer",     "ananya.iyer@example.com",     ["Python","Django","PostgreSQL","AWS"]),
        ("Marcus Hale",     "marcus.hale@example.com",     ["Go","Kubernetes","Terraform","AWS"]),
        ("Yuki Tanaka",     "yuki.tanaka@example.com",     ["Python","Airflow","Snowflake","SQL"]),
        ("Isla Fernandez",  "isla.fernandez@example.com",  ["Figma","UX","A/B Testing"]),
        ("Kenji Park",      "kenji.park@example.com",      ["React","TypeScript","Node.js"]),
        ("Zoe Lewis",       "zoe.lewis@example.com",       ["PyTorch","TensorFlow","Python"]),
        ("Rahul Mehta",     "rahul.mehta@example.com",     ["Sourcing","Greenhouse","ATS"]),
        ("Nadia Khan",      "nadia.khan@example.com",      ["Java","Spring","Microservices"]),
        ("Oliver Schmidt",  "oliver.schmidt@example.com",  ["Python","FastAPI","Redis"]),
        ("Chen Wei",        "chen.wei@example.com",        ["Figma","Product Management","UI"]),
        ("Farah Aziz",      "farah.aziz@example.com",      ["SQL","BigQuery","Python"]),
        ("Leo Romano",      "leo.romano@example.com",      ["React","Next.js","TypeScript"]),
    ]
    stages = ["sourced","sourced","screening","screening","interview","interview",
              "offer","rejected","hired","screening","interview","sourced"]

    flow = ["sourced","screening","interview","offer","hired"]
    rng = random.Random(42)

    for i, (name, email, skills) in enumerate(candidate_defs):
        vac = vacancies[i % len(vacancies)]
        stage = stages[i]
        cand = db.create_candidate({
            "name": name,
            "email": email,
            "phone": f"+1 {rng.randint(200, 999)}-{rng.randint(1000, 9999)}",
            "location": vac["location"],
            "headline": _headline_for(skills),
            "skills": skills,
            "experience_years": 2 + (i % 8),
            "vacancy_id": vac["id"],
            "source": "LinkedIn" if i % 2 else "Referral",
            "rating": (i % 5) + 1,
            "stage": "sourced",
        })
        _backdate(cand["id"], stage, now, flow, rng)
        _force_stage(cand["id"], stage)

    cands_for_interviews = db.list_candidates()[:5]
    for i, c in enumerate(cands_for_interviews):
        db.create_interview({
            "candidate_id": c["id"],
            "interviewer": ["Priya Raman", "Alex Hughes", "Rahul Nair", "Sara Owens"][i % 4],
            "type": ["Screening", "Technical", "Culture", "Final"][i % 4],
            "date": _iso(now + timedelta(hours=(i + 1) * 20)),
            "status": "Scheduled",
        })

    return True


def _headline_for(skills: list[str]) -> str:
    joined = " ".join(skills).lower()
    if any(t in joined for t in ("figma", "ux", "ui", "product")):
        return "Senior Product Designer"
    if any(t in joined for t in ("torch", "tensor", "scikit")):
        return "Machine Learning Engineer"
    if any(t in joined for t in ("sourcing", "ats", "greenhouse")):
        return "Talent Acquisition Partner"
    if any(t in joined for t in ("react", "next", "typescript")):
        return "Full-stack Engineer"
    return "Senior Backend Engineer"


def _backdate(candidate_id: str, stage: str, now: datetime, flow: list[str], rng: random.Random) -> None:
    """Rewrite candidate history to create realistic time-in-stage data."""
    with db.connect() as c:
        c.execute("DELETE FROM candidate_history WHERE candidate_id = ?", (candidate_id,))
        if stage in flow:
            idx = flow.index(stage)
            for i in range(idx + 1):
                offset = (idx - i + 1) * (3 + rng.random() * 5)
                at = _iso(now - timedelta(days=offset))
                frm = flow[i - 1] if i else None
                c.execute(
                    "INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
                    (candidate_id, flow[i], frm, at),
                )
        elif stage == "rejected":
            c.execute("INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
                      (candidate_id, "sourced", None, _iso(now - timedelta(days=12))))
            c.execute("INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
                      (candidate_id, "screening", "sourced", _iso(now - timedelta(days=9))))
            c.execute("INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
                      (candidate_id, "rejected", "screening", _iso(now - timedelta(days=4))))


def _force_stage(candidate_id: str, stage: str) -> None:
    with db.connect() as c:
        c.execute("UPDATE candidates SET stage = ? WHERE id = ?", (stage, candidate_id))
