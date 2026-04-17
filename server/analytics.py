"""Dashboard / reports aggregations computed from the raw DB rows."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import db


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_between(a: str | None, b: datetime | None = None) -> int:
    start = _parse_iso(a)
    if not start:
        return 0
    end = b or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds() // 86400))


def average_tat_by_stage(candidates: list[dict], histories: dict[str, list[dict]]) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)
    now = datetime.now(timezone.utc)
    for c in candidates:
        h = histories.get(c["id"], [])
        for i, cur in enumerate(h):
            nxt = h[i + 1] if i + 1 < len(h) else None
            start = _parse_iso(cur["at"])
            end = _parse_iso(nxt["at"]) if nxt else now
            if not start or not end:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            days = (end - start).total_seconds() / 86400
            totals[cur["stage"]].append(days)
    return {s["id"]: round(sum(totals[s["id"]]) / len(totals[s["id"]]), 1) if totals[s["id"]] else 0
            for s in db.STAGES}


def aging_buckets(candidates: list[dict], histories: dict[str, list[dict]]) -> dict[str, int]:
    result = {"<=3": 0, "4-7": 0, "8-14": 0, "15-30": 0, ">30": 0}
    for c in candidates:
        if c["stage"] in ("hired", "rejected"):
            continue
        h = histories.get(c["id"], [])
        last_change = h[-1]["at"] if h else c["created_at"]
        d = days_between(last_change)
        if d <= 3:
            result["<=3"] += 1
        elif d <= 7:
            result["4-7"] += 1
        elif d <= 14:
            result["8-14"] += 1
        elif d <= 30:
            result["15-30"] += 1
        else:
            result[">30"] += 1
    return result


def funnel_counts(candidates: list[dict]) -> dict[str, int]:
    counter = Counter(c["stage"] for c in candidates)
    return {s["id"]: counter.get(s["id"], 0) for s in db.STAGES}


def avg_time_to_hire(candidates: list[dict], histories: dict[str, list[dict]]) -> int:
    hired = [c for c in candidates if c["stage"] == "hired"]
    if not hired:
        return 0
    totals: list[float] = []
    for c in hired:
        h = histories.get(c["id"], [])
        if not h:
            continue
        start = _parse_iso(h[0]["at"]) or _parse_iso(c["created_at"])
        end = _parse_iso(h[-1]["at"]) or _parse_iso(c["updated_at"])
        if start and end:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            totals.append((end - start).total_seconds() / 86400)
    if not totals:
        return 0
    return round(sum(totals) / len(totals))


def same_month(iso: str | None, ref: datetime | None = None) -> bool:
    d = _parse_iso(iso)
    if not d:
        return False
    ref = ref or datetime.now(timezone.utc)
    return d.month == ref.month and d.year == ref.year


def source_breakdown(candidates: list[dict]) -> list[tuple[str, int]]:
    counter = Counter((c.get("source") or "Unknown") for c in candidates)
    return counter.most_common()


def conversion_pct(candidates: list[dict], histories: dict[str, list[dict]]) -> int:
    passed_screen = sum(1 for c in candidates if any(h["stage"] == "screening" for h in histories.get(c["id"], [])))
    reached_offer = sum(1 for c in candidates if c["stage"] in ("offer", "hired"))
    if not passed_screen:
        return 0
    return round(reached_offer / passed_screen * 100)
