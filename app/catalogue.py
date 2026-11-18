"""Public catalogue metadata and course details for the workspace."""

import json
from functools import cache
from pathlib import Path

from app.models import CourseCache, Plan
from app.planner import COURSE_RE, classify_courses, extract_prereq_line, normalize_code
from app.scraper import course_url, get_cached_course
from app.services import get_or_scrape_course

DATA_DIR = Path(__file__).resolve().parent / "degree"


@cache
def starter_catalogue() -> dict:
    return json.loads((DATA_DIR / "starter_catalogue.json").read_text(encoding="utf-8"))


@cache
def cmpt_catalogue() -> dict:
    return json.loads((DATA_DIR / "cmpt_catalogue.json").read_text(encoding="utf-8"))


def available_courses() -> list[dict]:
    indexed = cmpt_catalogue()["courses"]
    starter = starter_catalogue()["courses"]
    codes = set(indexed) | set(starter)
    cached = CourseCache.query.with_entities(CourseCache.code).filter(CourseCache.raw_text != "")
    codes.update(code for (code,) in cached if COURSE_RE.fullmatch(code))
    courses = []
    for code in sorted(codes):
        metadata = indexed.get(code) or starter.get(code) or get_cached_course(code) or {}
        courses.append({
            "code": code,
            "title": metadata.get("title"),
            "credit_units": metadata.get("credit_units"),
            "starter": code in starter,
        })
    return courses


def latest_completed() -> set[str]:
    plan = Plan.query.order_by(Plan.id.desc()).first()
    if plan is None:
        return set()
    try:
        values = json.loads(plan.completed_json)
    except (ValueError, TypeError):
        return set()
    return {normalize_code(code) for code in values if isinstance(code, str)} if isinstance(values, list) else set()


def course_detail(code: str, completed: set[str]) -> dict:
    record = get_or_scrape_course(code)
    metadata = cmpt_catalogue()["courses"].get(code, {})
    description = record["raw_text"]
    unavailable = record["not_found"]
    unlocked, locked = classify_courses({code: record}, completed)
    if code in completed:
        status = "completed"
    elif unlocked:
        status = "eligible"
    elif locked[0].get("reason"):
        status = "review"
    else:
        status = "locked"
    return {
        "code": code,
        "title": record.get("title") or metadata.get("title"),
        "credit_units": record.get("credit_units") if record.get("credit_units") is not None else metadata.get("credit_units"),
        "source_url": course_url(code),
        "description": description if not unavailable else "",
        "prerequisites": extract_prereq_line(description) if not unavailable else None,
        "prerequisite_groups": record["prereqs"],
        "retrieved": record.get("retrieved"),
        "cached": record.get("from_db", False),
        "status": status,
        "registration_note": locked[0].get("reason") if locked else None,
        "missing": locked[0]["missing"] if locked else [],
        "available": not unavailable,
    }
