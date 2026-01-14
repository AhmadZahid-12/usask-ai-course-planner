from flask import Blueprint, render_template, request, jsonify
import json
from pathlib import Path

from app.gpt_helper import summarize_course
from app.scraper import get_course_raw_info

from app.db import db
from app.models import Plan
from app.planner import unlocked_courses, normalize_code
from app.services import build_degree_course_map

bp = Blueprint("main", __name__)
DEBUG_SCRAPE = True  # set False later

DEGREE_DIR = Path(__file__).resolve().parent / "degree"
DEFAULT_DEGREE_FILE = DEGREE_DIR / "bsc_cs.json"


@bp.route("/", methods=["GET"])
def home():
    return render_template("index.html", summary=None)


@bp.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@bp.route("/planner", methods=["GET"])
def planner():
    return render_template("planner.html")


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
# API: Degree + Planner
# ---------------------------

@bp.route("/api/degree/bsci_cs", methods=["GET"])
def api_degree_bsci_cs():
    if not DEFAULT_DEGREE_FILE.exists():
        return jsonify({"error": "Degree template not found", "path": str(DEFAULT_DEGREE_FILE)}), 404

    degree = json.loads(DEFAULT_DEGREE_FILE.read_text(encoding="utf-8"))
    return jsonify(degree)


@bp.route("/api/planner/unlocked", methods=["POST"])
def api_planner_unlocked():
    payload = request.get_json(silent=True) or {}
    completed = payload.get("completed", [])
    completed_set = {normalize_code(c) for c in completed}

    degree = json.loads(DEFAULT_DEGREE_FILE.read_text(encoding="utf-8"))
    required = [normalize_code(c) for c in degree.get("required_courses", [])]

    # Build course_map with cached official prereqs for required list
    course_map = build_degree_course_map(required)

    unlocked = unlocked_courses(course_map, completed_set)

    return jsonify({
        "required_count": len(required),
        "completed_count": len(completed_set),
        "unlocked": unlocked
    })


# ---------------------------
# API: Plan Save/Load
# ---------------------------

@bp.route("/api/plan/save", methods=["POST"])
def api_plan_save():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "My Plan").strip()
    completed = payload.get("completed", [])
    notes = payload.get("notes", "")

    completed_norm = [normalize_code(c) for c in completed]
    completed_json = json.dumps(completed_norm)

    plan_id = payload.get("id")

    if plan_id:
        plan = Plan.query.get(int(plan_id))
        if not plan:
            return jsonify({"error": "Plan not found"}), 404
    else:
        plan = Plan()

    plan.name = name
    plan.completed_json = completed_json
    plan.notes = notes

    db.session.add(plan)
    db.session.commit()

    return jsonify({"ok": True, "plan": plan.to_dict()})


@bp.route("/api/plan/load", methods=["GET"])
def api_plan_load():
    """
    For MVP: load the latest plan (most recent).
    """
    plan = Plan.query.order_by(Plan.id.desc()).first()
    if not plan:
        return jsonify({"plan": None})

    return jsonify({"plan": plan.to_dict()})


@bp.route("/api/plan/export", methods=["GET"])
def api_plan_export():
    plan = Plan.query.order_by(Plan.id.desc()).first()
    if not plan:
        return jsonify({"error": "No plan found"}), 404

    return jsonify({
        "name": plan.name,
        "completed": json.loads(plan.completed_json or "[]"),
        "notes": plan.notes
    })


@bp.route("/api/plan/import", methods=["POST"])
def api_plan_import():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "Imported Plan").strip()
    completed = payload.get("completed", [])
    notes = payload.get("notes", "")

    completed_norm = [normalize_code(c) for c in completed]

    plan = Plan(
        name=name,
        completed_json=json.dumps(completed_norm),
        notes=notes
    )
    db.session.add(plan)
    db.session.commit()

    return jsonify({"ok": True, "plan": plan.to_dict()})