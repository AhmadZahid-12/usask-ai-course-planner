from flask import Blueprint, Response, render_template, request, jsonify
import json
import os
from pathlib import Path

from app.gpt_helper import SUMMARY_UNAVAILABLE, summarize_course
from app.scraper import course_url, get_course_raw_info

from app.catalogue import available_courses, cmpt_catalogue, course_detail, latest_completed, starter_catalogue
from app.db import db
from app.models import Plan
from app.planner import COURSE_RE, normalize_code

from app.services import (
    bulk_scrape_courses,
    check_term_sequence,
    planner_status,
)

bp = Blueprint("main", __name__)

DEGREE_DIR = Path(__file__).resolve().parent / "degree"
DEFAULT_DEGREE_FILE = DEGREE_DIR / "bsc_cs.json"
PROGRAM_URL = "https://programs.usask.ca/arts-and-science/computer-science/bsc-4-computer-science.php"


@bp.route("/", methods=["GET"])
def home():
    catalogue = starter_catalogue()
    return render_template(
        "dashboard.html", courses=template_courses(), edition=catalogue["edition"],
        program_url=PROGRAM_URL,
    )


@bp.get("/courses")
def explorer():
    return render_template("explorer.html", courses=available_courses(), catalogue=cmpt_catalogue())


@bp.get("/api/catalogue/course")
def api_catalogue_course():
    code = normalize_code(request.args.get("code"))
    if not COURSE_RE.fullmatch(code):
        return jsonify({"error": "Enter a course code like CMPT 141."}), 400
    return jsonify(course_detail(code, latest_completed()))


@bp.get("/assistant")
def assistant():
    return _assistant_page(code=request.args.get("code", ""))


def _assistant_page(**context):
    return render_template(
        "assistant.html", ai_enabled=bool(os.getenv("OPENAI_API_KEY", "").strip()), **context,
    )


@bp.get("/settings")
def settings():
    return render_template("settings.html")


@bp.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@bp.route("/planner", methods=["GET"])
def planner():
    return render_template("planner.html", courses=template_courses())


def template_courses() -> dict:
    degree = json.loads(DEFAULT_DEGREE_FILE.read_text(encoding="utf-8"))
    metadata = starter_catalogue()["courses"]
    return {
        code: metadata.get(code, {"title": code, "credit_units": None})
        for code in degree["required_courses"]
    }


@bp.route("/summarize", methods=["POST"], endpoint="summarize_course")
def summarize_course_route():
    code = normalize_code(request.form.get("course_code"))
    if not COURSE_RE.fullmatch(code):
        return _assistant_page(code=code, error="Enter a course code such as CMPT 141.")

    raw = get_course_raw_info(code)
    official = (raw.get("raw_text") or "").strip()
    context = {
        "code": code,
        "source_url": course_url(code),
        "retrieved": raw.get("retrieved"),
        "official": official,
    }
    if raw.get("not_found") or not official:
        context["official"] = ""
        return _assistant_page(**context, error="Could not load the official course entry. Try the catalogue link.")

    action = request.form.get("action", "generate")
    if action == "generate" and os.getenv("OPENAI_API_KEY", "").strip():
        summary = summarize_course(code, desc=official)
        if summary == SUMMARY_UNAVAILABLE or not summary:
            return _assistant_page(**context, error="The AI summary is unavailable. The official entry is below.")
        return _assistant_page(**context, summary=summary)

    return _assistant_page(**context)


# ---------------------------
# API: Degree + Planner
# ---------------------------

@bp.route("/api/degree/bsci_cs", methods=["GET"])
def api_degree_bsci_cs():
    if not DEFAULT_DEGREE_FILE.exists():
        return jsonify({"error": "Degree template not found", "path": str(DEFAULT_DEGREE_FILE)}), 404

    degree = json.loads(DEFAULT_DEGREE_FILE.read_text(encoding="utf-8"))
    return jsonify(degree)


@bp.route("/api/courses/bulk_scrape", methods=["POST"])
def api_courses_bulk_scrape():
    payload = request.get_json(silent=True)
    codes = payload.get("codes", []) if isinstance(payload, dict) else []
    if not isinstance(codes, list) or any(code is not None and not isinstance(code, str) for code in codes):
        return jsonify({"error": "Provide a list of course-code strings."}), 400
    normalized = [normalize_code(code) for code in codes if code and code.strip()]
    if not normalized:
        return jsonify({"error": "No codes provided"}), 400
    if not all(COURSE_RE.fullmatch(code) for code in normalized):
        return jsonify({"error": "Enter course codes such as CMPT 141."}), 400

    result = bulk_scrape_courses(normalized)
    return jsonify(result)


