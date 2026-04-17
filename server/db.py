"""SQLite data layer for the recruitment tracker."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).parent / "data.db"

STAGES = [
    {"id": "sourced",   "label": "Sourced",   "sla": 3},
    {"id": "screening", "label": "Screening", "sla": 5},
    {"id": "interview", "label": "Interview", "sla": 10},
    {"id": "offer",     "label": "Offer",     "sla": 7},
    {"id": "hired",     "label": "Hired",     "sla": 0},
    {"id": "rejected",  "label": "Rejected",  "sla": 0},
]
STAGE_IDS = [s["id"] for s in STAGES]
STAGE_LABEL = {s["id"]: s["label"] for s in STAGES}
STAGE_SLA = {s["id"]: s["sla"] for s in STAGES}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT,
    location TEXT,
    hiring_manager TEXT,
    openings INTEGER DEFAULT 1,
    priority TEXT DEFAULT 'Medium',
    status TEXT DEFAULT 'Open',
    target_close TEXT,
    description TEXT,
    skills TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    location TEXT,
    headline TEXT,
    skills TEXT DEFAULT '[]',
    experience_years INTEGER,
    education TEXT DEFAULT '[]',
    experience TEXT DEFAULT '[]',
    source TEXT,
    vacancy_id TEXT,
    stage TEXT DEFAULT 'sourced',
    rating INTEGER DEFAULT 0,
    raw_cv TEXT,
    file_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(vacancy_id) REFERENCES vacancies(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS candidate_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    from_stage TEXT,
    at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    interviewer TEXT,
    type TEXT,
    date TEXT,
    status TEXT DEFAULT 'Scheduled',
    feedback TEXT,
    rating INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    meta TEXT DEFAULT '{}',
    ts TEXT NOT NULL
);
"""


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)


# ----- Row helpers -----

def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("skills", "education", "experience"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k] or "[]")
            except json.JSONDecodeError:
                d[k] = []
    return d


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [_row_to_dict(r) for r in rows]


# ----- Activity -----

def log_activity(conn: sqlite3.Connection, type_: str, message: str, meta: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO activity (type, message, meta, ts) VALUES (?, ?, ?, ?)",
        (type_, message, json.dumps(meta or {}), now_iso()),
    )


def list_activity(limit: int = 20) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta") or "{}")
        except json.JSONDecodeError:
            d["meta"] = {}
        out.append(d)
    return out


# ----- Vacancies -----

def list_vacancies(status: str | None = None) -> list[dict]:
    with connect() as c:
        if status:
            rows = c.execute("SELECT * FROM vacancies WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM vacancies ORDER BY created_at DESC").fetchall()
    return _rows(rows)


def get_vacancy(vid: str) -> dict | None:
    with connect() as c:
        return _row_to_dict(c.execute("SELECT * FROM vacancies WHERE id = ?", (vid,)).fetchone())


