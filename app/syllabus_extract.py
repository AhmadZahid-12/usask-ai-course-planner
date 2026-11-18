"""Conservative, line-based extraction of reviewable syllabus dates."""

from dataclasses import dataclass
from datetime import date
import hashlib
import re

from app.planner import normalize_code

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_EXACT_DATE = re.compile(
    rf"\b(?:(?P<iso_year>\d{{4}})-(?P<iso_month>\d{{2}})-(?P<iso_day>\d{{2}})"
    rf"|(?P<month_first>{_MONTH})\.?\s+(?P<day_after>{_DAY}),?\s+(?P<year_after>\d{{4}})"
    rf"|(?P<day_first>{_DAY})\s+(?P<month_after>{_MONTH})\.?,?\s+(?P<year_last>\d{{4}}))\b",
    re.IGNORECASE,
)
_PARTIAL_DATE = re.compile(
    rf"\b(?:{_MONTH}\.?\s+{_DAY}|{_DAY}\s+{_MONTH}\.?|\d{{1,4}}/\d{{1,2}}(?:/\d{{2,4}})?|\d{{4}}-\d{{2}}-\d{{2}})\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"(?<![\d:])(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>[ap]\.?\s*m\.?)\b"
    r"|(?<![\d:])(?P<hour24>\d{1,2}):(?P<minute24>\d{2})(?![\d:])",
    re.IGNORECASE,
)
_KIND = re.compile(
    r"\b(quiz(?:zes)?|midterms?|final\s+exam(?:ination)?s?|exams?|tests?|"
    r"assignments?|homework|projects?|essays?|papers?|problem\s+sets?|lab\s+reports?|presentations?|"
    r"deadlines?|reading\s+week|withdrawal|important\s+dates|class\s+cancelled)\b",
    re.IGNORECASE,
)
_REVIEW = re.compile(
    r"\b(?:tentative|possibly|provisional(?:ly)?|expected|approximately|around|"
    r"subject to change|TBA|TBD|to be (?:announced|confirmed|determined)|weeks?\s+\d+)\b",
    re.IGNORECASE,
)
_TIME_NOTE = re.compile(
    r"\b(?:noon|midnight|morning|afternoon|evening|time\s+TBA|"
    r"UTC|GMT|CST|CDT|EST|EDT|PST|PDT|MST|MDT|AST|ADT|ET|PT|CT|MT|"
    r"local time|[A-Za-z_]+/[A-Za-z_]+)\b|(?<=\d)\s*[+-]\d{2}:?\d{2}\b",
    re.IGNORECASE,
)
_DUE = re.compile(r"\b(?:due|deadline|exam|quiz|test|midterm)(?:\s+(?:on|by|at))?\b", re.IGNORECASE)
_RANGE = re.compile(r"\b\d{1,2}\s*(?:[-–—]|to)\s*\d{1,2}\b", re.IGNORECASE)
_INFERRED_COURSE = re.compile(r"\b(?:[A-Z]{2,5}\s*\d{3,4}[A-Z]?)(?:\.\d+)?\b")
_NON_SUBJECTS = {
    "APR", "AUG", "CLASS", "DATE", "DEC", "DUE", "EXAM", "FALL", "FEB", "FINAL",
    "ISBN", "JAN", "JUL", "JULY", "JUN", "JUNE", "MAR", "MAY", "NOV", "OCT",
    "ROOM", "SEP", "TERM", "TEST", "WEEK", "YEAR",
}
MAX_CANDIDATES = 75


@dataclass(frozen=True)
class SyllabusCandidate:
    title: str
    category: str
    course_code: str
    date: str
    time: str
    precision: str
    reason: str
    evidence: str
    page: int | None
    source_key: str


def _date_value(match: re.Match) -> str:
    try:
        if match["iso_year"]:
            result = date(int(match["iso_year"]), int(match["iso_month"]), int(match["iso_day"]))
        else:
            month = (match["month_first"] or match["month_after"])[:3].lower()
            day = re.match(r"\d+", match["day_after"] or match["day_first"])[0]
            result = date(int(match["year_after"] or match["year_last"]), _MONTHS[month], int(day))
        return result.isoformat()
    except ValueError:
        return ""


