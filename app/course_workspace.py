"""Personal course records and locally indexed study materials."""

from datetime import date, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.calendar_store import CalendarEvent, list_events
from app.db import db
from app.institutions.usask import catalogue_url, cmpt_catalogue
from app.planner import COURSE_RE, normalize_code
from app.student_migrations import student_storage_ready
from app.syllabus_files import MAX_UPLOAD_BYTES, SyllabusFileError, read_document

bp = Blueprint("workspace", __name__)
MAX_COURSE_FILES = 24
DEADLINE_CATEGORIES = {"assignment", "exam", "quiz"}
STUDENT_ZONE = ZoneInfo("America/Regina")


class StudentCourse(db.Model):
    __tablename__ = "student_courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    title = db.Column(db.String(160), nullable=False)
    notes = db.Column(db.Text, nullable=False, default="")


class CourseMaterial(db.Model):
    __tablename__ = "course_materials"
    __table_args__ = (db.UniqueConstraint("course_id", "fingerprint"),)

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("student_courses.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    kind = db.Column(db.String(5), nullable=False)
    content = db.deferred(db.Column(db.LargeBinary, nullable=False))
    indexed_text = db.Column(db.Text, nullable=False, default="")


def storage_available() -> bool:
    return student_storage_ready(StudentCourse, CourseMaterial)


def needs_course_setup() -> bool:
    return storage_available() and db.session.scalar(select(StudentCourse.id).limit(1)) is None


def student_agenda(
    days: int, *, categories=None, course_code: str | None = None, deadlines_only: bool = False
) -> list[dict]:
    """Read the student's dated calendar entries for the local planning window."""
    if not student_storage_ready(CalendarEvent):
        return []
    now = datetime.now(STUDENT_ZONE)
    today = now.date()
    events = list_events(today.isoformat(), (today + timedelta(days=days)).isoformat(), STUDENT_ZONE.key)
    visible = []
    for record in events:
        event = record.as_dict()
        if deadlines_only and not is_deadline(event):
            continue
        if categories and event["category"] not in categories:
            continue
        if course_code and event["course_code"] != course_code:
            continue
        if event["all_day"]:
            if event["end"] <= today.isoformat():
                continue
        elif datetime.fromisoformat(event["end"].replace("Z", "+00:00")) <= now:
            continue
        if event["all_day"]:
            local_day = date.fromisoformat(event["start"])
            clock_label = "Due this day" if event["deadline"] else "All day"
            event["when"] = f"{local_day:%a, %b} {local_day.day} · {clock_label}"
        else:
            local_start = datetime.fromisoformat(event["start"].replace("Z", "+00:00")).astimezone(STUDENT_ZONE)
            due = "Due " if event["deadline"] else ""
            event["when"] = f"{local_start:%a, %b} {local_start.day} · {due}{local_start:%I:%M %p}"
        visible.append(event)
    return visible


def is_deadline(event: dict) -> bool:
    return event["deadline"] or event["category"] in DEADLINE_CATEGORIES


def _course_or_404(course_id: int) -> StudentCourse:
    if not storage_available():
        abort(503, "Course storage has not been enabled.")
    return db.get_or_404(StudentCourse, course_id)


def _render_index(error=None, *, code="", title=""):
    ready = storage_available()
    courses = db.session.scalars(select(StudentCourse).order_by(StudentCourse.code)).all() if ready else []
    return render_template("student_courses.html", courses=courses, ready=ready, error=error, form_code=code, form_title=title), 422 if error else 200


@bp.route("/student/courses", methods=["GET", "POST"])
def courses():
    if request.method == "GET":
        return _render_index()
    if not storage_available():
        abort(503, "Course storage has not been enabled.")
    submitted_code = request.form.get("code", "")
    code = normalize_code(submitted_code)
    title = request.form.get("title", "").strip()
    if not COURSE_RE.fullmatch(code) or len(title) > 160:
        return _render_index("Enter a course code like CMPT 141 and a title up to 160 characters.", code=submitted_code[:20], title=title[:160])
    title = title or cmpt_catalogue()["courses"].get(code, {}).get("title") or code
    course = StudentCourse(code=code, title=title)
    db.session.add(course)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_index(f"{code} already has a workspace. Open it above to add notes or deadlines.", code=submitted_code[:20], title=title)
    return redirect(url_for("workspace.course_page", course_id=course.id), code=303)


def _render_course(course, *, query="", error=None, note_form=None):
    materials = select(CourseMaterial).where(CourseMaterial.course_id == course.id).order_by(CourseMaterial.id.desc())
    if query:
        needle = query.lower()
        materials = materials.where(
            func.lower(CourseMaterial.name).contains(needle, autoescape=True)
            | func.lower(CourseMaterial.indexed_text).contains(needle, autoescape=True)
        )
    return render_template(
        "student_course.html", course=course, materials=db.session.scalars(materials).all(),
        deadlines=student_agenda(90, course_code=course.code, deadlines_only=True),
        catalogue=catalogue_url(course.code), query=query, error=error, note_form=note_form,
    ), 422 if error else 200


@bp.get("/student/courses/<int:course_id>")
def course_page(course_id):
    return _render_course(_course_or_404(course_id), query=request.args.get("q", "").strip()[:100])


@bp.post("/student/courses/<int:course_id>/notes")
def save_notes(course_id):
    course = _course_or_404(course_id)
    title = request.form.get("title", "").strip()
    notes = request.form.get("notes", "")
    if not title or len(title) > 160 or len(notes) > 20_000:
        return _render_course(
            course, error="Enter a title up to 160 characters and notes up to 20,000 characters.",
            note_form={"title": title[:160], "notes": notes[:20_000]},
        )
    course.title = title
    course.notes = notes
    db.session.commit()
    return redirect(url_for("workspace.course_page", course_id=course.id, saved="notes"), code=303)


@bp.post("/student/courses/<int:course_id>/materials")
def upload_material(course_id):
    course = _course_or_404(course_id)
    request.max_content_length = MAX_UPLOAD_BYTES + 64 * 1024
    file = request.files.get("material")
    name = secure_filename(file.filename or "") if file else ""
    suffix = PurePath(name).suffix.lower()
    if not file or suffix not in {".pdf", ".txt"} or len(name) > 160:
        return _render_course(course, error="Choose a PDF or UTF-8 text file with a shorter filename.")
    data = file.stream.read(MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > MAX_UPLOAD_BYTES:
        return _render_course(course, error="Choose a nonempty file up to 4 MB.")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        return _render_course(course, error="This file does not have a PDF header.")
    count = db.session.scalar(select(func.count()).select_from(CourseMaterial).where(CourseMaterial.course_id == course.id))
    if count >= MAX_COURSE_FILES:
        return _render_course(course, error="Remove a file before adding another. Each course can keep 24 materials.")
    try:
        text = "\n".join(page for _, page in read_document(data, suffix))[:150_000]
    except SyllabusFileError as error:
        if suffix == ".txt":
            return _render_course(course, error=str(error))
        # Scanned or encrypted PDFs can still be filed and searched by name.
        text = ""
    db.session.add(CourseMaterial(
        course_id=course.id, name=name, fingerprint=sha256(data).hexdigest(),
        kind=suffix[1:], content=data, indexed_text=text,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_course(course, error="This course already has a copy of that file.")
    return redirect(url_for("workspace.course_page", course_id=course.id, saved="material"), code=303)


def _material_or_404(course_id: int, material_id: int) -> CourseMaterial:
    _course_or_404(course_id)
    return db.first_or_404(select(CourseMaterial).where(
        CourseMaterial.course_id == course_id, CourseMaterial.id == material_id,
    ))


@bp.get("/student/courses/<int:course_id>/materials/<int:material_id>")
def download_material(course_id, material_id):
    material = _material_or_404(course_id, material_id)
    response = send_file(BytesIO(material.content), download_name=material.name, as_attachment=True)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.post("/student/courses/<int:course_id>/materials/<int:material_id>/remove")
def remove_material(course_id, material_id):
    if request.form.get("confirmed") != "yes":
        abort(400, "Confirm removal before deleting a study material.")
    db.session.delete(_material_or_404(course_id, material_id))
    db.session.commit()
    return redirect(url_for("workspace.course_page", course_id=course_id, saved="removed"), code=303)


@bp.get("/student/agenda")
def agenda():
    view = request.args.get("view", "today")
    views = {
        "today": ("Today", 1, None),
        "week": ("Next seven days", 7, None),
        "exams": ("Upcoming exams", 90, {"exam"}),
    }
    if view not in views:
        abort(404)
    title, days, categories = views[view]
    events = student_agenda(days, categories=categories)
    first_deadline = next((event for event in events if is_deadline(event)), None)
    return render_template(
        "student_agenda.html", view=view, title=title, events=events, suggestion=first_deadline,
        ready=student_storage_ready(CalendarEvent),
    )
