"""Preview private syllabi and save only reviewed calendar deadlines."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from pathlib import Path
import re
import secrets
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge

from app.calendar_store import CalendarEvent, CalendarValidationError, create_event
from app.db import db
from app.planner import COURSE_RE, normalize_code
from app.student_migrations import student_storage_ready
from app.syllabus_extract import MAX_CANDIDATES, extract_candidates
from app.syllabus_files import MAX_UPLOAD_BYTES, read_document

bp = Blueprint("syllabus", __name__)
_PROCESS_REVIEW_KEY = secrets.token_bytes(32)
_REVIEW_AGE_SECONDS = 2 * 60 * 60
_APPROVAL_LIMIT_BYTES = 192 * 1024
_DEFAULT_TIME_ZONE = "America/Regina"
_CATEGORIES = {"assignment", "quiz", "exam", "personal"}
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CLOCK = re.compile(r"\d{2}:\d{2}")


@bp.after_request
def prevent_private_response_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.errorhandler(RequestEntityTooLarge)
def upload_too_large(error):
    return jsonify(error="The request is too large. Upload one syllabus up to 4 MB."), 413


def _serializer() -> URLSafeTimedSerializer:
    key = current_app.secret_key or _PROCESS_REVIEW_KEY
    return URLSafeTimedSerializer(key, salt="syllabus-preview-v1")


def _course_code(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Enter a course code such as CMPT 141.")
    code = normalize_code(value)
    if code and not COURSE_RE.fullmatch(code):
        raise ValueError("Enter a course code such as CMPT 141.")
    return code


@bp.get("/syllabus")
def upload_page():
    try:
        code = _course_code(request.args.get("course_code", ""))
    except ValueError:
        code = ""
    return render_template("syllabus.html", prefill_course=code, default_zone=_DEFAULT_TIME_ZONE)


@bp.post("/api/syllabus/preview")
def preview():
    request.max_content_length = MAX_UPLOAD_BYTES + 64 * 1024
    request.max_form_memory_size = 512 * 1024
    request.max_form_parts = 8
    file = request.files.get("syllabus")
    if not file or not file.filename:
        return jsonify(error="Choose a syllabus file."), 400
    try:
        code = _course_code(request.form.get("course_code", ""))
        content = file.stream.read(MAX_UPLOAD_BYTES + 1)
        pages = read_document(content, Path(file.filename).suffix)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    serializer = _serializer()
    proposals = []
    for candidate in extract_candidates(pages, code):
        data = asdict(candidate)
        token = serializer.dumps({
            "source_key": data.pop("source_key"),
            "evidence": candidate.evidence,
            "page": candidate.page,
        })
        proposals.append({**data, "token": token})
    return jsonify(
        candidates=proposals,
        limit_reached=len(proposals) == MAX_CANDIDATES,
    )


def _local_time(day: date, clock: str, name: str) -> datetime:
    if not _CLOCK.fullmatch(clock) or not name or len(name) > 80:
        raise ValueError("Enter a valid time and an IANA time zone, such as America/Regina.")
    try:
        zone = ZoneInfo(name)
        wall_time = datetime.combine(day, time.fromisoformat(clock))
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Enter a valid time and an IANA time zone, such as America/Regina.") from None
    possibilities = set()
    try:
        for fold in (0, 1):
            instant = wall_time.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if instant.astimezone(zone).replace(tzinfo=None) == wall_time:
                possibilities.add(instant)
    except OverflowError:
        raise ValueError("Enter a date and time inside the supported calendar range.") from None
    if len(possibilities) != 1:
        raise ValueError("That local time is skipped or repeated because of daylight saving. Verify the time and zone.")
    return possibilities.pop().astimezone(zone)


def _reviewed_event(item: dict, serializer: URLSafeTimedSerializer) -> tuple[str, dict]:
    token = item.get("token")
    if not isinstance(token, str) or not 1 <= len(token) <= 2200:
        raise ValueError("This proposal is invalid. Upload the syllabus again.")
    try:
        source = serializer.loads(token, max_age=_REVIEW_AGE_SECONDS)
    except BadSignature:
        raise ValueError("This preview expired or is invalid. Upload the syllabus again.") from None

    course = _course_code(item.get("course_code", ""))
    title = item.get("title")
    category = item.get("category")
    day_text = item.get("date")
    clock = item.get("time", "")
    zone = item.get("timezone", _DEFAULT_TIME_ZONE)
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise ValueError("Each approved deadline needs a title up to 120 characters.")
    if not isinstance(category, str) or category not in _CATEGORIES:
        raise ValueError("Choose Assignment, Quiz, Exam or Other for the deadline.")
    if not isinstance(day_text, str) or not _ISO_DATE.fullmatch(day_text):
        raise ValueError("Enter a complete date for each approved deadline.")
    if not isinstance(clock, str) or not isinstance(zone, str):
        raise ValueError("Enter a valid time and time zone.")
    try:
        day = date.fromisoformat(day_text)
        following_day = day + timedelta(days=1)
    except (ValueError, OverflowError):
        raise ValueError("Enter a valid calendar date.") from None

    if clock:
        when = _local_time(day, clock, zone)
        try:
            end = (when.astimezone(timezone.utc) + timedelta(minutes=1)).astimezone(when.tzinfo)
        except OverflowError:
            raise ValueError("Enter a date and time inside the supported calendar range.") from None
        start_text, end_text = when.isoformat(), end.isoformat()
    else:
        start_text, end_text = day.isoformat(), following_day.isoformat()

    source_key = hashlib.sha256(f"{source['source_key']}\0{course}".encode()).hexdigest()
    position = f"PDF page {source['page']}" if source["page"] is not None else "text upload"
    event = {
        "title": title.strip(), "category": category, "course_code": course,
        "start": start_text, "end": end_text, "all_day": not clock,
        "timezone": zone if clock else _DEFAULT_TIME_ZONE,
        "description": f"Syllabus source ({position})\n{source['evidence']}",
        "reminder_minutes": None,
    }
    return source_key, event


@bp.post("/api/syllabus/approve")
def approve():
    request.max_content_length = _APPROVAL_LIMIT_BYTES
    payload = request.get_json(silent=True)
    items = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CANDIDATES or not all(isinstance(item, dict) for item in items):
        return jsonify(error="Select at least one reviewed deadline to import."), 400
    if not student_storage_ready(CalendarEvent):
        return jsonify(error="Calendar storage has not been set up. The review has not been saved."), 503
    serializer = _serializer()
    try:
        reviewed = [_reviewed_event(item, serializer) for item in items]
    except ValueError as error:
        return jsonify(error=str(error)), 400

    for attempt in range(2):
        added = []
        duplicates = 0
        keys = {key for key, _ in reviewed}
        seen = set(db.session.scalars(db.select(CalendarEvent.import_key).where(CalendarEvent.import_key.in_(keys))))
        try:
            for key, event in reviewed:
                if key in seen:
                    duplicates += 1
                else:
                    added.append(create_event(event, import_key=key).as_dict())
                    seen.add(key)
            db.session.commit()
        except CalendarValidationError as error:
            db.session.rollback()
            return jsonify(error=str(error)), 400
        except IntegrityError:
            db.session.rollback()
            if attempt:
                return jsonify(error="Another import changed the calendar. Review and try again."), 409
        else:
            return jsonify(events=added, duplicate_count=duplicates)
    raise AssertionError("The import attempt did not return a result.")
