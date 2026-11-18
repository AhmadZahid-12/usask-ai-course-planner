"""
scraper.py
Fetch OFFICIAL course descriptions from the USask catalogue.
NO guessing. NO OpenAI calls here.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from app.planner import normalize_code as normalize_course_code

CATALOGUE_BASE = "https://catalogue.usask.ca"

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
TIMEOUT = 15


# Cache utilities
def _cache_path(course_code: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", course_code)
    return CACHE_DIR / f"{safe}.json"


def _read_cache(course_code: str) -> Optional[Dict[str, Any]]:
    p = _cache_path(course_code)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        age = time.time() - float(data.get("saved_at", 0))
    except (OSError, ValueError, TypeError):
        return None
    ttl = 60 * 5 if data.get("error") else CACHE_TTL_SECONDS
    if age > ttl:
        return None
    return data


def _write_cache(course_code: str, payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload["saved_at"] = time.time()
    temp_path = None
    try:
        with NamedTemporaryFile(dir=CACHE_DIR, encoding="utf-8", mode="w", delete=False) as file:
            temp_path = Path(file.name)
            json.dump(payload, file)
        temp_path.replace(_cache_path(course_code))
    except OSError:
        # The catalogue response remains usable when the on-disk cache is unavailable.
        pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def course_url(course_code: str) -> str:
    """Generate catalogue URL from course code"""
    slug = normalize_course_code(course_code).replace(" ", "-")
    return f"{CATALOGUE_BASE}/{slug}"


# Extraction

def extract_description(html: str) -> str:
    """Extract course description from USask catalogue HTML."""
    return _description(BeautifulSoup(html, "html.parser"))


def _description(soup: BeautifulSoup) -> str:
    desc_section = soup.find(id="Description")
    if not desc_section:
        return ""

    paragraphs = desc_section.find_all("p")
    if not paragraphs:
        return ""

    parts = []
    for p in paragraphs:
        text = p.get_text(" ", strip=True)
        if text:
            parts.append(text)

    return " ".join(parts).strip()


# Main scraping function

def scrape_course_page(course_code: str) -> Dict[str, Any]:
    """Scrape a single course page from USask catalogue."""
    url = course_url(course_code)

    try:
        r = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )

        if r.status_code == 404:
            return {
                "course_code": normalize_course_code(course_code),
                "source_url": url,
                "raw_text": "",
                "not_found": True,
            }

        r.raise_for_status()

    except requests.RequestException as e:
        return {
            "course_code": normalize_course_code(course_code),
            "source_url": url,
            "raw_text": "",
            "not_found": True,
            "error": str(e),
        }

    soup = BeautifulSoup(r.text, "html.parser")
    desc = _description(soup)
    heading = soup.select_one("h1")
    title = soup.select_one("h1 + .lead")
    units = None
    if heading and normalize_course_code(heading.get_text(" ", strip=True)) == normalize_course_code(course_code):
        credit = re.search(r"\.(\d+)$", heading.get_text(" ", strip=True))
        units = int(credit[1]) if credit else None
    else:
        title = None

    return {
        "course_code": normalize_course_code(course_code),
        "source_url": url,
        "raw_text": desc[:6000],
        "title": title.get_text(" ", strip=True) if title else None,
        "credit_units": units,
        "retrieved": datetime.now(timezone.utc).date().isoformat(),
        "not_found": not bool(desc),
    }


def get_cached_course(course_code: str) -> Optional[Dict[str, Any]]:
    """Read fresh catalogue cache metadata without contacting USask."""
    return _read_cache(normalize_course_code(course_code))


def get_course_raw_info(course_code: str) -> Dict[str, Any]:
    """Get course info with caching."""
    course_code = normalize_course_code(course_code)

    cached = _read_cache(course_code)
    if cached:
        cached["from_cache"] = True
        # Ensure key exists for callers
        cached.setdefault("not_found", not bool((cached.get("raw_text") or "").strip()))
        return cached

    payload = scrape_course_page(course_code)
    payload["from_cache"] = False
    _write_cache(course_code, payload)
    return payload
