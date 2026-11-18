import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask

from app.calendar_routes import bp
from app.calendar_store import CalendarEvent, create_event, upcoming_events
from app.db import db
from app.models import Plan
from app.student_migrations import register_student_migrations, student_storage_ready, upgrade_student_schema


def _app(uri="sqlite://"):
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=uri)
    db.init_app(app)
    app.register_blueprint(bp)
    register_student_migrations(app)
    return app


def _timed(**overrides):
    return {
        "title": "Database quiz",
        "category": "quiz",
        "course_code": "cmpt141",
        "timezone": "America/Toronto",
        "start": "2026-11-01T01:30:00-04:00",
        "end": "2026-11-01T01:30:00-05:00",
        **overrides,
    }


def _range(client, start, end, tz="America/Regina"):
    return client.get("/api/calendar/events", query_string={"start": start, "end": end, "tz": tz})


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.client = self.app.test_client()
        with self.app.app_context():
            upgrade_student_schema(target=1)

    def test_create_edit_list_delete_and_reconnect(self):
        created = self.client.post("/api/calendar/events", json=_timed(reminder_minutes=30))
        self.assertEqual(created.status_code, 201)
        event = created.get_json()["event"]
        url = f"/api/calendar/events/{event['id']}"
        self.assertEqual(event["course_code"], "CMPT 141")
        self.assertEqual(event["start"], "2026-11-01T05:30:00Z")
        self.assertEqual(event["end"], "2026-11-01T06:30:00Z")
        self.assertEqual(event["reminder_at"], "2026-11-01T05:00:00Z")

        other_client = self.app.test_client()
        found = _range(other_client, "2026-10-31", "2026-11-01").get_json()["events"]
        self.assertEqual(found, [event])

        updated = self.client.patch(url, json={"title": "Updated quiz", "reminder_minutes": None})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["event"]["title"], "Updated quiz")
        self.assertIsNone(updated.get_json()["event"]["reminder_at"])
        invalid = self.client.patch(url, json={"end": "2026-11-01T00:00:00Z"})
        self.assertEqual(invalid.status_code, 400)
        found = _range(other_client, "2026-10-31", "2026-11-01").get_json()["events"]
        self.assertEqual(found[0]["end"], event["end"])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_all_day_dates_do_not_shift_across_time_zones(self):
        response = self.client.post("/api/calendar/events", json={
            "title": "Submit assignment",
            "category": "assignment",
            "all_day": True,
            "start": "2026-11-03",
            "end": "2026-11-05",
            "reminder_minutes": 60,
        })
        self.assertEqual(response.status_code, 201)
        expected = response.get_json()["event"]
        for zone in ("Asia/Tokyo", "America/Regina"):
            event = _range(self.client, "2026-11-04", "2026-11-05", zone).get_json()["events"][0]
            self.assertEqual(event, expected)
        excluded = _range(self.client, "2026-11-05", "2026-11-06").get_json()["events"]
        self.assertEqual(excluded, [])
        self.assertEqual(expected["reminder_at"], "2026-11-03T05:00:00Z")

    def test_invalid_events_and_ranges(self):
        for patch in (
            {"title": "  "},
            {"category": []},
            {"start": "2026-11-01T01:30:00"},
            {"start": "2026-11-01T01:30:00+30:00"},
            {"start": "2026-11-01T01:30:00+00:89"},
            {"timezone": "../../etc/password"},
            {"course_code": "This is not a course code"},
            {"all_day": "true"},
            {"reminder_minutes": True},
            {"reminder_minutes": 10081},
        ):
            with self.subTest(patch=patch):
                self.assertEqual(self.client.post("/api/calendar/events", json=_timed(**patch)).status_code, 400)
        self.assertEqual(self.client.post("/api/calendar/events", data="broken").status_code, 400)
        self.assertEqual(_range(self.client, "2026-01-01", "2027-02-01").status_code, 400)
        self.assertEqual(_range(self.client, "2026-02-30", "2026-03-01").status_code, 400)
        self.assertEqual(_range(self.client, "2026-11-01", "2026-11-02", "/etc/passwd").status_code, 400)

    def test_upcoming_respects_local_day_and_older_timed_events(self):
        with self.app.app_context():
            for title, stamp in (
                ("Past", "2026-11-01T01:30:00Z"),
                ("Upcoming", "2026-11-01T23:45:00Z"),
            ):
                create_event(_timed(title=title, start=stamp, end="2026-11-02T00:30:00Z"))
            db.session.commit()
            now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
            self.assertEqual([event.title for event in upcoming_events(now=now)], ["Upcoming"])


class MigrationTests(unittest.TestCase):
    def test_missing_file_is_not_created_when_checking_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh.sqlite"
            app = _app(f"sqlite:///{path}")
            self.assertEqual(app.test_client().get("/api/calendar/events").status_code, 503)
            self.assertFalse(path.exists())

    def test_legacy_db_backup_and_idempotent_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            backup = Path(directory) / "backup.sqlite"
            app = _app(f"sqlite:///{path}")
            with app.app_context():
                Plan.__table__.create(db.engine)
                db.session.add(Plan(name="Existing plan", completed_json='["CMPT 141"]'))
                db.session.commit()

                with self.assertRaisesRegex(ValueError, "--backup"):
                    upgrade_student_schema(target=1)
                self.assertFalse(student_storage_ready(CalendarEvent))
                self.assertEqual(upgrade_student_schema(backup=backup, target=1), [1])
                self.assertTrue(student_storage_ready(CalendarEvent))
                self.assertTrue(student_storage_ready(Plan))
                self.assertEqual(db.session.scalar(db.select(Plan.name)), "Existing plan")
                self.assertEqual(upgrade_student_schema(target=1), [])

            with sqlite3.connect(backup) as prior:
                self.assertEqual(prior.execute("SELECT name FROM plans").fetchone()[0], "Existing plan")
                self.assertFalse(prior.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'calendar_events'"
                ).fetchone())

    def test_existing_backup_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            backup = Path(directory) / "keep-me.sqlite"
            app = _app(f"sqlite:///{path}")
            backup.write_bytes(b"original")
            with app.app_context():
                Plan.__table__.create(db.engine)
                with self.assertRaises(FileExistsError):
                    upgrade_student_schema(backup=backup, target=1)
                self.assertFalse(student_storage_ready(CalendarEvent))
            self.assertEqual(backup.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