def create_vacancy(data: dict) -> dict:
    vid = new_id("vac")
    with connect() as c:
        c.execute(
            """INSERT INTO vacancies (id, title, department, location, hiring_manager, openings,
                                       priority, status, target_close, description, skills, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                vid,
                (data.get("title") or "Untitled role").strip(),
                data.get("department") or "General",
                data.get("location") or "Remote",
                data.get("hiring_manager") or "",
                int(data.get("openings") or 1),
                data.get("priority") or "Medium",
                data.get("status") or "Open",
                data.get("target_close") or "",
                data.get("description") or "",
                json.dumps(data.get("skills") or []),
                now_iso(),
            ),
        )
        log_activity(c, "vacancy.created", f'Vacancy "{data.get("title")}" opened')
    return get_vacancy(vid)


def update_vacancy(vid: str, data: dict) -> None:
    with connect() as c:
        c.execute(
            """UPDATE vacancies
               SET title=?, department=?, location=?, hiring_manager=?, openings=?, priority=?,
                   status=?, target_close=?, description=?, skills=?
               WHERE id = ?""",
            (
                data.get("title"),
                data.get("department"),
                data.get("location"),
                data.get("hiring_manager"),
                int(data.get("openings") or 1),
                data.get("priority"),
                data.get("status"),
                data.get("target_close"),
                data.get("description"),
                json.dumps(data.get("skills") or []),
                vid,
            ),
        )


def delete_vacancy(vid: str) -> None:
    with connect() as c:
        c.execute("UPDATE candidates SET vacancy_id = NULL WHERE vacancy_id = ?", (vid,))
        c.execute("DELETE FROM vacancies WHERE id = ?", (vid,))


# ----- Candidates -----

def list_candidates(stage: str | None = None, vacancy_id: str | None = None, q: str | None = None) -> list[dict]:
    sql = "SELECT * FROM candidates WHERE 1=1"
    params: list[Any] = []
    if stage and stage != "all":
        sql += " AND stage = ?"; params.append(stage)
    if vacancy_id and vacancy_id != "all":
        sql += " AND vacancy_id = ?"; params.append(vacancy_id)
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(headline) LIKE ? OR LOWER(skills) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like, like, like])
    sql += " ORDER BY created_at DESC"
    with connect() as c:
        rows = c.execute(sql, params).fetchall()
    return _rows(rows)


def get_candidate(cid: str) -> dict | None:
    with connect() as c:
        cand = _row_to_dict(c.execute("SELECT * FROM candidates WHERE id = ?", (cid,)).fetchone())
        if not cand:
            return None
        cand["history"] = [dict(r) for r in c.execute(
            "SELECT stage, from_stage, at FROM candidate_history WHERE candidate_id = ? ORDER BY at ASC",
            (cid,)).fetchall()]
        cand["interviews"] = [dict(r) for r in c.execute(
            "SELECT * FROM interviews WHERE candidate_id = ? ORDER BY date DESC", (cid,)).fetchall()]
    return cand


def get_histories_for(candidate_ids: list[str]) -> dict[str, list[dict]]:
    if not candidate_ids:
        return {}
    placeholders = ",".join("?" for _ in candidate_ids)
    with connect() as c:
        rows = c.execute(
            f"SELECT candidate_id, stage, from_stage, at FROM candidate_history WHERE candidate_id IN ({placeholders}) ORDER BY at ASC",
            candidate_ids,
        ).fetchall()
    out: dict[str, list[dict]] = {cid: [] for cid in candidate_ids}
    for r in rows:
        out[r["candidate_id"]].append({"stage": r["stage"], "from_stage": r["from_stage"], "at": r["at"]})
    return out


def create_candidate(data: dict) -> dict:
    cid = new_id("cand")
    stage = data.get("stage") or "sourced"
    ts = now_iso()
    with connect() as c:
        c.execute(
            """INSERT INTO candidates (id, name, email, phone, location, headline, skills,
                                       experience_years, education, experience, source, vacancy_id,
                                       stage, rating, raw_cv, file_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                (data.get("name") or "Unnamed Candidate").strip(),
                data.get("email") or "",
                data.get("phone") or "",
                data.get("location") or "",
                data.get("headline") or "",
                json.dumps(data.get("skills") or []),
                data.get("experience_years"),
                json.dumps(data.get("education") or []),
                json.dumps(data.get("experience") or []),
                data.get("source") or "CV Upload",
                data.get("vacancy_id") or None,
                stage,
                int(data.get("rating") or 0),
                data.get("raw_cv") or "",
                data.get("file_name") or "",
                ts, ts,
            ),
        )
        c.execute(
            "INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
            (cid, stage, None, ts),
        )
        log_activity(c, "candidate.created", f'Candidate "{data.get("name")}" added', {"candidate_id": cid})
    return get_candidate(cid)


def update_candidate(cid: str, data: dict) -> None:
    with connect() as c:
        c.execute(
            """UPDATE candidates
               SET name=?, email=?, phone=?, location=?, headline=?, skills=?, experience_years=?,
                   source=?, vacancy_id=?, rating=?, updated_at=?
               WHERE id=?""",
            (
                data.get("name"),
                data.get("email"),
                data.get("phone"),
                data.get("location"),
                data.get("headline"),
                json.dumps(data.get("skills") or []),
                data.get("experience_years"),
                data.get("source"),
                data.get("vacancy_id") or None,
                int(data.get("rating") or 0),
                now_iso(),
                cid,
            ),
        )


def move_candidate(cid: str, to_stage: str) -> None:
    if to_stage not in STAGE_IDS:
        return
    with connect() as c:
        row = c.execute("SELECT stage, name FROM candidates WHERE id = ?", (cid,)).fetchone()
        if not row or row["stage"] == to_stage:
            return
        from_stage = row["stage"]
        ts = now_iso()
        c.execute("UPDATE candidates SET stage = ?, updated_at = ? WHERE id = ?", (to_stage, ts, cid))
        c.execute(
            "INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
            (cid, to_stage, from_stage, ts),
        )
        log_activity(c, "candidate.moved", f'{row["name"]} → {STAGE_LABEL.get(to_stage, to_stage)}', {"candidate_id": cid})


