import io
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import create_app
from app.db import db
from app.syllabus_extract import extract_candidates
from app.syllabus_files import MAX_UPLOAD_BYTES, SyllabusFileError, read_document

_SAMPLE = """CMPT 141
Assignment 1 due November 20, 2026 at 11:59 p.m.
Quiz 2 21 November 2026
Final exam November 27
Midterm November 25–26, 2026
Quiz 3 2026-12-03 at 18:00 CST
"""


def _pdf_bytes(content: str | None = None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    if content:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 30 350 Td ({content}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class SyllabusParsingTests(unittest.TestCase):
    def test_exact_date_only_tentative_and_ambiguous_clock(self):
        assignment, quiz, missing_year, date_range, ambiguous_clock = extract_candidates([(None, _SAMPLE)])
        self.assertEqual(
            (assignment.title, assignment.course_code, assignment.date, assignment.time, assignment.precision),
            ("Assignment 1", "CMPT 141", "2026-11-20", "23:59", "timed"),
        )
        self.assertEqual((quiz.date, quiz.precision), ("2026-11-21", "date"))
        self.assertEqual((missing_year.date, date_range.date), ("", ""))
        self.assertEqual((ambiguous_clock.date, ambiguous_clock.time, ambiguous_clock.precision),
                         ("2026-12-03", "", "ambiguous"))

    def test_tentative_date_label_is_not_part_of_title(self):
        [candidate] = extract_candidates([(1, "Quiz 3: date to be announced")])
        self.assertEqual((candidate.title, candidate.date, candidate.precision), ("Quiz 3", "", "ambiguous"))

    def test_pdf_extracts_text_with_page_numbers_and_flags_scans(self):
        pages = read_document(_pdf_bytes("Assignment 1 due 2026-11-20"), ".pdf")
        candidate = extract_candidates(pages, "CMPT 141")[0]
        self.assertEqual((candidate.page, candidate.date), (1, "2026-11-20"))
        with self.assertRaisesRegex(SyllabusFileError, "No selectable text"):
            read_document(_pdf_bytes(), ".pdf")

    def test_unsupported_and_oversized_files_rejected(self):
        with self.assertRaisesRegex(SyllabusFileError, "up to 4 MB"):
            read_document(b"a" * (MAX_UPLOAD_BYTES + 1), ".txt")
        with self.assertRaisesRegex(SyllabusFileError, "valid PDF header"):
            read_document(b"not pdf", ".pdf")
        with self.assertRaisesRegex(SyllabusFileError, "PDF or UTF-8 text"):
            read_document(b"text", ".docx")


class SyllabusApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name, "test.db")
        self.settings = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.database}",
            "SECRET_KEY": "disposable-test-key",
        }
        self.app = create_app(self.settings)
        with self.app.app_context():
            db.create_all()
        self.client = self.app.test_client()

    def preview(self, text=_SAMPLE, filename="syllabus.txt"):
        response = self.client.post(
            "/api/syllabus/preview",
            data={"syllabus": (io.BytesIO(text.encode()), filename), "course_code": "CMPT 141"},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["candidates"]

    def calendar(self):
        return self.client.get("/api/calendar/events?start=2026-11-01&end=2027-01-01").json["events"]

    def test_preview_writes_nothing_and_only_approved_candidate_persists(self):
        proposed = self.preview()
        self.assertEqual(self.calendar(), [])
        reviewed = {**proposed[0], "title": "Assignment work", "timezone": "America/Regina"}
        response = self.client.post("/api/syllabus/approve", json={"events": [reviewed]})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(response.json["events"]), 1)
        [added] = self.calendar()
        self.assertEqual((added["start"], added["title"]), ("2026-11-21T05:59:00Z", "Assignment work"))
        self.assertIn("Assignment 1 due November 20", added["description"])

    def test_minute_before_midnight_does_not_add_a_second_due_day(self):
        [proposal] = self.preview("Assignment due November 20, 2026 at 11:59 PM")
        response = self.client.post("/api/syllabus/approve", json={"events": [proposal]})
        self.assertEqual(response.status_code, 200, response.json)
        [added] = response.json["events"]
        self.assertTrue(added["deadline"])
        self.assertEqual(added["end"], "2026-11-21T06:00:00Z")
        following_day = self.client.get(
            "/api/calendar/events?start=2026-11-21&end=2026-11-22&tz=America%2FRegina"
        )
        self.assertEqual(following_day.json, {"events": []})

    def test_ambiguous_or_forged_proposals_are_not_saved(self):
        proposed = self.preview()
        ambiguous = proposed[2]
        forged = {**proposed[0], "token": "false"}
        for rejected in (ambiguous, forged):
            response = self.client.post("/api/syllabus/approve", json={"events": [proposed[0], rejected]})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.calendar(), [])

    def test_duplicate_from_reupload_after_app_restart(self):
        original = self.preview()[1]
        first = self.client.post("/api/syllabus/approve", json={"events": [original]})
        self.assertEqual(first.json["duplicate_count"], 0)
        self.client = create_app(self.settings).test_client()
        reviewed = {**self.preview(filename="renamed.txt")[1], "title": "Edited title"}
        second = self.client.post("/api/syllabus/approve", json={"events": [reviewed]})
        self.assertEqual(second.json, {"events": [], "duplicate_count": 1})
        [added] = self.calendar()
        self.assertTrue(added["all_day"])
        self.assertEqual(added["end"], "2026-11-22")

    def test_reviewed_time_in_dst_gap_is_rejected(self):
        [proposal] = self.preview("Midterm 2026-03-08 at 02:30")
        response = self.client.post(
            "/api/syllabus/approve", json={"events": [{**proposal, "timezone": "America/Toronto"}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("daylight saving", response.json["error"])

    def test_selected_zone_is_preserved_with_the_event(self):
        [proposal] = self.preview("Midterm 2026-11-14 at 14:30")
        response = self.client.post(
            "/api/syllabus/approve", json={"events": [{**proposal, "timezone": "America/Toronto"}]},
        )
        self.assertEqual(response.status_code, 200, response.json)
        [added] = self.calendar()
        self.assertEqual((added["start"], added["timezone"]), ("2026-11-14T19:30:00Z", "America/Toronto"))
