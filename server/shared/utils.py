"""Shared utilities used across all HRMS modules.

Extracted from db.py (now_iso, new_id) and analytics.py (_parse_iso, days_between)
so every module can import from one place without circular dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_between(a: str | None, b: datetime | None = None) -> int:
    start = parse_iso(a)
    if not start:
        return 0
    end = b or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds() // 86400))


def same_month(iso: str | None, ref: datetime | None = None) -> bool:
    d = parse_iso(iso)
    if not d:
        return False
    ref = ref or datetime.now(timezone.utc)
    return d.month == ref.month and d.year == ref.year


def fiscal_year(dt: datetime | None = None) -> int:
    """Return the Indian fiscal year start year. Apr 2024–Mar 2025 → 2024."""
    dt = dt or datetime.now(timezone.utc)
    return dt.year if dt.month >= 4 else dt.year - 1
