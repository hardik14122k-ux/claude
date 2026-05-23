"""Regression tests for the CV parser ported from the talenttrack prototype."""
from eden.recruitment import cv_parser


def test_parses_email_phone_and_skills():
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
    assert "PostgreSQL" in out["skills"]
    assert "AWS" in out["skills"]
    assert out["name"]
    assert out["phone"]


def test_falls_back_to_email_local_for_name():
    text = "alex.kim@example.com\nSome unrelated text here.\n"
    out = cv_parser.parse_cv(text)
    assert out["email"] == "alex.kim@example.com"
    assert "Alex" in out["name"]


def test_estimates_years_from_explicit_phrase():
    text = "Backend engineer with 7+ years of experience in distributed systems."
    out = cv_parser.parse_cv(text)
    assert out["experience_years"] == 7
