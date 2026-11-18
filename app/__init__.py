from flask import Flask
from app.db import db
from app.routes import bp as main_bp

def create_app(config: dict | None = None):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///planner.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    db.init_app(app)
    app.register_blueprint(main_bp)

    return app