from datetime import datetime
from app.db import db


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default="My Plan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # stored as JSON string for simplicity
    completed_json = db.Column(db.Text, nullable=False, default="[]")
    notes = db.Column(db.Text, nullable=False, default="")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "completed_json": self.completed_json,
            "notes": self.notes,
        }


class CourseCache(db.Model):
    """
    Cache of scraped official text + parsed prereqs for faster planner logic.
    """
    __tablename__ = "course_cache"

    code = db.Column(db.String(20), primary_key=True)
    source_url = db.Column(db.Text, nullable=False, default="")
    raw_text = db.Column(db.Text, nullable=False, default="")
    prereqs_json = db.Column(db.Text, nullable=False, default="[]")  # OR-of-AND groups as JSON string

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "code": self.code,
            "source_url": self.source_url,
            "raw_text": self.raw_text,
            "prereqs_json": self.prereqs_json,
            "updated_at": self.updated_at.isoformat(),
        }