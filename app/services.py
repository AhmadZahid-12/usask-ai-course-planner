import json
from typing import Dict, List, Set, Any
from datetime import datetime

from app.db import db
from app.models import CourseCache
from app.scraper import get_course_raw_info
from app.planner import normalize_code, parse_prereqs, prereqs_satisfied


def _coursecache_get(code: str) -> CourseCache | None:
    code = normalize_code(code)
    return CourseCache.query.filter_by(code=code).first()


def _coursecache_upsert(code: str, source_url: str, raw_text: str, prereq_groups: List[List[str]]) -> CourseCache:
    code = normalize_code(code)
    row = _coursecache_get(code)
    if not row:
        row = CourseCache(code=code)

    row.source_url = source_url or ""
    row.raw_text = raw_text or ""
    row.prereqs_json = json.dumps(prereq_groups or [])
    row.updated_at = datetime.utcnow()

    db.session.add(row)
    return row


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
        return {
            "code": cached.code,
            "source_url": cached.source_url,
            "raw_text": cached.raw_text,
            "prereqs": json.loads(cached.prereqs_json or "[]"),
            "from_db": True,
            "not_found": False,
        }

    raw = get_course_raw_info(code)
    official_text = (raw.get("raw_text") or "").strip()
    source_url = raw.get("source_url") or ""
    not_found = bool(raw.get("not_found")) or not official_text

    prereq_groups: List[List[str]] = []
    if official_text:
        prereq_groups = parse_prereqs(official_text)

    # write to DB even if empty so we don't hammer scraper repeatedly
    _coursecache_upsert(code, source_url, official_text, prereq_groups)
    db.session.commit()

    return {
        "code": normalize_code(raw.get("course_code", code)),
        "source_url": source_url,
        "raw_text": official_text,
        "prereqs": prereq_groups,
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


def build_degree_course_map(required_codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Builds the planner course_map:
      course_map["CMPT 214"] = {"raw_text": "...", "prereqs": [[...], [...]], "source_url": "..."}
    Uses DB-backed CourseCache and scrapes missing ones.
    """
    course_map: Dict[str, Dict[str, Any]] = {}

    for code in required_codes:
        info = get_or_scrape_course(code)
        course_map[normalize_code(info["code"])] = {
            "raw_text": info["raw_text"],
            "prereqs": info["prereqs"],
            "source_url": info["source_url"],
            "not_found": info["not_found"],
        }

    return course_map


def _best_missing_group(prereq_groups: List[List[str]], completed: Set[str]) -> List[str]:
    """
    If prereqs are unsatisfied, return the "closest" group (fewest missing),
    and list which courses are missing from that group.
    """
    completed_norm = {normalize_code(c) for c in completed}

    if not prereq_groups:
        return []

    best_missing: List[str] | None = None

    for group in prereq_groups:
        group_norm = [normalize_code(c) for c in group]
        missing = [c for c in group_norm if c not in completed_norm]

        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing

    return best_missing or []


def planner_status(required_codes: List[str], completed: Set[str]) -> Dict[str, Any]:
    """
    Returns:
      {
        unlocked: [...],
        locked: [{code, missing_prereqs: [...]}, ...],
        required_count, completed_count
      }
    """
    required_norm = [normalize_code(c) for c in required_codes]
    completed_norm = {normalize_code(c) for c in completed}

    course_map = build_degree_course_map(required_norm)

    unlocked: List[str] = []
    locked: List[Dict[str, Any]] = []

    for code in required_norm:
        if code in completed_norm:
            continue

        data = course_map.get(code, {})
        prereq_groups = data.get("prereqs", [])

        if prereqs_satisfied(prereq_groups, completed_norm):
            unlocked.append(code)
        else:
            locked.append({
                "code": code,
                "missing_prereqs": _best_missing_group(prereq_groups, completed_norm),
            })

    return {
        "required_count": len(required_norm),
        "completed_count": len(completed_norm),
        "unlocked": sorted(unlocked),
        "locked": sorted(locked, key=lambda x: x["code"]),
    }