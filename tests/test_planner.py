import unittest
from unittest.mock import patch

from flask import Flask

from app.db import db
from app.models import CourseCache
from app.planner import (
    classify_courses,
    missing_prereqs,
    normalize_code,
    parse_prereqs,
    prereqs_satisfied,
)
from app.routes import bp
from app.scraper import course_url


CMPT_214_TEXT = (
    "Prerequisite(s): Completion at a 60% grade or higher, in one of "
    "CMPT 145.3, CMPT 146.3, CMPT 115.3 or CMPT 117.3. "
    "Note: Students who have credit for CMPT 330 may not take this course for credit."
)


class PrerequisiteTests(unittest.TestCase):
    def test_catalogue_course_codes_are_normalized(self):
        for code in ("cmpt145", " CMPT\t145 ", "cmpt 145.3"):
            with self.subTest(code=code):
                self.assertEqual(normalize_code(code), "CMPT 145")
                self.assertTrue(prereqs_satisfied([["CMPT 145"]], {code}))
                self.assertTrue(course_url(code).endswith("/CMPT-145"))
        self.assertEqual(normalize_code("math 100a.3"), "MATH 100A")

    def test_nested_alternatives_keep_the_shared_requirement(self):
        groups = parse_prereqs("Prerequisite(s): CMPT 145 and (MATH 110 or MATH 116).")
        self.assertEqual(groups, [["CMPT 145", "MATH 110"], ["CMPT 145", "MATH 116"]])
        self.assertFalse(prereqs_satisfied(groups, {"MATH 116"}))
        self.assertTrue(prereqs_satisfied(groups, {"CMPT 145", "MATH 116"}))

    def test_unparenthesized_one_of_binds_to_the_previous_and(self):
        groups = parse_prereqs(
            "Prerequisite(s): CMPT 214.3; and CMPT 280.3; "
            "and one of CMPT 215.3 or CME 331.3."
        )
        self.assertFalse(prereqs_satisfied(groups, {"CME 331"}))
        self.assertTrue(prereqs_satisfied(groups, {"CMPT 214", "CMPT 280", "CME 331"}))

    def test_parenthesized_one_of_lists_form_independent_choices(self):
        groups = parse_prereqs(
            "Prerequisite(s): One of (CMPT 145.3, CMPT146.3, CMPT 115.3, or CMPT 117.3); "
            "and one of (MATH110.3, MATH 133.4, MATH 163.3, or MATH 176.3)."
        )
        self.assertEqual(len(groups), 16)
        self.assertFalse(prereqs_satisfied(groups, {"CMPT 115"}))
        self.assertTrue(prereqs_satisfied(groups, {"CMPT 115", "MATH 133"}))

    def test_plain_one_of_lists_form_single_course_alternatives(self):
        groups = parse_prereqs("Prerequisites: One of CMPT 145.3, CMPT 146.3, or CMPT 117.3.")
        self.assertEqual(groups, [["CMPT 145"], ["CMPT 146"], ["CMPT 117"]])

    def test_semicolon_or_can_start_a_separate_alternative(self):
        groups = parse_prereqs(
            "Prerequisites: CMPT 100 and one of CMPT 141 or CMPT 145; or CMPT 146."
        )
        self.assertTrue(prereqs_satisfied(groups, {"CMPT 146"}))
        self.assertFalse(prereqs_satisfied(groups, {"CMPT 141"}))

    def test_multiline_section_stops_at_corequisites_or_notes(self):
        for heading in ("Co-requisite(s)", "Corequisites", "Note"):
            with self.subTest(heading=heading):
                groups = parse_prereqs(
                    f"Description. Prerequisite: CMPT 145\nand MATH 110.\n{heading}: STAT 242."
                )
                self.assertEqual(groups, [["CMPT 145", "MATH 110"]])

    def test_complex_and_malformed_requirements_need_manual_verification(self):
        examples = (
            CMPT_214_TEXT,
            "Prerequisite(s): Permission of the department.",
            "Prerequisite(s): CMPT 145 or permission of the department.",
            "Prerequisite(s): CMPT 145 (or equivalent).",
            "Prerequisite(s): CMPT 145 and (MATH 110 or MATH 116.",
            "Prerequisite(s): CMPT 145 or.",
            "Prerequisite(s):",
            "Prerequisite(s) or Corequisite(s): CMPT 145.",
            "",
        )
        for raw_text in examples:
            with self.subTest(raw_text=raw_text):
                groups = parse_prereqs(raw_text)
                self.assertIsNone(groups)
                self.assertFalse(prereqs_satisfied(groups, {"CMPT 145", "CMPT 117"}))

    def test_no_prerequisite_is_distinct_from_missing_catalogue_data(self):
        for raw_text in ("A course description.", "Prerequisite(s): None."):
            with self.subTest(raw_text=raw_text):
                self.assertEqual(parse_prereqs(raw_text), [])
        unlocked, locked = classify_courses({
            "CMPT 100": {"prereqs": []},
            "CMPT 200": {"prereqs": [], "not_found": True},
            "CMPT 300": {},
        }, set())
        self.assertEqual(unlocked, ["CMPT 100"])
        self.assertEqual([item["course"] for item in locked], ["CMPT 200", "CMPT 300"])
        self.assertTrue(all("Manual verification" in item["reason"] for item in locked))

    def test_closest_alternative_counts_unique_missing_courses(self):
        groups = [["CMPT 145", "cmpt145.3"], ["MATH 110", "STAT 242"]]
        self.assertEqual(missing_prereqs(groups, set()), ["CMPT 145"])
        self.assertEqual(missing_prereqs(groups, {"MATH 110", "STAT 242"}), [])


