"""Parse catalogue prerequisites and evaluate them against completed courses."""

import re
from collections import deque
from collections.abc import Mapping, Set
from typing import TypedDict

_COURSE_CODE = r"([A-Z]{2,5})\s*([0-9]{2,4}[A-Z]?)(?:\.[0-9]+)?"
COURSE_RE = re.compile(rf"\b{_COURSE_CODE}\b")
_PREREQUISITE = r"Pre[- ]?requisite(?:\(s\)|s)?"
_COREQUISITE = r"Co[- ]?requisite(?:\(s\)|s)?"
_COMBINED_HEADING = rf"{_PREREQUISITE}\s*(?:or|/)\s*{_COREQUISITE}"
_SECTION_RE = re.compile(
    rf"\b{_PREREQUISITE}\s*:\s*(.*?)"
    rf"(?=\b(?:Notes?|{_COREQUISITE}|{_COMBINED_HEADING}|Restrictions?)\s*:"
    r"|\bCosts in addition\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_COMBINED_SECTION_RE = re.compile(rf"\b{_COMBINED_HEADING}\s*:", re.IGNORECASE)
_TOKEN_RE = re.compile(
    rf"{COURSE_RE.pattern}|;?\b(?:AND|OR)\b|\b(?:ONE OF|EITHER)\b|\S"
)
_MAX_ALTERNATIVES = 256

PrerequisiteGroups = list[list[str]]


class CourseInfo(TypedDict, total=False):
    prereqs: PrerequisiteGroups | None
    not_found: bool
    raw_text: str
    source_url: str


class LockedCourse(TypedDict):
    course: str
    missing: list[str]


class LockedCourseWithReason(LockedCourse, total=False):
    reason: str


def normalize_code(code: str | None) -> str:
    """Return the course identifier without the catalogue credit-unit suffix."""
    cleaned = " ".join((code or "").upper().split())
    match = COURSE_RE.fullmatch(cleaned)
    if match:
        return f"{match[1]} {match[2]}"
    return cleaned


def extract_prereq_line(raw_text: str) -> str | None:
    """Return the prerequisite section, or None when there is no heading."""
    match = _SECTION_RE.search(raw_text)
    return match[1].strip() if match else None


class _PrerequisiteParser:
    """Parse course expressions directly into alternatives of required courses."""

    def __init__(self, text: str) -> None:
        text = re.sub(r",\s*(?=(?:AND|OR)\b)", " ", text)
        text = re.sub(r";\s*(?=(?:AND|OR)\b)", ";", text)
        self.tokens = deque(match[0] for match in _TOKEN_RE.finditer(text))

    def _accept(self, *choices: str) -> bool:
        if self.tokens and self.tokens[0] in choices:
            self.tokens.popleft()
            return True
        return False

    def _course(self) -> str:
        if not self.tokens or not COURSE_RE.fullmatch(self.tokens[0]):
            raise ValueError("Expected a course code")
        return normalize_code(self.tokens.popleft())

    def _close_group(self) -> None:
        if not self._accept(")"):
            raise ValueError("Expected a closing parenthesis")

    def _term(self) -> PrerequisiteGroups:
        if self._accept("ONE OF"):
            parenthesized = self._accept("(")
            alternatives = [[self._course()]]
            while self._accept(",", "OR"):
                alternatives.append([self._course()])
            if parenthesized:
                self._close_group()
            return alternatives

        if self._accept("("):
            groups = self._expression()
            self._close_group()
            return groups

        return [[self._course()]]

    def _conjunction(self) -> PrerequisiteGroups:
        groups = self._term()
        while self._accept("AND", ";AND"):
            following = self._term()
            if len(groups) * len(following) > _MAX_ALTERNATIVES:
                raise ValueError("Too many prerequisite alternatives")
            groups = [left + right for left in groups for right in following]
        return groups

    def _expression(self) -> PrerequisiteGroups:
        either = self._accept("EITHER")
        groups = self._conjunction()
        has_alternative = False
        while self._accept("OR", ";OR"):
            has_alternative = True
            groups.extend(self._conjunction())
            if len(groups) > _MAX_ALTERNATIVES:
                raise ValueError("Too many prerequisite alternatives")
        if either and not has_alternative:
            raise ValueError("Expected an alternative after either")
        return groups

    def parse(self) -> PrerequisiteGroups:
        # Bound nesting and work on catalogue text with unusually large expressions.
        if len(self.tokens) > _MAX_ALTERNATIVES:
            raise ValueError("Prerequisite expression is too long")
        groups = self._expression()
        if self.tokens:
            raise ValueError("Unsupported prerequisite wording")
        return [list(dict.fromkeys(group)) for group in groups]


def parse_prereqs(raw_text: str | None) -> PrerequisiteGroups | None:
    """Return OR-of-AND course groups, or None if manual verification is needed."""
    if not raw_text or not raw_text.strip() or _COMBINED_SECTION_RE.search(raw_text):
        return None

    section = extract_prereq_line(raw_text)
    if section is None:
        return []

    text = " ".join(section.removesuffix(".").upper().split())
    if text in {"NONE", "NONE REQUIRED"}:
        return []

    try:
        return _PrerequisiteParser(text).parse()
    except ValueError:
        return None


def _missing_prereqs(
    groups: PrerequisiteGroups, completed: Set[str]
) -> list[str]:
    missing_options = (
        {normalize_code(code) for code in group} - completed for group in groups
    )
    return sorted(min(missing_options, key=len, default=set()))


def prereqs_satisfied(
    prereq_groups: PrerequisiteGroups | None, completed: Set[str]
) -> bool:
    """Check whether a course-only prerequisite alternative is complete."""
    return prereq_groups is not None and not missing_prereqs(prereq_groups, completed)


def missing_prereqs(
    prereq_groups: PrerequisiteGroups, completed: Set[str]
) -> list[str]:
    """Return the missing courses from the closest alternative."""
    return _missing_prereqs(prereq_groups, {normalize_code(code) for code in completed})


def classify_courses(
    course_map: Mapping[str, CourseInfo], completed: Set[str]
) -> tuple[list[str], list[LockedCourseWithReason]]:
    """List unlocked and locked courses, excluding completed courses."""
    completed_codes = {normalize_code(code) for code in completed}
    unlocked: list[str] = []
    locked: list[LockedCourseWithReason] = []
    for code, data in course_map.items():
        code = normalize_code(code)
        if code in completed_codes:
            continue

        groups = data.get("prereqs")
        if data.get("not_found"):
            locked.append({
                "course": code,
                "missing": [],
                "reason": "Manual verification needed: catalogue information is unavailable.",
            })
        elif groups is None:
            locked.append({
                "course": code,
                "missing": [],
                "reason": "Manual verification needed: check the catalogue prerequisites.",
            })
        elif missing := _missing_prereqs(groups, completed_codes):
            locked.append({"course": code, "missing": missing})
        else:
            unlocked.append(code)

    return sorted(unlocked), sorted(locked, key=lambda item: item["course"])


def unlocked_courses(
    course_map: Mapping[str, CourseInfo], completed: Set[str]
) -> list[str]:
    return classify_courses(course_map, completed)[0]


def locked_courses_with_reasons(
    course_map: Mapping[str, CourseInfo], completed: Set[str]
) -> list[LockedCourseWithReason]:
    return classify_courses(course_map, completed)[1]
