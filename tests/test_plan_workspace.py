import unittest

from app import create_app
from app.db import db
from app.models import CourseCache


class PlanWorkspaceTests(unittest.TestCase):
    def setUp(self):
        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            db.session.add_all([
                CourseCache(code="CMPT 270", raw_text="A catalogue description."),
                CourseCache(code="CMPT 280", raw_text="Prerequisite: CMPT 270."),
                CourseCache(code="CMPT 214", raw_text="Prerequisite: 60% in CMPT 145."),
            ])
            db.session.commit()

    def test_existing_export_round_trips_without_overwriting_prior_plan(self):
        original = self.client.post("/api/plan/save", json={
            "name": "First plan", "completed": ["cmpt141.3"], "notes": "Check electives",
        }).get_json()["plan"]
        exported = self.client.get("/api/plan/export").get_json()
        self.assertEqual(exported, {"name": "First plan", "completed": ["CMPT 141"], "notes": "Check electives"})
        imported = self.client.post("/api/plan/import", json=exported).get_json()["plan"]
        self.assertGreater(imported["id"], original["id"])
        self.assertEqual(self.client.get("/api/plan/load").get_json()["plan"], imported)
        self.assertEqual(self.client.post("/api/plan/import", json={"completed": [4]}).status_code, 400)

    def test_plan_responses_are_private_and_cross_site_writes_are_rejected(self):
        payload = {"name": "Private plan", "completed": [], "notes": "Advising notes"}
        self.assertEqual(self.client.post("/api/plan/save", json=payload).status_code, 200)
        for path in ("/api/plan/save", "/api/plan/import"):
            rejected = self.client.post(path, json=payload, headers={"Origin": "https://example.test"})
            self.assertEqual(rejected.status_code, 403)
        for path in ("/api/plan/load", "/api/plan/export"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_sequence_checks_earlier_terms_and_flags_unknown_requirements(self):
        response = self.client.post("/api/planner/sequence", json={
            "completed": [], "terms": [["CMPT 280", "CMPT 270"], ["CMPT 214", "CMPT 999"]],
        })
        first, second = response.get_json()["terms"]
        self.assertEqual(first[0]["missing"], ["CMPT 270"])
        self.assertIn("Manual verification needed", second[0]["reason"])
        self.assertIn("catalogue information is unavailable", second[1]["reason"])

        response = self.client.post("/api/planner/sequence", json={
            "completed": [], "terms": [["CMPT270"], ["CMPT 280"]],
        })
        second = response.get_json()["terms"][1]
        self.assertEqual(second[0]["missing"], [])
        self.assertEqual(second[0]["dependencies"], [["CMPT 270"]])

    def test_sequence_rejects_duplicate_course_placements(self):
        response = self.client.post("/api/planner/sequence", json={"terms": [["CMPT270"], ["CMPT 270"]]})
        self.assertEqual(response.status_code, 400)
