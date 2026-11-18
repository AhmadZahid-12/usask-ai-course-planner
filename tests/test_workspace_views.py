import unittest

from bs4 import BeautifulSoup

from app import create_app
from app.db import db


class WorkspaceViewsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        with self.app.app_context():
            db.create_all()
        self.client = self.app.test_client()

    def page(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return BeautifulSoup(response.data, "html.parser")

    def test_dashboard_scopes_progress_and_exposes_course_credits(self):
        page = self.page("/")
        self.assertIn("Starter template", page.select_one(".overview").get_text(" "))
        self.assertEqual(page.select_one("progress")["aria-label"], "Starter template progress")
        self.assertEqual(len(page.select("#dashboard-courses .course-identity")), 7)
        self.assertIn("3 cu", page.select_one("#dashboard-courses .course-units").get_text())

    def test_explorer_places_prerequisites_before_description(self):
        page = self.page("/courses")
        details = page.select_one("#course-details")
        self.assertIsNotNone(details.select_one("#back-to-results"))
        headings = [node.get_text() for node in details.select("h3, summary")]
        self.assertEqual(headings, ["Prerequisites", "Catalogue description"])
        result_template = page.select_one("template#course-result")
        self.assertIsNotNone(result_template)
        self.assertIsNotNone(result_template.select_one(".course-identity"))

    def test_planner_places_workspace_before_saved_plan_tools(self):
        page = self.page("/planner")
        titles = [heading.get_text() for heading in page.select(".planner-grid h2")]
        self.assertEqual(titles, ["Completed courses", "Semester draft", "Saved progress"])
        dialog = page.select_one("#import-dialog")
        self.assertIsNotNone(dialog.select_one('label[for="plan-file"]'))
        self.assertEqual(dialog.select_one("#import-error")["role"], "alert")
        self.assertIsNotNone(dialog.select_one(".dialog-footer #submit-import"))

    def test_font_is_served_locally(self):
        page = self.page("/")
        source = page.select_one('link[rel="preload"][as="font"]')["href"]
        self.assertTrue(source.startswith("/static/fonts/"))
        with self.client.get(source) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data[:4], b"wOF2")
