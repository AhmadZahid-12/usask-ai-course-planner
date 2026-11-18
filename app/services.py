import json
from typing import Dict, List, Set, Any
from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert

from app.db import db
from app.models import CourseCache
from app.scraper import get_cached_course, get_course_raw_info
from app.planner import (
    CourseInfo,
    PrerequisiteGroups,
    classify_courses,
    normalize_code,
    parse_prereqs,
)


def _coursecache_get(code: str) -> CourseCache | None:
    code = normalize_code(code)
    return CourseCache.query.filter_by(code=code).first()


def _coursecache_upsert(
    code: str, source_url: str, raw_text: str, prereq_groups: PrerequisiteGroups | None
) -> None:
    values = {
        "source_url": source_url,
        "raw_text": raw_text,
        "prereqs_json": json.dumps(prereq_groups),
        "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    statement = insert(CourseCache).values(code=normalize_code(code), **values)
    db.session.execute(statement.on_conflict_do_update(index_elements=["code"], set_=values))


def get_or_scrape_course(code: str) -> Dict[str, Any]:
    """
    Returns a dict containing:
      {
        code, source_url, raw_text, prereqs (list of OR-of-AND groups), from_db, not_found
      }
    """
    code = normalize_code(code)

    cached = _coursecache_get(code)
    if cached and (cached.raw_text or "").strip():
        metadata = get_cached_course(code) or {}
        # Reparse older cache entries with the current prerequisite rules.
        return {
            "code": cached.code,
            "source_url": cached.source_url,
            "raw_text": cached.raw_text,
            "prereqs": parse_prereqs(cached.raw_text),
            "title": metadata.get("title"),
            "credit_units": metadata.get("credit_units"),
            "retrieved": metadata.get("retrieved"),
            "from_db": True,
            "not_found": False,
        }

    raw = get_course_raw_info(code)
    official_text = (raw.get("raw_text") or "").strip()
    source_url = raw.get("source_url") or ""
    not_found = bool(raw.get("not_found")) or not official_text

    prereq_groups = None if not_found else parse_prereqs(official_text)

    if not not_found:
        _coursecache_upsert(code, source_url, official_text, prereq_groups)
        db.session.commit()

    return {
        "code": normalize_code(raw.get("course_code", code)),
        "source_url": source_url,
        "raw_text": official_text,
        "prereqs": prereq_groups,
        "title": raw.get("title"),
        "credit_units": raw.get("credit_units"),
        "retrieved": raw.get("retrieved"),
        "from_db": False,
        "not_found": not_found,
    }


def bulk_scrape_courses(codes: List[str]) -> Dict[str, Any]:
    """
    Scrape/cache many courses. Returns summary info + per-course results.
    """
    results = []
    ok = 0
    missing = 0

    for c in codes:
        info = get_or_scrape_course(c)
        results.append({
            "code": info["code"],
            "from_db": info["from_db"],
            "not_found": info["not_found"],
            "source_url": info["source_url"],
        })
        if info["not_found"]:
            missing += 1
        else:
            ok += 1

    return {
        "requested": len(codes),
        "ok": ok,
        "missing": missing,
        "results": results,
    }


def build_degree_course_map(required_codes: List[str]) -> dict[str, CourseInfo]:
    """Load catalogue records from the cache or scraper."""
    course_map: dict[str, CourseInfo] = {}
    for code in dict.fromkeys(map(normalize_code, required_codes)):
        info = get_or_scrape_course(code)
        course_map[code] = {
            "raw_text": info["raw_text"],
            "prereqs": info["prereqs"],
            "source_url": info["source_url"],
            "not_found": info["not_found"],
        }

    return course_map


def planner_status(
    required_codes: list[str], completed: Set[str], *, legacy: bool = False
) -> Dict[str, Any]:
    """Compute planner results and preserve each endpoint's response fields."""
    completed = {normalize_code(code) for code in completed}
    course_map = build_degree_course_map(required_codes)
    unlocked, locked = classify_courses(course_map, completed)

    return {
        "required_count": len(course_map),
        "completed_count": len(completed),
        "unlocked": unlocked,
        "locked": locked if legacy else [
            {
                "code": item["course"],
                "missing_prereqs": item["missing"],
                **({"reason": item["reason"]} if "reason" in item else {}),
            }
            for item in locked
        ],
    }


def check_term_sequence(terms: list[list[str]], completed: set[str]) -> list[list[dict]]:
    """Compare draft order with cached prerequisites, without requesting class times."""
    codes = {code for term in terms for code in term}
    records = {
        row.code: parse_prereqs(row.raw_text)
        for row in CourseCache.query.filter(CourseCache.code.in_(codes))
    }
    earlier = set(completed)
    results = []
    for term in terms:
        course_map: dict[str, CourseInfo] = {
            code: {"prereqs": records.get(code), "not_found": code not in records}
            for code in term
        }
        _, locked = classify_courses(course_map, earlier)
        reasons = {row["course"]: row for row in locked}
        results.append([
            {
                **reasons.get(code, {"course": code, "missing": []}),
                "already_completed": code in completed,
                "dependencies": (records.get(code) or [])[:4],
            }
            for code in term
        ])
        earlier.update(term)
    return results
