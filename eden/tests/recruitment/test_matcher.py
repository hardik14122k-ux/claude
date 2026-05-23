"""Regression tests for the JD <-> CV matcher ported from the talenttrack prototype."""
from eden.recruitment import matcher


def test_score_matches_required_skills():
    cand = {"skills": ["Python", "AWS"], "headline": "Backend", "raw_cv": "Python AWS Linux"}
    vac = {"title": "Backend", "skills": ["Python", "AWS"], "description": "5 years experience needed"}
    s = matcher.score(cand, vac)
    assert 0 <= s["total"] <= 100
    assert "Python" in s["matched_skills"]
    assert "AWS" in s["matched_skills"]
    assert s["missing_skills"] == []


def test_score_reports_missing_skills():
    cand = {"skills": ["Python"], "raw_cv": "Python"}
    vac = {"skills": ["Python", "Kubernetes"], "description": ""}
    s = matcher.score(cand, vac)
    assert s["matched_skills"] == ["Python"]
    assert s["missing_skills"] == ["Kubernetes"]


def test_required_years_from_jd_text():
    assert matcher.required_years_from_jd("5+ years of experience required") == 5
    assert matcher.required_years_from_jd("no number here") is None


def test_rank_candidates_against_vacancy_orders_by_total():
    vac = {"skills": ["Python", "AWS"], "description": ""}
    weak = {"skills": ["Python"], "raw_cv": "Python"}
    strong = {"skills": ["Python", "AWS"], "raw_cv": "Python AWS"}
    ranked = matcher.rank_candidates_against_vacancy([weak, strong], vac)
    assert ranked[0]["candidate"] is strong
    assert ranked[0]["match"]["total"] >= ranked[1]["match"]["total"]
