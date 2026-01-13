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
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

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
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    if time.time() - data.get("saved_at", 0) > CACHE_TTL_SECONDS:
        return None
    return data


def _write_cache(course_code: str, payload: Dict[str, Any]) -> None:
    payload = dict(payload)
    payload["saved_at"] = time.time()
    _cache_path(course_code).write_text(json.dumps(payload, indent=2))


# Helpers
def normalize_course_code(code: str) -> str:
    """Normalize course code to format: 'CMPT 214'"""
    code = (code or "").strip().upper()
    m = re.match(r"^([A-Z]{2,5})\s*([0-9]{2,4}[A-Z]?)$", code.replace(" ", ""))
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return code


def course_url(course_code: str) -> str:
    """Generate catalogue URL from course code"""
    slug = normalize_course_code(course_code).replace(" ", "-")
    return f"{CATALOGUE_BASE}/{slug}"


# Extraction

def extract_description(html: str) -> str:
    """Extract course description from USask catalogue HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Find the Description section by ID
    desc_section = soup.find(id="Description")
    if not desc_section:
        return ""

    # Extract all paragraphs in the Description section
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

    desc = extract_description(r.text)

    return {
        "course_code": normalize_course_code(course_code),
        "source_url": url,
        "raw_text": desc[:6000],
        "not_found": not bool(desc),
    }


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