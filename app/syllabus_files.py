"""Bounded local extraction for supported syllabus and study files."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_TEXT_CHARS = 250_000


class SyllabusFileError(ValueError):
    """A document cannot be read within the supported format or limits."""


def read_document(data: bytes, suffix: str) -> list[tuple[int | None, str]]:
    """Return plain text with a page number for each PDF page."""
    if not data:
        raise SyllabusFileError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise SyllabusFileError("Choose a file up to 4 MB.")

    if suffix.lower() == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SyllabusFileError("Save the text file as UTF-8 and try again.") from None
        if any(ord(character) < 32 and character not in "\r\n\t\f" for character in text):
            raise SyllabusFileError("The file contains binary data. Choose a plain-text file.")
        if not text.strip():
            raise SyllabusFileError("The file has no readable text.")
        if len(text) > MAX_TEXT_CHARS:
            raise SyllabusFileError("This file has too much text. Try a shorter syllabus.")
        return [(None, text)]

    if suffix.lower() != ".pdf":
        raise SyllabusFileError("Choose a PDF or UTF-8 text file.")
    if not data.startswith(b"%PDF-"):
        raise SyllabusFileError("The file does not have a valid PDF header.")

    package = importlib.util.find_spec("pypdf")
    if not package or not package.origin:
        raise SyllabusFileError("PDF reading is unavailable. Install the app dependencies or choose a text file.")

    # Keep parser CPU and memory outside the web process, and leave secrets out of its environment.
    environment = {"PYTHONPATH": str(Path(package.origin).resolve().parent.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    try:
        process = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("syllabus_pdf.py"))],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=7,
            check=True,
            env=environment,
            cwd=Path(__file__).parent,
        )
        result = json.loads(process.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        raise SyllabusFileError("This PDF could not be read within the extraction limits. Try a smaller text-based PDF.") from None
    if "error" in result:
        raise SyllabusFileError(result["error"])
    return [(number, text) for number, text in result["pages"]]
