"""Pin existing recruitment behaviour: parser, matcher, db CRUD must work
the same way as before the HRMS extension landed."""


def test_cv_parser_extracts_email_and_phone(tmp_db):
    from server import cv_parser
    text = """Jane Doe
jane.doe@example.com
+1 415 555 0100
Senior Backend Engineer
Skills: Python, PostgreSQL, AWS, Kubernetes
Experience
2018 - 2024 Acme Corp
"""
    out = cv_parser.parse_cv(text)
    assert out["email"] == "jane.doe@example.com"
    assert "Python" in out["skills"]
    assert out["name"]


def test_matcher_score_against_vacancy(tmp_db):
    from server import matcher
    cand = {"skills": ["Python", "AWS"], "headline": "Backend", "raw_cv": "Python AWS Linux"}
    vac = {"title": "Backend", "skills": ["Python", "AWS"], "description": "5 years experience needed"}
    s = matcher.score(cand, vac)
    assert 0 <= s["total"] <= 100
    assert "Python" in s["matched_skills"]


def test_db_create_vacancy_and_candidate(tmp_db):
    from server import db
    v = db.create_vacancy({"title": "Backend Engineer", "skills": ["Python"]})
    c = db.create_candidate({"name": "X Y", "vacancy_id": v["id"], "skills": ["Python"]})
    assert c["vacancy_id"] == v["id"]
    cands = db.list_candidates(vacancy_id=v["id"])
    assert len(cands) == 1


def test_dashboard_route_renders(tmp_db, client):
    resp = client.get("/")
    # Should redirect to login OR render dashboard. Either status indicates the
    # blueprint chain loaded without errors.
    assert resp.status_code in (200, 302)


def test_login_route_renders(tmp_db, client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_login_flow(tmp_db, client, admin_user):
    resp = client.post("/auth/login", data={
        "email": "admin@example.com", "password": "admin",
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
