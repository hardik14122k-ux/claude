"""TalentTrack — Flask recruitment tracker with CV parsing + JD matching."""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file,
    session, url_for,
)

from . import analytics, cv_parser, db, matcher, seed

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"  # only used for flash + ephemeral upload tokens
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB CV uploads

# Ephemeral parsed-CV cache keyed by short tokens. Simple dict is fine for dev;
# sessions would bloat for large CV text. Clears automatically on restart.
PARSED_CACHE: dict[str, dict] = {}


@app.before_request
def _ensure_db() -> None:
    db.init_db()


def _csv(raw: str) -> list[str]:
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def _iso(local: str) -> str:
    if not local:
        return ""
    try:
        return datetime.fromisoformat(local).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return local


# ---------------- Dashboard ----------------

@app.route("/")
def dashboard():
    vacancies = db.list_vacancies()
    candidates = db.list_candidates()
    histories = db.get_histories_for([c["id"] for c in candidates])
    open_vacancies = [v for v in vacancies if v.get("status") != "Closed"]

    return render_template(
        "dashboard.html",
        stages=db.STAGES,
        open_vacancies=open_vacancies,
        total_openings=sum(v.get("openings") or 1 for v in open_vacancies),
        active_candidates=sum(1 for c in candidates if c["stage"] not in ("hired", "rejected")),
        total_candidates=len(candidates),
        pending_offers=sum(1 for c in candidates if c["stage"] == "offer"),
        hired_this_month=sum(1 for c in candidates if c["stage"] == "hired" and analytics.same_month(c["updated_at"])),
        total_hired=sum(1 for c in candidates if c["stage"] == "hired"),
        avg_time_to_hire=analytics.avg_time_to_hire(candidates, histories),
        funnel=analytics.funnel_counts(candidates),
        funnel_max=max([1] + list(analytics.funnel_counts(candidates).values())),
        aging=analytics.aging_buckets(candidates, histories),
        tat=analytics.average_tat_by_stage(candidates, histories),
        vacancy_age={v["id"]: analytics.days_between(v["created_at"]) for v in vacancies},
        activity=db.list_activity(10),
    )


# ---------------- Vacancies ----------------

@app.route("/vacancies")
def vacancies_list():
    vacancies = db.list_vacancies()
    candidates = db.list_candidates()
    return render_template(
        "vacancies.html",
        vacancies=vacancies,
        candidate_counts={v["id"]: sum(1 for c in candidates if c.get("vacancy_id") == v["id"]) for v in vacancies},
        vacancy_age={v["id"]: analytics.days_between(v["created_at"]) for v in vacancies},
    )


@app.route("/vacancies/new", methods=["GET", "POST"])
def vacancy_new():
    if request.method == "POST":
        db.create_vacancy({
            "title": request.form.get("title", ""),
            "department": request.form.get("department", ""),
            "location": request.form.get("location", ""),
            "hiring_manager": request.form.get("hiring_manager", ""),
            "openings": request.form.get("openings", 1),
            "priority": request.form.get("priority", "Medium"),
            "status": request.form.get("status", "Open"),
            "target_close": _iso(request.form.get("target_close", "")),
            "description": request.form.get("description", ""),
            "skills": _csv(request.form.get("skills", "")),
        })
        flash("Vacancy created", "ok")
        return redirect(url_for("vacancies_list"))
    return render_template("vacancy_form.html", vacancy=None)


@app.route("/vacancies/<vid>/edit", methods=["GET", "POST"])
def vacancy_edit(vid: str):
    vacancy = db.get_vacancy(vid)
    if not vacancy:
        abort(404)
    if request.method == "POST":
        db.update_vacancy(vid, {
            "title": request.form.get("title"),
            "department": request.form.get("department"),
            "location": request.form.get("location"),
            "hiring_manager": request.form.get("hiring_manager"),
            "openings": request.form.get("openings", 1),
            "priority": request.form.get("priority"),
            "status": request.form.get("status"),
            "target_close": _iso(request.form.get("target_close", "")),
            "description": request.form.get("description"),
            "skills": _csv(request.form.get("skills", "")),
        })
        flash("Vacancy updated", "ok")
        return redirect(url_for("vacancies_list"))
    return render_template("vacancy_form.html", vacancy=vacancy)


@app.route("/vacancies/<vid>/delete", methods=["POST"])
def vacancy_delete(vid: str):
    db.delete_vacancy(vid)
    flash("Vacancy deleted", "ok")
    return redirect(url_for("vacancies_list"))