def _time_value(match: re.Match) -> str:
    if match["hour24"] is not None:
        hours = int(match["hour24"])
        minutes = int(match["minute24"])
    else:
        hours = int(match["hour"])
        minutes = int(match["minute"] or 0)
        if not 1 <= hours <= 12:
            return ""
        hours = hours % 12 + (12 if match["meridiem"].lower().startswith("p") else 0)
    return f"{hours:02d}:{minutes:02d}" if hours <= 23 and minutes <= 59 else ""


def _category(word: str) -> str:
    word = word.lower()
    if word.startswith("quiz"):
        return "quiz"
    if word.startswith(("midterm", "final exam", "exam", "test")):
        return "exam"
    if word.startswith(("deadline", "reading", "withdrawal", "important", "class")):
        return "personal"
    return "assignment"


def _title(line: str, kind: re.Match, schedule: re.Match | None) -> str:
    if schedule and schedule.start() > kind.start():
        title = line[:schedule.start()]
    elif schedule:
        title = line[kind.start():]
    else:
        title = line
    title = re.split(r"\b(?:is\s+due|due|deadline|TBA|TBD|(?:date\s+)?to be (?:announced|confirmed|determined)|tentative)\b", title, maxsplit=1, flags=re.IGNORECASE)[0]
    return title.strip(" .,:;–—-•")[:120] or kind[0].capitalize()


def _schedule(line: str, dates: list[re.Match], partial: list[re.Match]) -> tuple[str, str, str, str]:
    # A complete date mixed with a second date fragment can describe a range.
    if len(dates) != 1 or len(partial) > 1 or _REVIEW.search(line):
        reason = "The source is tentative or does not specify one complete date. Verify it before importing."
        return "", "", "ambiguous", reason
    chosen = dates[0]
    if _RANGE.search(line[:chosen.start()]) or (
        chosen["iso_year"] is None and _RANGE.search(line[chosen.start():])
    ):
        return "", "", "ambiguous", "The source appears to give a date range. Choose the correct date."
    day = _date_value(chosen)
    if not day:
        return "", "", "ambiguous", "The source date is invalid. Enter the correct date."

    clocks = list(_CLOCK.finditer(line))
    text_after_date = line[chosen.end():]
    if _TIME_NOTE.search(line) or len(clocks) > 1 or (
        not clocks and re.search(r"\b(?:at|by)\s+\d{1,2}\b", text_after_date, re.IGNORECASE)
    ):
        return day, "", "ambiguous", "The date is present, but the time or time zone needs verification."
    if clocks:
        when = _time_value(clocks[0])
        if not when:
            return day, "", "ambiguous", "The source time is invalid. Enter the correct time."
        return day, when, "timed", "Date and clock time found. Verify the time zone."
    return day, "", "date", "Date found without a time. Leave the time blank to import an all-day deadline."


def _course_codes(text: str) -> set[str]:
    candidates = {normalize_code(match[0]) for match in _INFERRED_COURSE.finditer(text)}
    return {code for code in candidates if code.split()[0] not in _NON_SUBJECTS}


def extract_candidates(pages: list[tuple[int | None, str]], course_code: str = "") -> list[SyllabusCandidate]:
    """Keep ambiguous dates blank and preserve the text that supports each suggestion."""
    document_codes = {code for _, text in pages for code in _course_codes(text)}
    inferred_code = course_code or (next(iter(document_codes)) if len(document_codes) == 1 else "")
    candidates = []
    seen: set[str] = set()
    for page, text in pages:
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line or len(line) > 700:
                continue
            kind = _KIND.search(line)
            if not kind:
                continue
            dates = list(_EXACT_DATE.finditer(line))
            partial = [match for match in _PARTIAL_DATE.finditer(line)
                       if not any(item.start() <= match.start() and match.end() <= item.end() for item in dates)]
            if not dates and not partial and not (_REVIEW.search(line) or _DUE.search(line[:55]) and len(line) < 80):
                continue
            source_key = hashlib.sha256(line.casefold().encode()).hexdigest()
            if source_key in seen:
                continue
            seen.add(source_key)
            day, clock, precision, reason = _schedule(line, dates, partial)
            line_codes = _course_codes(line)
            code = course_code or (next(iter(line_codes)) if len(line_codes) == 1 else inferred_code)
            candidates.append(SyllabusCandidate(
                title=_title(line, kind, (dates or partial or [None])[0]),
                category=_category(kind[0]), course_code=code, date=day, time=clock,
                precision=precision, reason=reason, evidence=line[:500], page=page,
                source_key=source_key,
            ))
            if len(candidates) == MAX_CANDIDATES:
                return candidates
    return candidates
