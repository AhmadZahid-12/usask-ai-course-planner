"""University of Saskatchewan catalogue URLs and bundled program data."""

import json
from functools import cache
from pathlib import Path

CATALOGUE_BASE = "https://catalogue.usask.ca"
PROGRAM_URL = "https://programs.usask.ca/arts-and-science/computer-science/bsc-4-computer-science.php"
DATA_DIR = Path(__file__).resolve().parents[1] / "degree"
DEGREE_FILE = DATA_DIR / "bsc_cs.json"


def catalogue_url(code: str) -> str:
    return f"{CATALOGUE_BASE}/{code.replace(' ', '-')}"


@cache
def starter_catalogue() -> dict:
    return json.loads((DATA_DIR / "starter_catalogue.json").read_text(encoding="utf-8"))


@cache
def cmpt_catalogue() -> dict:
    return json.loads((DATA_DIR / "cmpt_catalogue.json").read_text(encoding="utf-8"))
