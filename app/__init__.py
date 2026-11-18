from flask import Flask, abort, request

from app.db import db
from app.routes import bp as main_bp

STUDENT_BLUEPRINTS = {"calendar", "syllabus", "workspace"}


def create_app(config: dict | None = None):
    from app.calendar_routes import bp as calendar_bp
    from app.course_workspace import bp as workspace_bp
    from app.student_migrations import register_student_migrations
    from app.syllabus import bp as syllabus_bp

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///planner.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    db.init_app(app)
    for blueprint in (main_bp, calendar_bp, syllabus_bp, workspace_bp):
        app.register_blueprint(blueprint)
    register_student_migrations(app)

    @app.context_processor
    def student_navigation():
        return {"student_navigation": True}

    @app.before_request
    def protect_student_mutations():
        if request.blueprint not in STUDENT_BLUEPRINTS:
            return None
        if request.method not in {"POST", "PATCH", "PUT", "DELETE"}:
            return None
        origin = request.headers.get("Origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
            origin and origin != request.host_url.rstrip("/")
        ):
            abort(403)
        return None

    @app.after_request
    def protect_student_responses(response):
        if request.blueprint in STUDENT_BLUEPRINTS or request.endpoint == "main.home":
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
