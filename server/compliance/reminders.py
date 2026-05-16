"""Statutory deadline reminder calendar.

Standard monthly Indian statutory due dates:
  - PF (ECR): 15th of next month
  - ESI:      15th of next month
  - PT:       varies by state (typically 10th–21st of next month)
  - TDS:      7th of next month (for prior-month deductions)
  - LWF:      half-yearly (Jun 30, Dec 31) for most states
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from .. import db as recruitment_db
from ..shared.utils import new_id, now_iso


STANDARD_TEMPLATES = [
    ("PF (EPF) — ECR filing & remittance", "pf",  15, "monthly"),
    ("ESI contribution remittance",        "esi", 15, "monthly"),
    ("Professional Tax remittance",        "pt",  21, "monthly"),
    ("TDS remittance (Section 192)",       "tds",  7, "monthly"),
]


def seed_for_year(tenant_id: str, year: int) -> int:
    """Pre-populate next-year reminders. Returns rows added."""
    added = 0
    with recruitment_db.connect() as c:
        for month in range(1, 13):
            for title, category, day, _ in STANDARD_TEMPLATES:
                last_day = monthrange(year, month)[1]
                due = date(year, month, min(day, last_day)).isoformat()
                rid = new_id("rmd")
                cur = c.execute(
                    """INSERT INTO compliance_reminders
                        (id, tenant_id, title, category, due_date, recurrence,
                         description, status, created_at)
                       VALUES (?, ?, ?, ?, ?, 'monthly', ?, 'open', ?)""",
                    (rid, tenant_id, f"{title} — {month:02d}/{year}", category, due,
                     f"Standard monthly compliance: {title}", now_iso()),
                )
                added += cur.rowcount or 0
    return added


def list_open(tenant_id: str, days_ahead: int = 60) -> list[dict]:
    cutoff = (date.today().toordinal() + days_ahead)
    with recruitment_db.connect() as c:
        rows = c.execute(
            """SELECT * FROM compliance_reminders
               WHERE tenant_id = ? AND status = 'open'
               ORDER BY due_date ASC""",
            (tenant_id,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            due = date.fromisoformat(r["due_date"])
        except ValueError:
            continue
        if due.toordinal() <= cutoff:
            d = dict(r)
            d["days_to_due"] = due.toordinal() - date.today().toordinal()
            out.append(d)
    return out


def mark_done(tenant_id: str, rid: str) -> bool:
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE compliance_reminders SET status='completed', completed_at=? "
            "WHERE tenant_id=? AND id=?",
            (now_iso(), tenant_id, rid),
        )
    return True
