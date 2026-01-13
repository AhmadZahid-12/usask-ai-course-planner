from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from app.gpt_helper import summarize_course
from app.scraper import get_course_raw_info

# planner helpers (make sure app/planner.py exists and has these)
from app.planner import unlocked_courses, normalize_code

bp = Blueprint("main", __name__)

DEBUG_SCRAPE = True  # set to False later


@bp.route("/", methods=["GET"])
def home():
    return render_template("index.html", summary=None)


@bp.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@bp.route("/summarize", methods=["POST"], endpoint="summarize_course")
def summarize_course_route():
    code = (request.form.get("course_code") or "").strip()
    if not code:
        return render_template("index.html", summary="No course code provided.")

    raw = get_course_raw_info(code)

    official_text = (raw.get("raw_text") or "").strip()
    source_url = raw.get("source_url")
    from_cache = raw.get("from_cache", False)
    not_found = raw.get("not_found", False)

    if DEBUG_SCRAPE:
        print("\n================ SCRAPE DEBUG ================")
        print("Input:", code)
        print("Normalized:", raw.get("course_code"))
        print("URL:", source_url)
        print("From cache:", from_cache)
        print("Not found:", not_found)
        print("Official text preview:\n", official_text[:1200])
        print("=============================================\n")

    if not_found or not official_text:
        summary = "I couldn't find official details for this course on the page I scraped."
        return render_template(
            "index.html",
            summary=summary,
            source_url=source_url,
            from_cache=from_cache,
        )

    summary = summarize_course(raw.get("course_code", code), desc=official_text)

    return render_template(
        "index.html",
        summary=summary,
        source_url=source_url,
        from_cache=from_cache,
    )


# ---------------------------
# Degree Planner (MVP)
# ---------------------------

@bp.route("/planner", methods=["GET"])
def planner_page():
    return render_template("planner.html")


@bp.route("/api/degree/bsc-cs", methods=["GET"])
def api_degree_bsc_cs():
    """
    Loads the degree template JSON from:
      app/degree/bsc_cs.json
    """
    degree_path = Path(__file__).resolve().parent / "degree" / "bsc_cs.json"

    if not degree_path.exists():
        return jsonify(
            {
                "error": "Degree template file not found.",
                "expected_path": str(degree_path),
            }
        ), 404

    data = json.loads(degree_path.read_text(encoding="utf-8"))
    return jsonify(data)


@bp.route("/api/planner/unlocked", methods=["POST"])
def api_planner_unlocked():
    payload = request.get_json(silent=True) or {}
    completed = payload.get("completed", []) or []
    required = payload.get("required", []) or []

    completed_norm = [normalize_code(c) for c in completed if isinstance(c, str)]
    required_norm = [normalize_code(c) for c in required if isinstance(c, str)]

    unlocked = unlocked_courses(completed_norm, required_norm)
    return jsonify({"unlocked": unlocked})