def delete_candidate(cid: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM candidates WHERE id = ?", (cid,))


# ----- Interviews -----

def list_interviews() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM interviews ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]


def get_interview(iid: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM interviews WHERE id = ?", (iid,)).fetchone()
    return dict(r) if r else None


def create_interview(data: dict) -> dict:
    iid = new_id("int")
    with connect() as c:
        c.execute(
            """INSERT INTO interviews (id, candidate_id, interviewer, type, date, status, feedback, rating, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                iid,
                data["candidate_id"],
                data.get("interviewer") or "",
                data.get("type") or "Technical",
                data.get("date") or now_iso(),
                data.get("status") or "Scheduled",
                data.get("feedback") or "",
                int(data.get("rating") or 0),
                now_iso(),
            ),
        )
        name_row = c.execute("SELECT name FROM candidates WHERE id = ?", (data["candidate_id"],)).fetchone()
        name = name_row["name"] if name_row else ""
        msg = f"Interview scheduled with {name}" if name else "Interview scheduled"
        log_activity(c, "interview.scheduled", msg)
    return get_interview(iid)


def update_interview(iid: str, data: dict) -> None:
    with connect() as c:
        c.execute(
            """UPDATE interviews
               SET interviewer=?, type=?, date=?, status=?, feedback=?, rating=?
               WHERE id=?""",
            (
                data.get("interviewer"),
                data.get("type"),
                data.get("date"),
                data.get("status"),
                data.get("feedback"),
                int(data.get("rating") or 0),
                iid,
            ),
        )


def delete_interview(iid: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM interviews WHERE id = ?", (iid,))


# ----- Aggregates -----

def all_state() -> dict:
    """Full export of DB for JSON round-tripping."""
    with connect() as c:
        return {
            "vacancies": _rows(c.execute("SELECT * FROM vacancies").fetchall()),
            "candidates": _rows(c.execute("SELECT * FROM candidates").fetchall()),
            "history": [dict(r) for r in c.execute("SELECT * FROM candidate_history").fetchall()],
            "interviews": [dict(r) for r in c.execute("SELECT * FROM interviews").fetchall()],
            "activity": list_activity(1000),
        }


def reset_all() -> None:
    with connect() as c:
        for t in ("candidate_history", "interviews", "candidates", "vacancies", "activity"):
            c.execute(f"DELETE FROM {t}")


def import_state(payload: dict) -> None:
    reset_all()
    with connect() as c:
        for v in payload.get("vacancies", []):
            c.execute(
                """INSERT INTO vacancies (id, title, department, location, hiring_manager, openings,
                                           priority, status, target_close, description, skills, created_at)
                   VALUES (:id, :title, :department, :location, :hiring_manager, :openings,
                           :priority, :status, :target_close, :description, :skills, :created_at)""",
                {**v, "skills": json.dumps(v.get("skills") or [])},
            )
        for cand in payload.get("candidates", []):
            c.execute(
                """INSERT INTO candidates (id, name, email, phone, location, headline, skills,
                                            experience_years, education, experience, source, vacancy_id,
                                            stage, rating, raw_cv, file_name, created_at, updated_at)
                   VALUES (:id, :name, :email, :phone, :location, :headline, :skills,
                           :experience_years, :education, :experience, :source, :vacancy_id,
                           :stage, :rating, :raw_cv, :file_name, :created_at, :updated_at)""",
                {
                    **cand,
                    "skills": json.dumps(cand.get("skills") or []),
                    "education": json.dumps(cand.get("education") or []),
                    "experience": json.dumps(cand.get("experience") or []),
                },
            )
        for h in payload.get("history", []):
            c.execute(
                "INSERT INTO candidate_history (candidate_id, stage, from_stage, at) VALUES (?, ?, ?, ?)",
                (h["candidate_id"], h["stage"], h.get("from_stage"), h["at"]),
            )
        for i in payload.get("interviews", []):
            c.execute(
                """INSERT INTO interviews (id, candidate_id, interviewer, type, date, status, feedback, rating, created_at)
                   VALUES (:id, :candidate_id, :interviewer, :type, :date, :status, :feedback, :rating, :created_at)""",
                i,
            )
