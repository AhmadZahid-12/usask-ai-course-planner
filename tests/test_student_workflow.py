import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from app.db import db
from app.student_migrations import upgrade_student_schema


class StudentWorkflowTests(unittest.TestCase):
    def test_approved_syllabus_connects_course_calendar_and_read_only_assistant(self):
        with tempfile.TemporaryDirectory() as directory:
            uri = f"sqlite:///{Path(directory) / 'workflow.db'}"
            config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri, "SECRET_KEY": "test"}
            app = create_app(config)
            with app.app_context():
                upgrade_student_schema()
            client = app.test_client()
            created = client.post("/student/courses", data={"code": "cmpt141"})
            self.assertEqual(created.status_code, 303)
            course = created.headers["Location"]
            self.assertIn(b"/syllabus?course_code=CMPT+141", client.get(course).data)

            now = datetime.now(ZoneInfo("America/Regina"))
            tomorrow = (now + timedelta(days=1)).date()
            syllabus = f"Research outline due {tomorrow.isoformat()} at 11:59 PM\nQuiz date TBA\nCancelled due to weather on {tomorrow.isoformat()}"
            preview = client.post("/api/syllabus/preview", data={
                "syllabus": (io.BytesIO(syllabus.encode()), "syllabus.txt"),
                "course_code": "CMPT 141",
            })
            self.assertEqual(preview.status_code, 200)
            events_url = f"/api/calendar/events?start={tomorrow}&end={tomorrow + timedelta(days=1)}"
            self.assertEqual(client.get(events_url).json, {"events": []})
            self.assertEqual(len(preview.json["candidates"]), 2)
            candidate = preview.json["candidates"][0]
            self.assertEqual((candidate["title"], candidate["category"]), ("Research outline", "personal"))
            approved = client.post("/api/syllabus/approve", json={
                "events": [{**candidate, "timezone": "America/Regina"}],
            })
            self.assertEqual(approved.status_code, 200, approved.json)
            self.assertEqual(len(approved.json["events"]), 1)

            rejected_note = client.post(course + "/notes", data={
                "title": " ", "notes": "Draft notes I intend to keep",
            })
            self.assertEqual(rejected_note.status_code, 422)
            self.assertIn(b"Draft notes I intend to keep", rejected_note.data)
            self.assertNotIn(b"Draft notes I intend to keep", client.get(course).data)
            self.assertEqual(client.post(course + "/notes", data={
                "title": "Computer Science", "notes": "Saved review notes",
            }).status_code, 303)
            self.assertEqual(client.post(course + "/materials", data={
                "material": (io.BytesIO(b"Practice recursion and tracing."), "worksheet.txt"),
            }).status_code, 303)

            with app.app_context():
                db.engine.dispose()
            client = create_app(config).test_client()
            stored = client.get(events_url).json
            self.assertEqual(len(stored["events"]), 1)
            self.assertIn(b"Research outline", client.get(course).data)
            self.assertIn(b"Research outline", client.get("/").data)
            self.assertIn(b"Saved review notes", client.get(course).data)
            self.assertIn(b"worksheet.txt", client.get(course + "?q=tracing").data)
            self.assertNotIn(b"worksheet.txt", client.get(course + "?q=unrelated").data)
            with patch("app.gpt_helper._get_client", side_effect=AssertionError("External calls not allowed")):
                advice = client.get("/student/agenda?view=week")
            self.assertIn(b">Deadline</span>", advice.data)
            self.assertIn(b"earliest saved deadline", advice.data)
            self.assertEqual(client.get(events_url).json, stored)