@app.route("/vacancies/<vid>/match")
def vacancy_match(vid: str):
    vacancy = db.get_vacancy(vid)
    if not vacancy:
        abort(404)
    candidates = db.list_candidates()
    ranked = matcher.rank_candidates_against_vacancy(candidates, vacancy)
    return render_template("vacancy_match.html", vacancy=vacancy, results=ranked)


# ---------------- Candidates ----------------

@app.route("/candidates")
def candidates_list():
    q = request.args.get("q", "").strip()
    stage_filter = request.args.get("stage", "all")
    vacancy_filter = request.args.get("vacancy", "all")
    candidates = db.list_candidates(stage=stage_filter, vacancy_id=vacancy_filter, q=q or None)
    vacancies = db.list_vacancies()
    histories = db.get_histories_for([c["id"] for c in candidates])
    days_in_stage = {}
    for c in candidates:
        h = histories.get(c["id"], [])
        last = h[-1]["at"] if h else c["created_at"]
        days_in_stage[c["id"]] = analytics.days_between(last)
    return render_template(
        "candidates.html",
        candidates=candidates,
        vacancies=vacancies,
        vacancy_titles={v["id"]: v["title"] for v in vacancies},
        stages=db.STAGES,
        stage_filter=stage_filter,
        vacancy_filter=vacancy_filter,
        q=q,
        days_in_stage=days_in_stage,
    )


@app.route("/candidates/new", methods=["GET", "POST"])
def candidate_new():
    if request.method == "POST":
        _save_candidate_from_form()
        flash("Candidate added", "ok")
        return redirect(url_for("candidates_list"))
    return render_template("candidate_form.html", candidate=None, vacancies=db.list_vacancies())


