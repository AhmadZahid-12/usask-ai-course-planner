"""HTTP routes for the student calendar."""

from flask import Blueprint, jsonify, render_template, request

from app.calendar_store import (
    DEFAULT_TIMEZONE,
    CalendarEvent,
    CalendarValidationError,
    create_event,
    list_events,
    update_event,
)
from app.db import db
from app.student_migrations import student_storage_ready

bp = Blueprint("calendar", __name__)


@bp.get("/calendar")
def page():
    event_id = request.args.get("event", type=int)
    selected_event = None
    if event_id is not None and 0 < event_id <= 2**63 - 1 and student_storage_ready(CalendarEvent):
        stored = db.session.get(CalendarEvent, event_id)
        selected_event = stored.as_dict() if stored else None
    return render_template("calendar.html", selected_event=selected_event)


@bp.before_request
def check_storage():
    if request.endpoint != "calendar.page" and not student_storage_ready(CalendarEvent):
        return jsonify(error="Calendar storage needs setup before events can be used."), 503


@bp.errorhandler(CalendarValidationError)
def invalid_event(error):
    return jsonify(error=str(error)), 400


@bp.route("/api/calendar/events", methods=["GET", "POST"])
def events():
    if request.method == "POST":
        event = create_event(request.get_json(silent=True))
        result = event.as_dict()
        db.session.commit()
        return jsonify(event=result), 201
    records = list_events(
        request.args.get("start"),
        request.args.get("end"),
        request.args.get("tz", DEFAULT_TIMEZONE),
    )
    return jsonify(events=[event.as_dict() for event in records])


@bp.route("/api/calendar/events/<int:event_id>", methods=["PATCH", "DELETE"])
def event(event_id: int):
    stored = db.session.get(CalendarEvent, event_id)
    if stored is None:
        return jsonify(error="That event could not be found."), 404
    if request.method == "DELETE":
        db.session.delete(stored)
        db.session.commit()
        return "", 204

    update_event(stored, request.get_json(silent=True))
    result = stored.as_dict()
    db.session.commit()
    return jsonify(event=result)
