"""Calendar validation and persistence."""

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import CheckConstraint, Index, and_, or_

from app.db import db
from app.planner import COURSE_RE, normalize_code

DEFAULT_TIMEZONE = "America/Regina"
CATEGORIES = frozenset({"class", "assignment", "exam", "study", "personal", "quiz"})
DEADLINE_CATEGORIES = frozenset({"assignment", "exam", "quiz"})
MAX_REMINDER_MINUTES = 7 * 24 * 60
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)


class CalendarValidationError(ValueError):
    """An event or range contains invalid input."""


class CalendarEvent(db.Model):
    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint(
            "(all_day = 1 AND start_date IS NOT NULL AND end_date IS NOT NULL AND end_date > start_date "
            "AND start_at IS NULL AND end_at IS NULL) OR "
            "(all_day = 0 AND start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at "
            "AND start_date IS NULL AND end_date IS NULL)",
            name="calendar_event_valid_period",
        ),
        Index("ix_calendar_events_timed_range", "start_at", "end_at"),
        Index("ix_calendar_events_day_range", "start_date", "end_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(16), nullable=False)
    course_code = db.Column(db.String(20), nullable=True)
    description = db.Column(db.Text, nullable=False, default="")
    all_day = db.Column(db.Boolean, nullable=False)
    timezone = db.Column(db.String(64), nullable=False)
    # SQLite does not retain offsets. Timed events use UTC; all-day dates stay local.
    start_at = db.Column(db.DateTime, nullable=True)
    end_at = db.Column(db.DateTime, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    reminder_minutes = db.Column(db.Integer, nullable=True)
    import_key = db.Column(db.String(128), nullable=True, unique=True)

    def as_dict(self) -> dict:
        reminder_at = None
        if self.reminder_minutes is not None:
            start = self.start_at if not self.all_day else local_midnight(
                self.start_date, parse_timezone(self.timezone)
            )
            reminder_at = _utc_text(start - timedelta(minutes=self.reminder_minutes))
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "course_code": self.course_code,
            "description": self.description,
            "timezone": self.timezone,
            "all_day": self.all_day,
            "start": self.start_date.isoformat() if self.all_day else _utc_text(self.start_at),
            "end": self.end_date.isoformat() if self.all_day else _utc_text(self.end_at),
            "reminder_minutes": self.reminder_minutes,
            "reminder_at": reminder_at,
            "deadline": bool(self.import_key) and (
                self.end_date - self.start_date == timedelta(days=1) if self.all_day
                else self.end_at - self.start_at == timedelta(minutes=1)
            ),
        }


def parse_timezone(value: str) -> ZoneInfo:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise CalendarValidationError("Choose a valid time zone.")
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise CalendarValidationError("Choose a valid time zone.") from error


def parse_date(value: str, label: str) -> date:
    if isinstance(value, str) and _DATE.fullmatch(value):
        try:
            result = date.fromisoformat(value)
            if 1 < result.year < 9999:
                return result
        except ValueError:
            pass
    raise CalendarValidationError(f"{label} must be a valid date in YYYY-MM-DD format.")


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def _utc_text(value: datetime) -> str:
    return value.isoformat() + "Z"


def _parse_timestamp(value: str, label: str) -> datetime:
    if isinstance(value, str) and _TIMESTAMP.fullmatch(value):
        try:
            normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
            result = datetime.fromisoformat(normalized).astimezone(timezone.utc).replace(tzinfo=None)
            if 1 < result.year < 9999:
                return result
        except (ValueError, OverflowError):
            pass
    raise CalendarValidationError(f"{label} must include a valid time and UTC offset.")


def _event_fields(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise CalendarValidationError("Send an event as a JSON object.")

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
        raise CalendarValidationError("Enter an event title between 1 and 160 characters.")

    category = payload.get("category")
    if not isinstance(category, str) or category not in CATEGORIES:
        raise CalendarValidationError("Choose a valid event category.")

    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 4000:
        raise CalendarValidationError("Keep the description under 4,000 characters.")

    course_code = payload.get("course_code")
    if course_code is not None:
        if not isinstance(course_code, str):
            raise CalendarValidationError("Enter a valid course code, such as CMPT 141.")
        course_code = normalize_code(course_code) or None
        if course_code and not COURSE_RE.fullmatch(course_code):
            raise CalendarValidationError("Enter a valid course code, such as CMPT 141.")

    zone = parse_timezone(payload.get("timezone", payload.get("tz", DEFAULT_TIMEZONE)))
    reminder = payload.get("reminder_minutes")
    if reminder is not None and (type(reminder) is not int or not 0 <= reminder <= MAX_REMINDER_MINUTES):
        raise CalendarValidationError("Choose a reminder from 0 minutes to 7 days before the event.")

    all_day = payload.get("all_day", False)
    if type(all_day) is not bool:
        raise CalendarValidationError("All-day must be true or false.")
    if all_day:
        start = parse_date(payload.get("start"), "Start")
        end = parse_date(payload.get("end"), "End")
    else:
        start = _parse_timestamp(payload.get("start"), "Start")
        end = _parse_timestamp(payload.get("end"), "End")
    if end <= start:
        raise CalendarValidationError("The end must be after the start.")

    return {
        "title": title.strip(),
        "category": category,
        "description": description.strip(),
        "course_code": course_code,
        "timezone": zone.key,
        "reminder_minutes": reminder,
        "all_day": all_day,
        "start_date": start if all_day else None,
        "end_date": end if all_day else None,
        "start_at": start if not all_day else None,
        "end_at": end if not all_day else None,
    }


def create_event(payload: dict, *, import_key: str | None = None) -> CalendarEvent:
    """Insert an event in the caller's transaction."""
    event = CalendarEvent(**_event_fields(payload), import_key=import_key)
    db.session.add(event)
    db.session.flush()
    return event


def update_event(event: CalendarEvent, patch: dict) -> CalendarEvent:
    if not isinstance(patch, dict):
        raise CalendarValidationError("Send an event as a JSON object.")
    values = {**event.as_dict(), **patch}
    if "tz" in patch and "timezone" not in patch:
        values["timezone"] = patch["tz"]
    fields = _event_fields(values)
    for key, value in fields.items():
        setattr(event, key, value)
    return event


def list_events(start: str, end: str, tz: str = DEFAULT_TIMEZONE) -> list[CalendarEvent]:
    first = parse_date(start, "Range start")
    last = parse_date(end, "Range end")
    if not 1 <= (last - first).days <= 366:
        raise CalendarValidationError("Choose a date range of 1 to 366 days.")
    zone = parse_timezone(tz)
    lower = local_midnight(first, zone)
    upper = local_midnight(last, zone)
    events = db.session.scalars(db.select(CalendarEvent).where(or_(
        and_(CalendarEvent.all_day.is_(True), CalendarEvent.start_date < last, CalendarEvent.end_date > first),
        and_(CalendarEvent.all_day.is_(False), CalendarEvent.start_at < upper, CalendarEvent.end_at > lower),
    )))
    return sorted(
        events,
        key=lambda event: (
            local_midnight(event.start_date, zone) if event.all_day else event.start_at,
            not event.all_day,
            event.id,
        ),
    )


def upcoming_events(*, tz: str = DEFAULT_TIMEZONE, days: int = 30, now: datetime | None = None) -> list[CalendarEvent]:
    """Return events starting within a local window, excluding elapsed times."""
    zone = parse_timezone(tz)
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    day = instant.astimezone(zone).date()
    events = list_events(day.isoformat(), (day + timedelta(days=days)).isoformat(), tz)
    return [
        event for event in events
        if (event.start_date >= day if event.all_day else event.start_at >= instant.replace(tzinfo=None))
    ]
