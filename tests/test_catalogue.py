import unittest
from unittest.mock import Mock, patch

from flask import Flask

from app.db import db
from app.models import CourseCache, Plan
from app.routes import bp
from app.scraper import scrape_course_page


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        app = Flask("app")
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(app)
        app.register_blueprint(bp)
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            db.session.add(Plan(name="Test plan", completed_json='["CMPT 145"]'))
            db.session.add(CourseCache(code="CMPT 210", raw_text="Prerequisite: CMPT 145 and MATH 110."))
            db.session.commit()

    def test_dashboard_and_explorer_render_real_catalogue_index(self):
        dashboard = self.client.get("/")
        explorer = self.client.get("/courses")
        self.assertIn(b"Starter template", dashboard.data)
        self.assertIn(b"CMPT 317", explorer.data)
        self.assertIn(b"CMPT 210", explorer.data)
        self.assertIn(b"2026-11-18", explorer.data)

    def test_course_detail_uses_saved_progress_and_explains_missing_courses(self):
        response = self.client.get("/api/catalogue/course", query_string={"code": "cmpt210.3"})
        self.assertEqual(response.status_code, 200)
        course = response.get_json()
        self.assertEqual(course["status"], "locked")
        self.assertEqual(course["missing"], ["MATH 110"])
        self.assertEqual(course["source_url"], "https://catalogue.usask.ca/CMPT-210")

    @patch("app.services.get_course_raw_info", return_value={"not_found": True})
    def test_unavailable_catalogue_does_not_unlock_course(self, fetch):
        response = self.client.get("/api/catalogue/course?code=MATH110")
        self.assertEqual(response.get_json()["status"], "review")
        self.assertFalse(response.get_json()["available"])
        self.assertEqual(self.client.get("/api/catalogue/course?code=../admin").status_code, 400)
        fetch.assert_called_once_with("MATH 110")

    @patch("app.scraper.requests.get")
    def test_scraper_reads_course_title_and_verified_credit_units(self, fetch):
        fetch.return_value = Mock(status_code=200, text="""
            <h1>MATH 133.4</h1><p class="lead">Calculus</p>
            <section id="Description"><p>Description from the catalogue.</p></section>
        """)
        course = scrape_course_page("MATH 133")
        self.assertEqual(course["credit_units"], 4)
        self.assertEqual(course["title"], "Calculus")
        self.assertEqual(course["raw_text"], "Description from the catalogue.")
