import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.course_workspace import CourseMaterial
from app.db import db
from app.models import Plan
from app.student_migrations import upgrade_student_schema


class MigrationRehearsalTests(unittest.TestCase):
    def test_backup_restore_and_schema_conflict_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "legacy.db"
            backup = base / "before.db"
            restored = base / "restored.db"
            app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}"})
            with app.app_context():
                Plan.__table__.create(db.engine)
                db.session.add(Plan(name="Original plan"))
                db.session.commit()
                with db.engine.begin() as connection:
                    connection.exec_driver_sql("CREATE TABLE calendar_events (id INTEGER PRIMARY KEY)")
                with self.assertRaisesRegex(ValueError, "Unversioned student table"):
                    upgrade_student_schema(backup=backup)
                self.assertFalse(backup.exists())
                with db.engine.begin() as connection:
                    connection.exec_driver_sql("DROP TABLE calendar_events")
                self.assertEqual(upgrade_student_schema(backup=backup), [1, 2])
                self.assertEqual(db.session.scalar(db.select(Plan.name)), "Original plan")
            with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as source:
                self.assertEqual(source.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                with closing(sqlite3.connect(restored)) as target:
                    source.backup(target)
                    self.assertEqual(target.execute("SELECT name FROM plans").fetchall(), [("Original plan",)])
                    self.assertEqual(target.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall(),
                                     [("plans",)])

    def test_failed_upgrade_keeps_backup_and_rolls_back_schema_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "legacy.db"
            backup = base / "before.db"
            app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}"})
            with app.app_context():
                Plan.__table__.create(db.engine)
                db.session.add(Plan(name="Keep this plan"))
                db.session.commit()
                with patch.object(CourseMaterial.__table__, "create", side_effect=RuntimeError("simulated failure")):
                    with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                        upgrade_student_schema(backup=backup)
            for path in (database, backup):
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
                    self.assertEqual(source.execute("SELECT name FROM plans").fetchall(), [("Keep this plan",)])
                    tables = source.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
                    self.assertEqual(tables, [("plans",)])