class PlannerEndpointTests(unittest.TestCase):
    def setUp(self):
        app = Flask("app")
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(app)
        app.register_blueprint(bp)
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            # Older rows stored incorrect or unverified groups.
            db.session.add_all([
                CourseCache(code="CMPT 214", raw_text=CMPT_214_TEXT, prereqs_json='[["CMPT 117"]]'),
                CourseCache(code="CMPT 260", raw_text="Prerequisite: CMPT 145 and MATH 110.",
                            prereqs_json="[]"),
                CourseCache(code="CMPT 280", raw_text="Prerequisite: CMPT 145."),
                CourseCache(code="CMPT 332", raw_text="A course with no prerequisites."),
            ])
            db.session.commit()

    def test_status_and_legacy_share_results_and_keep_their_fields(self):
        with patch("app.services.get_course_raw_info", return_value={"not_found": True}) as scrape:
            payload = {"completed": ["cmpt145.3", " CMPT 141 ", "cmpt117"]}
            status = self.client.post("/api/planner/status", json=payload)
            legacy = self.client.post("/api/planner/unlocked", json=payload)

        self.assertEqual(status.status_code, 200)
        self.assertEqual(legacy.status_code, 200)
        status_data, legacy_data = status.get_json(), legacy.get_json()
        expected_common = {
            "unlocked": ["CMPT 280", "CMPT 332"], "completed_count": 3, "required_count": 7
        }
        for field, value in expected_common.items():
            self.assertEqual(status_data[field], value)
            self.assertEqual(legacy_data[field], value)

        self.assertEqual(status_data["locked"], [
            {"code": "CMPT 214", "missing_prereqs": [],
             "reason": "Manual verification needed: check the catalogue prerequisites."},
            {"code": "CMPT 260", "missing_prereqs": ["MATH 110"]},
            {"code": "CMPT 270", "missing_prereqs": [],
             "reason": "Manual verification needed: catalogue information is unavailable."},
        ])
        self.assertEqual(legacy_data["locked"], [
            {"course": item["code"], "missing": item["missing_prereqs"],
             **({"reason": item["reason"]} if "reason" in item else {})}
            for item in status_data["locked"]
        ])
        self.assertEqual({call.args[0] for call in scrape.call_args_list},
                         {"CMPT 141", "CMPT 145", "CMPT 270"})

    def test_invalid_completed_values_return_a_client_error(self):
        for path in ("/api/planner/status", "/api/planner/unlocked"):
            for completed in (None, "CMPT 145", [145]):
                with self.subTest(path=path, completed=completed):
                    response = self.client.post(path, json={"completed": completed})
                    self.assertEqual(response.status_code, 400)

    def test_legacy_get_still_explains_how_to_use_post(self):
        response = self.client.get("/api/planner/unlocked")
        self.assertEqual(response.status_code, 405)
        self.assertIn("Use POST", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