@app.route("/candidates/<cid>/edit", methods=["GET", "POST"])
def candidate_edit(cid: str):
    cand = db.get_candidate(cid)
    if not cand:
        abort(404)
    if request.method == "POST":
        db.update_candidate(cid, {
            "name": request.form.get("name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "location": request.form.get("location"),
            "headline": request.form.get("headline"),
            "experience_years": int(request.form.get("experience_years") or 0) or None,
            "source": request.form.get("source"),
            "vacancy_id": request.form.get("vacancy_id") or None,
            "rating": request.form.get("rating", 0),
            "skills": _csv(request.form.get("skills", "")),
        })
        flash("Candidate updated", "ok")
        return redirect(url_for("candidate_detail", cid=cid))
    return render_template("candidate_form.html", candidate=cand, vacancies=db.list_vacancies())


def _save_candidate_from_form(extra: dict | None = None) -> dict:
    data = {
        "name": request.form.get("name"),
        "email": request.form.get("email"),
        "phone": request.form.get("phone"),
        "location": request.form.get("location"),
        "headline": request.form.get("headline"),
        "experience_years": int(request.form.get("experience_years") or 0) or None,
        "source": request.form.get("source") or "CV Upload",
        "vacancy_id": request.form.get("vacancy_id") or None,
        "skills": _csv(request.form.get("skills", "")),
        "stage": "sourced",
    }
    if extra:
        data.update(extra)
    return db.create_candidate(data)


@app.route("/candidates/<cid>")
def candidate_detail(cid: str):
    cand = db.get_candidate(cid)
    if not cand:
        abort(404)
    vacancy = db.get_vacancy(cand["vacancy_id"]) if cand.get("vacancy_id") else None
    match = matcher.score(cand, vacancy) if vacancy and (vacancy.get("description") or vacancy.get("skills")) else None
    return render_template(
        "candidate_detail.html",
        candidate=cand,
        vacancy=vacancy,
        vacancy_title=(vacancy["title"] if vacancy else None),
        stage_label=db.STAGE_LABEL.get(cand["stage"], cand["stage"]),
        stages_by_id=db.STAGE_LABEL,
        match=match,
    )


@app.route("/candidates/<cid>/match")
def match_candidate(cid: str):
    cand = db.get_candidate(cid)
    if not cand:
        abort(404)
    results = matcher.rank_candidate_against_all(cand, db.list_vacancies())
    return render_template("match_candidate.html", candidate=cand, results=results)


@app.route("/candidates/<cid>/link", methods=["POST"])
def candidate_link_vacancy(cid: str):
    cand = db.get_candidate(cid)
    if not cand:
        abort(404)
    db.update_candidate(cid, {**cand, "vacancy_id": request.form.get("vacancy_id") or None})
    flash("Linked", "ok")
    return redirect(url_for("candidate_detail", cid=cid))


@app.route("/candidates/<cid>/move", methods=["POST"])
def candidate_move(cid: str):
    db.move_candidate(cid, request.form.get("stage", ""))
    flash("Stage updated", "ok")
    if request.headers.get("Accept") == "application/json" or request.form.get("_xhr"):
        return {"ok": True}
    return redirect(request.referrer or url_for("candidates_list"))


@app.route("/candidates/<cid>/delete", methods=["POST"])
def candidate_delete(cid: str):
    db.delete_candidate(cid)
    flash("Candidate deleted", "ok")
    return redirect(url_for("candidates_list"))


# ---------------- Upload flow ----------------

@app.route("/candidates/upload", methods=["GET", "POST"])
def candidate_upload():
    if request.method == "POST":
        up = request.files.get("cv")
        if not up or up.filename == "":
            flash("Pick a file first", "bad")
            return redirect(url_for("candidate_upload"))
        try:
            text = cv_parser.extract_text(up.stream, up.filename, up.content_type or "")
        except Exception as exc:
            flash(f"Failed to extract text: {exc}", "bad")
            return redirect(url_for("candidate_upload"))
        parsed = cv_parser.parse_cv(text, file_name=up.filename)
        token = uuid.uuid4().hex[:12]
        PARSED_CACHE[token] = parsed
        ranked = matcher.rank_candidate_against_all(parsed, db.list_vacancies())
        match_scores = {r["vacancy"]["id"]: r["match"]["total"] for r in ranked}
        best_match = ranked[0]["vacancy"]["id"] if ranked and ranked[0]["match"]["total"] >= 40 else None
        return render_template(
            "candidate_upload.html",
            parsed=parsed,
            token=token,
            vacancies=db.list_vacancies(),
            ranked_matches=ranked,
            match_scores=match_scores,
            best_match=best_match,
        )
    return render_template("candidate_upload.html", parsed=None)


@app.route("/candidates/upload/save", methods=["POST"])
def candidate_upload_save():
    token = request.form.get("token", "")
    parsed = PARSED_CACHE.pop(token, None)
    if parsed is None:
        flash("Session expired — please re-upload", "bad")
        return redirect(url_for("candidate_upload"))
    cand = _save_candidate_from_form({
        "education": parsed.get("education", []),
        "experience": parsed.get("experience", []),
        "raw_cv": parsed.get("raw_cv", ""),
        "file_name": parsed.get("file_name", ""),
    })
    flash(f"Candidate {cand['name']} saved", "ok")
    return redirect(url_for("candidate_detail", cid=cand["id"]))


# ---------------- Pipeline ----------------

@app.route("/pipeline")
def pipeline():
    vacancy_filter = request.args.get("vacancy", "all")
    candidates = db.list_candidates(vacancy_id=vacancy_filter)
    histories = db.get_histories_for([c["id"] for c in candidates])
    by_stage = {s["id"]: [] for s in db.STAGES}
    days_in_stage: dict[str, int] = {}
    for c in candidates:
        by_stage.setdefault(c["stage"], []).append(c)
        h = histories.get(c["id"], [])
        last = h[-1]["at"] if h else c["created_at"]
        days_in_stage[c["id"]] = analytics.days_between(last)
    return render_template(
        "pipeline.html",
        stages=db.STAGES,
        by_stage=by_stage,
        days_in_stage=days_in_stage,
        vacancies=db.list_vacancies(),
        vacancy_filter=vacancy_filter,
        any_candidates=bool(candidates),
    )


# ---------------- Interviews ----------------

@app.route("/interviews")
def interviews_list():
    rows = db.list_interviews()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    upcoming = [i for i in rows if (i.get("date") or "") >= now and i.get("status") not in ("Completed", "Cancelled")]
    past = [i for i in rows if i not in upcoming]
    candidates = db.list_candidates()
    vacancies = db.list_vacancies()
    cand_by_id = {c["id"]: c for c in candidates}
    return render_template(
        "interviews.html",
        total=len(rows),
        upcoming=upcoming,
        past=past,
        candidate_names={c["id"]: c["name"] for c in candidates},
        candidate_roles={c["id"]: next((v["title"] for v in vacancies if v["id"] == c.get("vacancy_id")), "—") for c in candidates},
    )


@app.route("/interviews/new", methods=["GET", "POST"])
def interview_new():
    if request.method == "POST":
        data = _collect_interview_form()
        if not data["candidate_id"] or not data["date"]:
            flash("Candidate and date are required", "bad")
            return redirect(url_for("interview_new"))
        db.create_interview(data)
        # Auto-advance to interview stage if still early
        cand = db.get_candidate(data["candidate_id"])
        if cand and cand["stage"] in ("sourced", "screening"):
            db.move_candidate(cand["id"], "interview")
        flash("Interview scheduled", "ok")
        return redirect(url_for("interviews_list"))
    return render_template("interview_form.html", interview=None, candidates=db.list_candidates())


@app.route("/interviews/<iid>/edit", methods=["GET", "POST"])
def interview_edit(iid: str):
    interview = db.get_interview(iid)
    if not interview:
        abort(404)
    if request.method == "POST":
        db.update_interview(iid, _collect_interview_form())
        flash("Interview updated", "ok")
        return redirect(url_for("interviews_list"))
    return render_template("interview_form.html", interview=interview, candidates=db.list_candidates())


@app.route("/interviews/<iid>/delete", methods=["POST"])
def interview_delete(iid: str):
    db.delete_interview(iid)
    flash("Interview deleted", "ok")
    return redirect(url_for("interviews_list"))


def _collect_interview_form() -> dict:
    return {
        "candidate_id": request.form.get("candidate_id") or "",
        "interviewer": request.form.get("interviewer", ""),
        "type": request.form.get("type", "Technical"),
        "date": _iso(request.form.get("date", "")),
        "status": request.form.get("status", "Scheduled"),
        "feedback": request.form.get("feedback", ""),
        "rating": int(request.form.get("rating") or 0),
    }


# ---------------- Reports ----------------

@app.route("/reports")
def reports():
    candidates = db.list_candidates()
    histories = db.get_histories_for([c["id"] for c in candidates])
    tat = analytics.average_tat_by_stage(candidates, histories)
    stage_counts = analytics.funnel_counts(candidates)
    sources = analytics.source_breakdown(candidates)
    vacancies = db.list_vacancies()
    by_vacancy = [
        {
            "title": v["title"],
            "total": sum(1 for c in candidates if c.get("vacancy_id") == v["id"]),
            "active": sum(1 for c in candidates if c.get("vacancy_id") == v["id"] and c["stage"] not in ("hired","rejected")),
            "hired": sum(1 for c in candidates if c.get("vacancy_id") == v["id"] and c["stage"] == "hired"),
            "age": analytics.days_between(v["created_at"]),
        }
        for v in vacancies
    ]
    return render_template(
        "reports.html",
        total=len(candidates),
        hired=sum(1 for c in candidates if c["stage"] == "hired"),
        rejected=sum(1 for c in candidates if c["stage"] == "rejected"),
        conversion=analytics.conversion_pct(candidates, histories),
        stages=db.STAGES,
        tat=tat,
        tat_max=max([0] + list(tat.values())),
        stage_counts=stage_counts,
        stage_max=max([0] + list(stage_counts.values())),
        sources=sources,
        source_max=max([0] + [v for _, v in sources]),
        by_vacancy=by_vacancy,
    )


# ---------------- Settings ----------------

@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/seed", methods=["POST"])
def seed_data():
    if seed.seed_demo_data():
        flash("Demo data loaded", "ok")
    else:
        flash("Already have data — reset first", "bad")
    return redirect(url_for("dashboard"))


@app.route("/reset", methods=["POST"])
def reset_data():
    db.reset_all()
    flash("Reset complete", "ok")
    return redirect(url_for("dashboard"))


@app.route("/export.json")
def export_json():
    payload = json.dumps(db.all_state(), indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"talenttrack-{datetime.now().strftime('%Y-%m-%d')}.json",
    )


@app.route("/import", methods=["POST"])
def import_json():
    up = request.files.get("file")
    if not up:
        flash("Pick a JSON file", "bad")
        return redirect(url_for("settings_page"))
    try:
        payload = json.loads(up.read().decode("utf-8"))
        db.import_state(payload)
        flash("Imported", "ok")
    except Exception as exc:
        flash(f"Invalid JSON: {exc}", "bad")
    return redirect(url_for("settings_page"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)
