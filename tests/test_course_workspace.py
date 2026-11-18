import io
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import create_app
from app.student_migrations import upgrade_student_schema


class CourseWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        with self.app.app_context():
            self.assertEqual(upgrade_student_schema(), [1, 2])
        self.client = self.app.test_client()

    def add_course(self, code="CMPT 141"):
        response = self.client.post("/student/courses", data={"code": code})
        self.assertEqual(response.status_code, 303)
        return response.headers["Location"]

    def test_course_notes_and_local_material_search(self):
        course = self.add_course()
        self.assertIn(b"Introduction to Computer Science", self.client.get(course).data)
        response = self.client.post(course + "/notes", data={"title": "CS I", "notes": "Study recursion."})
        self.assertEqual(response.status_code, 303)
        self.assertIn(b"Study recursion.", self.client.get(course).data)
        self.assertEqual(self.client.post("/student/courses", data={"code": "cmpt141.3"}).status_code, 422)

        for expected in (303, 422):
            upload = self.client.post(course + "/materials", data={
                "material": (io.BytesIO(b"Induction overview and worksheet."), "study.txt")
            })
            self.assertEqual(upload.status_code, expected)
        self.assertIn(b"study.txt", self.client.get(course + "?q=induction").data)
        self.assertNotIn(b"study.txt", self.client.get(course + "?q=unrelated").data)

        material_url = course + "/materials/1"
        self.assertIn("attachment", self.client.get(material_url).headers["Content-Disposition"])
        other = self.add_course("CMPT 145")
        self.assertEqual(self.client.get(other + "/materials/1").status_code, 404)
        self.assertEqual(self.client.post(material_url + "/remove").status_code, 400)
        self.assertEqual(self.client.post(material_url + "/remove", data={"confirmed": "yes"}).status_code, 303)
        self.assertEqual(self.client.get(material_url).status_code, 404)

    def test_agenda_and_dashboard_use_saved_events(self):
        course = self.add_course()
        today = datetime.now(ZoneInfo("America/Regina")).date()
        tomorrow = today + timedelta(days=1)
        following_day = tomorrow + timedelta(days=1)
        exam = {
            "title": "Recursion exam", "category": "exam", "course_code": "CMPT 141",
            "start": tomorrow.isoformat(), "end": following_day.isoformat(), "all_day": True,
        }
        self.assertEqual(self.client.post("/api/calendar/events", json=exam).status_code, 201)
        for url in ("/", course, "/student/agenda?view=week", "/student/agenda?view=exams"):
            self.assertIn(b"Recursion exam", self.client.get(url).data, url)
        self.assertNotIn(b"Recursion exam", self.client.get("/student/agenda?view=today").data)

    def test_external_origin_cannot_change_student_storage(self):
        response = self.client.post(
            "/student/courses", data={"code": "CMPT 141"}, headers={"Origin": "https://other.example"}
        )
        self.assertEqual(response.status_code, 403)

    def test_personal_workspace_pages_disable_response_caching(self):
        course = self.add_course()
        for path in ("/", course, "/syllabus", "/student/agenda"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("no-store", response.headers["Cache-Control"], path)
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