@bp.route("/api/planner/status", methods=["POST"])
def api_planner_status():
    return _planner_status_response()


def _planner_status_response(*, legacy: bool = False) -> Response | tuple[Response, int]:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    completed = payload.get("completed", [])
    if not isinstance(completed, list) or not all(isinstance(code, str) for code in completed):
        return jsonify({"error": "Completed courses must be a list of course-code strings"}), 400

    degree = json.loads(DEFAULT_DEGREE_FILE.read_text(encoding="utf-8"))
    required = degree.get("required_courses", [])
    return jsonify(planner_status(required, set(completed), legacy=legacy))


# Keep the old endpoint so older clients/UI don't break.
# Also allow GET to return a helpful message (curl mistakes) rather than a confusing 405.
@bp.route("/api/planner/unlocked", methods=["POST", "GET"])
def api_planner_unlocked():
    if request.method == "GET":
        return (
            jsonify(
                {
                    "error": "Use POST with JSON body",
                    "example": {"completed": ["CMPT 141", "CMPT 145"]},
                }
            ),
            405,
        )

    return _planner_status_response(legacy=True)


@bp.post("/api/planner/sequence")
def api_term_sequence():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a draft with terms and completed courses."}), 400
    terms = payload.get("terms")
    completed = payload.get("completed", [])
    if (
        not _string_list(completed) or len(completed) > 1000
        or not isinstance(terms, list) or len(terms) > 16
        or not all(_string_list(term) for term in terms)
        or sum(map(len, terms)) > 100
    ):
        return jsonify({"error": "Use course codes and at most 16 terms and 100 draft courses."}), 400
    normalized = [[normalize_code(code) for code in term] for term in terms]
    codes = [code for term in normalized for code in term]
    if any(not COURSE_RE.fullmatch(code) for code in codes) or len(set(codes)) != len(codes):
        return jsonify({"error": "Use valid course codes and place each draft course only once."}), 400
    return jsonify(terms=check_term_sequence(normalized, set(map(normalize_code, completed))))


def _string_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _plan_fields(payload, default_name: str) -> tuple[str, list[str], str]:
    if not isinstance(payload, dict):
        raise ValueError("Expected a plan JSON object.")
    name = payload.get("name") or default_name
    completed = payload.get("completed", [])
    notes = payload.get("notes", "")
    if not isinstance(name, str) or len(name) > 120:
        raise ValueError("Enter a plan name up to 120 characters.")
    if not _string_list(completed):
        raise ValueError("Completed courses must be a list of course codes.")
    if not isinstance(notes, str):
        raise ValueError("Notes must be text.")
    return name.strip() or default_name, list(map(normalize_code, completed)), notes


# ---------------------------
# API: Plan Save/Load
# ---------------------------

@bp.route("/api/plan/save", methods=["POST"])
def api_plan_save():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    try:
        name, completed, notes = _plan_fields(payload, "My Plan")
        plan_id = int(payload["id"]) if payload.get("id") else None
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    if plan_id:
        plan = db.session.get(Plan, plan_id)
        if not plan:
            return jsonify({"error": "Plan not found"}), 404
    else:
        plan = Plan()

    plan.name = name
    plan.completed_json = json.dumps(completed)
    plan.notes = notes

    db.session.add(plan)
    db.session.commit()

    return jsonify({"ok": True, "plan": plan.to_dict()})


@bp.route("/api/plan/load", methods=["GET"])
def api_plan_load():
    plan = Plan.query.order_by(Plan.id.desc()).first()
    if not plan:
        return jsonify({"plan": None})
    return jsonify({"plan": plan.to_dict()})


@bp.route("/api/plan/export", methods=["GET"])
def api_plan_export():
    plan = Plan.query.order_by(Plan.id.desc()).first()
    if not plan:
        return jsonify({"error": "No plan found"}), 404

    return jsonify(
        {
            "name": plan.name,
            "completed": json.loads(plan.completed_json or "[]"),
            "notes": plan.notes,
        }
    )


@bp.route("/api/plan/import", methods=["POST"])
def api_plan_import():
    payload = request.get_json(silent=True)
    try:
        name, completed, notes = _plan_fields(payload, "Imported Plan")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    plan = Plan(
        name=name,
        completed_json=json.dumps(completed),
        notes=notes,
    )
    db.session.add(plan)
    db.session.commit()

    return jsonify({"ok": True, "plan": plan.to_dict()})
