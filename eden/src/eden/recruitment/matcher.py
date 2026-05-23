"""JD ↔ CV matcher.

Given a candidate (parsed CV fields + raw CV text) and a vacancy (JD description,
required skills, optional minimum years), compute a weighted score plus a
breakdown showing matched / missing skills and overall keyword overlap.

The score is intentionally simple and explainable:

  total = 0.60 · skill_match + 0.30 · keyword_match + 0.10 · experience_fit

Each component is 0–1, then scaled to 0–100.
"""
from __future__ import annotations

import re
from typing import Iterable

STOPWORDS = {
    "the","a","an","and","or","of","in","to","for","with","on","at","by","as","is","are","was",
    "were","be","been","being","we","you","they","our","your","their","this","that","these",
    "those","it","its","from","will","can","have","has","had","not","no","but","if","so",
    "such","any","all","each","other","than","then","when","while","who","whom","which","what",
    "about","into","over","under","per","via","across","within","without",
    "experience","experienced","years","year","work","working","team","teams","role","roles",
    "project","projects","responsible","responsibilities","requirements","required","ability",
    "strong","solid","excellent","good","great","proven","preferred","must","should","would",
    "ideal","candidate","candidates","plus","including","etc","using","use","uses","used",
    "well","also","new","looking","seek","seeking","job","position","opportunity",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./]{1,}")


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {w for w in (m.group(0).lower() for m in WORD_RE.finditer(text))
            if len(w) >= 3 and w not in STOPWORDS}


def _normalize_skills(skills: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for s in skills or []:
        if not s:
            continue
        norm = s.strip()
        key = norm.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(norm)
    return out


def required_years_from_jd(jd_text: str) -> int | None:
    if not jd_text:
        return None
    m = re.search(r"(\d{1,2})\+?\s*(?:-\s*\d{1,2}\s*)?years?\s+(?:of\s+)?(?:relevant\s+|professional\s+)?experience", jd_text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def score(
    candidate: dict,
    vacancy: dict,
) -> dict:
    cv_text = " ".join([
        candidate.get("headline") or "",
        " ".join(candidate.get("skills") or []),
        candidate.get("raw_cv") or "",
    ])
    jd_text = " ".join([
        vacancy.get("title") or "",
        vacancy.get("description") or "",
        " ".join(vacancy.get("skills") or []),
    ])

    cv_lower = cv_text.lower()
    jd_skills = _normalize_skills(vacancy.get("skills") or [])
    cv_skills = _normalize_skills(candidate.get("skills") or [])
    cv_skill_lookup = {s.lower() for s in cv_skills}

    matched, missing = [], []
    for s in jd_skills:
        s_low = s.lower()
        if s_low in cv_skill_lookup or re.search(rf"(?:^|[^a-z0-9+#]){re.escape(s_low)}(?:$|[^a-z0-9+#])", cv_lower):
            matched.append(s)
        else:
            missing.append(s)

    total_jd_skills = len(jd_skills) or 0
    if total_jd_skills:
        skill_match = len(matched) / total_jd_skills
    else:
        jd_tokens = _tokens(jd_text)
        cv_tokens = _tokens(cv_text)
        skill_match = len(jd_tokens & cv_tokens) / max(1, len(jd_tokens))

    jd_tokens = _tokens(jd_text)
    cv_tokens = _tokens(cv_text)
    keyword_match = len(jd_tokens & cv_tokens) / max(1, len(jd_tokens))

    req_years = required_years_from_jd(vacancy.get("description") or "")
    cand_years = candidate.get("experience_years")
    if req_years is None:
        experience_fit = 1.0
    elif cand_years is None:
        experience_fit = 0.5
    else:
        experience_fit = min(1.0, cand_years / req_years) if req_years > 0 else 1.0

    total = round((skill_match * 0.6 + keyword_match * 0.3 + experience_fit * 0.1) * 100)

    return {
        "total": total,
        "skill_match": round(skill_match * 100),
        "keyword_match": round(keyword_match * 100),
        "experience_fit": round(experience_fit * 100),
        "matched_skills": matched,
        "missing_skills": missing,
        "required_years": req_years,
        "candidate_years": cand_years,
    }


def rank_candidate_against_all(candidate: dict, vacancies: list[dict]) -> list[dict]:
    """Return vacancies annotated with match scores, highest total first."""
    ranked = []
    for v in vacancies:
        if not (v.get("description") or v.get("skills")):
            continue
        ranked.append({"vacancy": v, "match": score(candidate, v)})
    ranked.sort(key=lambda r: r["match"]["total"], reverse=True)
    return ranked


def rank_candidates_against_vacancy(candidates: list[dict], vacancy: dict) -> list[dict]:
    """Return candidates annotated with match scores for a single vacancy."""
    ranked = []
    for c in candidates:
        ranked.append({"candidate": c, "match": score(c, vacancy)})
    ranked.sort(key=lambda r: r["match"]["total"], reverse=True)
    return ranked
