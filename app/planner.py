# app/planner.py
import re
from typing import Dict, List, Set, Tuple, Any

COURSE_RE = re.compile(r"\b([A-Z]{2,5})\s*([0-9]{2,4}[A-Z]?)\b")


def normalize_code(code: str) -> str:
    code = (code or "").strip().upper()
    code = re.sub(r"\s+", " ", code)

    m = re.match(r"^([A-Z]{2,5})\s*([0-9]{2,4}[A-Z]?)$", code)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    m2 = re.match(r"^([A-Z]{2,5})([0-9]{2,4}[A-Z]?)$", code.replace(" ", ""))
    if m2:
        return f"{m2.group(1)} {m2.group(2)}"

    return code


def extract_prereq_line(raw_text: str) -> str:
    if not raw_text:
        return ""
    m = re.search(
        r"Prerequisite\(s\)\s*:\s*(.*?)(?:Note:|Costs in addition|$)",
        raw_text,
        re.IGNORECASE,
    )
    if not m:
        return ""
    return m.group(1).strip()


def parse_prereqs(raw_text: str) -> List[List[str]]:
    """
    Returns prereqs as OR-of-AND groups:
      [
        ["CMPT 145", "MATH 110"],   # group 1 (AND)
        ["CMPT 115"]               # group 2 (AND)
      ]
    Meaning: (CMPT145 AND MATH110) OR (CMPT115)
    """
    line = extract_prereq_line(raw_text)
    if not line:
        return []

    cleaned = re.sub(r"\s+", " ", line)
    or_parts = re.split(r"\b(or|either)\b", cleaned, flags=re.IGNORECASE)

    groups: List[List[str]] = []
    current: List[str] = []

    def flush_current():
        nonlocal current
        if current:
            seen = set()
            out = []
            for c in current:
                if c not in seen:
                    out.append(c)
                    seen.add(c)
            groups.append(out)
            current = []

    for part in or_parts:
        p = part.strip().lower()
        if p in ("or", "either"):
            flush_current()
            continue

        found = COURSE_RE.findall(part.upper())
        codes = [normalize_code(f"{subj} {num}") for subj, num in found]
        if codes:
            current.extend(codes)

    flush_current()
    return groups


def prereqs_satisfied(prereq_groups: List[List[str]], completed: Set[str]) -> bool:
    if not prereq_groups:
        return True

    completed_norm = {normalize_code(c) for c in completed}

    for group in prereq_groups:
        group_norm = [normalize_code(c) for c in group]
        if all(c in completed_norm for c in group_norm):
            return True
    return False


def unlocked_courses(course_map: Dict[str, Dict[str, Any]], completed: Set[str]) -> List[str]:
    unlocked = []
    completed_norm = {normalize_code(c) for c in completed}

    for code, data in course_map.items():
        code_norm = normalize_code(code)
        if code_norm in completed_norm:
            continue
        prereq_groups = data.get("prereqs", [])
        if prereqs_satisfied(prereq_groups, completed_norm):
            unlocked.append(code_norm)

    return sorted(unlocked)


def missing_prereqs(prereq_groups: List[List[str]], completed: Set[str]) -> List[str]:
    """
    If prereqs satisfied -> []
    If not satisfied -> return the 'closest' option (smallest missing set) for a helpful explanation.
    """
    if not prereq_groups:
        return []

    completed_norm = {normalize_code(c) for c in completed}

    # if any satisfied, no missing
    for group in prereq_groups:
        group_norm = [normalize_code(c) for c in group]
        if all(c in completed_norm for c in group_norm):
            return []

    # otherwise, pick the group with the fewest missing courses
    best_missing: List[str] | None = None
    for group in prereq_groups:
        group_norm = [normalize_code(c) for c in group]
        missing = [c for c in group_norm if c not in completed_norm]
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing

    return sorted(best_missing or [])


def locked_courses_with_reasons(course_map: Dict[str, Dict[str, Any]], completed: Set[str]) -> List[Dict[str, Any]]:
    """
    Returns:
      [{"course": "CMPT 332", "missing": ["CMPT 214"]}, ...]
    """
    locked: List[Dict[str, Any]] = []
    completed_norm = {normalize_code(c) for c in completed}

    for code, data in course_map.items():
        code_norm = normalize_code(code)
        if code_norm in completed_norm:
            continue

        prereq_groups = data.get("prereqs", [])
        if prereqs_satisfied(prereq_groups, completed_norm):
            continue

        missing = missing_prereqs(prereq_groups, completed_norm)
        locked.append({"course": code_norm, "missing": missing})

    return sorted(locked, key=lambda x: x["course"])