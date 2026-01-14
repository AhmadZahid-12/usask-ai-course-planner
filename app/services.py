import json
from datetime import datetime

from app.scraper import get_course_raw_info
from app.planner import parse_prereqs, normalize_code
from app.db import db
from app.models import CourseCache


def ensure_course_cached(code: str) -> CourseCache:
    code = normalize_code(code)
    row = CourseCache.query.get(code)
    if row and row.raw_text:
        return row

    raw = get_course_raw_info(code)
    official_text = (raw.get("raw_text") or "").strip()

    prereq_groups = parse_prereqs(official_text)
    prereqs_json = json.dumps(prereq_groups)

    if not row:
        row = CourseCache(code=code)

    row.source_url = raw.get("source_url", "") or ""
    row.raw_text = official_text
    row.prereqs_json = prereqs_json
    row.updated_at = datetime.utcnow()

    db.session.add(row)
    db.session.commit()
    return row


def build_degree_course_map(required_courses: list[str]) -> dict:
    """
    Returns a dict:
      {
        "CMPT 214": {"raw_text": "...", "prereqs": [[...],[...]], "source_url": "..."},
        ...
      }
    """
    course_map = {}

    for c in required_courses:
        code = normalize_code(c)
        row = ensure_course_cached(code)

        try:
            prereqs = json.loads(row.prereqs_json or "[]")
        except Exception:
            prereqs = []

        course_map[code] = {
            "raw_text": row.raw_text,
            "prereqs": prereqs,
            "source_url": row.source_url,
        }

    return course_map